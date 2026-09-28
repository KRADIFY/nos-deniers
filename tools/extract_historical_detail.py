"""Extract historical RAP movements with independent printed totals and source proof.

Only report candidates are written. The application registry is never modified.
Every opening/cancellation header starts a separate block; continuations share
an unfinished table, while every caption is classified independently.
"""
from __future__ import annotations
import argparse, collections, datetime, hashlib, json, re, sqlite3, sys, unicodedata
from decimal import Decimal
from pathlib import Path
import fitz
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from budget_service.reconciliation import assess_difference, difference_note, capped_rounding_bound
COLUMNS=[dict(direction=d,sign=s,measure=m,title=t) for d,s in [('opening',1),('cancellation',-1)] for m in ('AE','CP') for t in ('2','HT2')]
CAPTION_START=re.compile(r'^(ARRETES|DECRETS|LOIS? DE FINANCES|OUVERTURES PAR VOIE|TOTAL DES OUVERTURES)')
RECAP='RECAPITULATION DES MOUVEMENTS DE CREDITS'

def norm(text):
    return ' '.join(unicodedata.normalize('NFKD',text.replace('\ufffd','e').replace('’', chr(39))).encode('ascii','ignore').decode().upper().replace("'",' ').split())

def kind_of(text):
    t=norm(text)
    if 'TOTAL DES OUVERTURES' in t:return 'TOTAL',None
    if 'ANNULATION' in t:return ('ANNULATION_FDC_ADP','FDC') if any(x in t for x in ('FDC','FONDS DE CONCOURS','ADP','ATTRIBUTION')) else ('ANNULATION','LEGIS')
    if 'DECRET' in t and 'AVANCE' in t:return 'DECRET_AVANCE','REGLEMENT'
    if 'DEPENSES ACCIDENTELLES' in t:return 'DEPENSES_ACCIDENTELLES','REGLEMENT'
    if 'TRANSFERT' in t:return 'TRANSFERT','REGLEMENT'
    if 'VIREMENT' in t:return 'VIREMENT','REGLEMENT'
    if 'REPARTITION' in t:return 'REPARTITION','REGLEMENT'
    if 'FINANCES RECTIFICATIV' in t or 'FINANCES DE FIN DE GESTION' in t:return 'LOI_FINANCES','LEGIS'
    if 'REPORT' in t:
        if 'HORS FONDS' in t or 'HORS FDC' in t:return 'REPORT_GENERAL','REPORT_ENTRANT'
        if 'AENE' in t or 'NON ENGAG' in t:return 'REPORT_AENE','REPORT_ENTRANT'
        if 'TRANCHES FONCTIONNELLES' in t:return 'REPORT_TRANCHES_FONCTIONNELLES','REPORT_ENTRANT'
        if 'FDC' in t or 'FONDS DE CONCOURS' in t:return 'REPORT_FDC','REPORT_ENTRANT'
        return 'REPORT_GENERAL','REPORT_ENTRANT'
    if re.search(r'ATTRIBUTIONS? DE PRODUITS',t) or 'ADP' in t:return 'RATTACHEMENT_ADP','FDC'
    if 'FONDS DE CONCOURS' in t or 'FDC' in t:return 'RATTACHEMENT_FDC','FDC'
    return None

def num(text):
    cleaned=''.join(text.split())
    if not re.fullmatch(r'[+-]?\d+(?:,\d+)?',cleaned):return None
    value=Decimal(cleaned.replace(',','.'))*100
    if value!=value.to_integral_value():raise ValueError(('fractional_cent',text))
    return int(value)

def get_lines(page):
    return sorted([{'text':''.join(sp['text'] for sp in ln['spans']).strip(),'bbox':[float(z) for z in ln['bbox']]} for b in page.get_text('dict')['blocks'] for ln in b.get('lines',[])],key=lambda x:(round(x['bbox'][1],1),x['bbox'][0]))

def midpoint(line):return (line['bbox'][0]+line['bbox'][2])/2

def cells_at(area,anchor,headers):
    values=[dict(c,amount_cents=None,raw_text=None) for c in COLUMNS]
    for z in area:
        if abs(z['bbox'][1]-anchor['bbox'][1])>1.5 or z['bbox'][0]<=anchor['bbox'][2]:continue
        value=num(z['text'])
        if value is None:continue
        j=min(range(8),key=lambda j:abs(midpoint(headers[j])-midpoint(z)))
        if abs(midpoint(headers[j])-midpoint(z))>32:raise ValueError(('numeric_column_outside_headers',anchor['text'],z))
        if values[j]['amount_cents'] is not None:raise ValueError(('duplicate_numeric_column',anchor['text'],j))
        if value<0:raise ValueError(('negative_source_cell_requires_review',anchor['text'],z))
        values[j].update(amount_cents=value,raw_text=z['text'],bbox=z['bbox'])
    return values

def checks_for(total,rows):
    checks=[]
    for i,cell in enumerate(total['cells']):
        amounts=[r['cells'][i]['amount_cents'] for r in rows if r['cells'][i]['amount_cents'] is not None]
        delta=(cell['amount_cents'] or 0)-sum(amounts)
        bound=capped_rounding_bound(len(amounts),0) if amounts else 0
        checks.append(dict(column=i,difference_cents=delta,rounding_bound_cents=bound,status='exact' if delta==0 else 'published_rounding_difference' if abs(delta)<=bound else 'material_difference',accepted=abs(delta)<=bound))
    return checks

def parse_document(path,year,mission,program,source,sha):
    rows=[];totals=[];problems=[];pages_read=[];captions=[];sections=[]
    with fitz.open(path) as doc:
        # Fast text pass finds the relevant recapitulation. Geometry is read only
        # for its actual pages, and all numerical cells retain physical boxes.
        starts=[]
        for pi,page in enumerate(doc):
            text=norm(page.get_text())
            if RECAP in text:
                present=re.findall(r'PROGRAMME N\D{0,5}(\d{3})',text)
                if present and program not in present:continue
                starts.append(pi)
        if not starts:return [],[],['no_recapitulation_heading'],dict(pages=[],caption_variants=[])
        if len(starts)>1:return [],[],['multiple_recapitulations_require_program_review'],dict(pages=[p+1 for p in starts],caption_variants=[])
        active=None;finished=False;start=starts[0]
        for pi in range(start,min(len(doc),start+30)):
            page=doc[pi];ls=get_lines(page);pages_read.append(pi+1)
            pageprograms=re.findall(r'PROGRAMME N\D{0,5}(\d{3})',norm(page.get_text()))
            if pageprograms and program not in pageprograms:
                problems.append('program_context_changed_before_grand_total');break
            heading=next((l['bbox'][1] for l in ls if RECAP in norm(l['text'])),0) if pi==start else 0
            opens=[l for l in ls if norm(l['text'])=='OUVERTURES' and l['bbox'][1]>heading]
            for oi,op in enumerate(opens):
                oy=op['bbox'][1];upper=opens[oi+1]['bbox'][1] if oi+1<len(opens) else page.rect.height
                before=[l for l in ls if 0<oy-l['bbox'][1]<85 and CAPTION_START.match(norm(l['text']))]
                cap=before[-1] if before else None
                if cap:
                    if active and not active.get('closed'):active['closed']=True  # Some one-row tables have no printed subtotal.
                    # Wrapped titles can place the identifying tail on a second line.
                    caption=' '.join(l['text'] for l in ls if cap['bbox'][1]<=l['bbox'][1]<oy and l['bbox'][0]<80)
                    if not caption:caption=cap['text']
                    classified=kind_of(caption);captions.append(caption)
                    if classified is None:problems.append(f'unrecognized_caption:{caption}');active=None;continue
                    k,stage=classified
                    active=dict(table_id=f'rap-{year}-{mission.lower()}-{program}-p{pi+1}-{k.lower()}-{oi}',kind=k,stage=stage,caption=caption,caption_page=pi+1,caption_bbox=cap['bbox'],rows=[],closed=False)
                elif active is None or active.get('closed') or oi!=0:
                    boundary=min([l['bbox'][1] for l in ls if oy<l['bbox'][1]<upper and CAPTION_START.match(norm(l['text']))] or [upper])
                    body=[l for l in ls if oy<l['bbox'][1]<boundary]
                    if not any(num(l['text']) is not None or re.fullmatch(r'\d{2}/(?:\d{2}/)?\d{4}',l['text']) or norm(l['text']) in ('TOTAL','TOTAL GENERAL') for l in body):continue
                    problems.append(f'orphan_continuation_page:{pi+1}');continue
                if cap:sections.append(active)
                area=[l for l in ls if oy<l['bbox'][1]<upper]
                nextcaps=[l for l in area if CAPTION_START.match(norm(l['text']))]
                if nextcaps:area=[l for l in area if l['bbox'][1]<nextcaps[0]['bbox'][1]]
                headers=[l for l in area if norm(l['text']) in ('TITRE 2','AUTRES TITRES')][:8]
                headers=sorted(headers,key=lambda l:l['bbox'][0])
                if len(headers)!=8 or [norm(l['text']) for l in headers]!=['TITRE 2','AUTRES TITRES']*4:
                    problems.append(f'invalid_eight_column_headers_page:{pi+1}');continue
                hy=max(l['bbox'][3] for l in headers)
                anchors=[l for l in area if l['bbox'][1]>hy and re.fullmatch(r'\d{2}/(?:\d{2}/)?\d{4}',l['text'])]
                for anchor in anchors:
                    raw=anchor['text'];precision='day' if len(raw)==10 else 'month'
                    dt=datetime.datetime.strptime(raw,'%d/%m/%Y' if precision=='day' else '%m/%Y')
                    date=dt.strftime('%Y-%m-%d' if precision=='day' else '%Y-%m')
                    row=dict(row_id=f'{active["table_id"]}-{date}-{len(active["rows"])}',table_id=active['table_id'],year=year,budget='BG',mission=mission,program=program,page=pi+1,source=source,sha256=sha,kind=active['kind'],reconciles_stage=active['stage'],date=date,date_precision=precision,date_kind='signature' if precision=='day' else 'month',table_title=active['caption'],source_date=raw,cells=cells_at(area,anchor,headers),bbox=anchor['bbox'],caption_page=active['caption_page'],caption_bbox=active['caption_bbox'],continuation=cap is None,published_precision="Montants publiés à l'euro dans le RAP.")
                    if not any(c['amount_cents'] is not None for c in row['cells']):problems.append(f'dated_row_without_cells:{row["row_id"]}')
                    rows.append(row);active['rows'].append(row)
                labels=[l for l in area if l['bbox'][1]>hy and norm(l['text']) in ('TOTAL','TOTAL GENERAL')]
                if len(labels)>1:problems.append(f'multiple_total_labels_page:{pi+1}')
                if labels:
                    anchor=labels[0];isgrand=active['kind']=='TOTAL'
                    if isgrand and norm(anchor['text'])!='TOTAL GENERAL':problems.append('grand_total_label_not_total_general')
                    if not isgrand and not active['rows']:problems.append(f'empty_dated_table:{active["table_id"]}')
                    total=dict(table_id=active['table_id'],year=year,budget='BG',mission=mission,program=program,page=pi+1,source=source,sha256=sha,kind=active['kind'],table_title=active['caption'],cells=cells_at(area,anchor,headers),headers=[dict(c,printed_label=l['text'],bbox=l['bbox']) for c,l in zip(COLUMNS,headers)],bbox=anchor['bbox'],raw_label=anchor['text'],caption_page=active['caption_page'],caption_bbox=active['caption_bbox'],is_grand_total=isgrand,checked_against_dated_rows=True,read_independently_from_source=True)
                    total['checks']=checks_for(total,rows if isgrand else active['rows'])
                    totals.append(total);active['closed']=True;active['printed_total_present']=True
                    if isgrand:finished=True;break
            if finished:break
        if not finished:problems.append('no_independent_grand_total')
        if not rows:problems.append('no_dated_rows')
        if any(not c['accepted'] for t in totals for c in t['checks']):problems.append('printed_total_difference_exceeds_bound')
    return rows,totals,problems,dict(pages=pages_read,caption_variants=captions,sections=[dict(table_id=t['table_id'],kind=t['kind'],caption=t['caption'],caption_page=t['caption_page'],dated_rows=len(t['rows']),printed_total_present=t.get('printed_total_present',False)) for t in sections])

def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def recover_missing_reference(path,year,program,reference,source):
    """Fill missing reference cells only from explicit current-year RAP evidence.

    Empty cells never imply zero. The P343/2018 CP zero has separate narrative
    proof, bound to a source hash. No canonical database row is changed here.
    """
    reference=dict(reference);proofs=[]
    labels={'TOTAL DES AE PREVUES EN LFI':('LFI','AE'),'TOTAL DES CP PREVUS EN LFI':('LFI','CP'),'TOTAL DES AE OUVERTES':('OUVERT','AE'),'TOTAL DES CP OUVERTS':('OUVERT','CP')}
    missing={(st,m) for st in ('LFI','OUVERT') for m in ('AE','CP') if (st,m) not in reference}
    if not missing:return reference,proofs
    with fitz.open(path) as doc:
        for pi,page in enumerate(doc):
            ls=get_lines(page)
            for anchor in ls:
                field=labels.get(norm(anchor['text']))
                if field not in missing:continue
                previous_headers=[(l,re.search(r'PREVISION LFI (\d{4})',norm(l['text']))) for l in ls if l['bbox'][1]<anchor['bbox'][1]]
                previous_headers=[(l,m) for l,m in previous_headers if m]
                if not previous_headers or previous_headers[-1][1].group(1)!=str(year):continue
                cells=[dict(raw_text=l['text'],amount_cents=num(l['text']),bbox=l['bbox']) for l in ls if abs(l['bbox'][1]-anchor['bbox'][1])<1.5 and l['bbox'][0]>anchor['bbox'][2] and num(l['text']) is not None]
                amounts={c['amount_cents'] for c in cells}
                # Equal repeated values avoid guessing which one is the total.
                # A zero LFI is accepted only when every published cell is zero.
                if len(amounts)!=1 or (field[0]=='LFI' and amounts!={0}):continue
                amount=next(iter(amounts));reference[field]=amount;missing.remove(field)
                proofs.append(dict(stage=field[0],measure=field[1],amount_cents=amount,source=source['id'],sha256=source['sha256'],page=pi+1,label=anchor['text'],bbox=anchor['bbox'],cells=cells,origin='independent_RAP_summary_table',canonical_fact_missing=True))
        if ('LFI','CP') in missing and (year,program)==(2018,'343') and source['sha256']=='19ae43035ed152563a182cb0b3cbf1ff344395908b6d34c3ce8ef135a3e9d86b':
            txt=doc[11].get_text();normalized=norm(txt)
            if 'JUSQU EN 2018, LE PROGRAMME 343 ETAIT DOTE UNIQUEMENT EN AE' in normalized:
                selected=[l for l in get_lines(doc[11]) if 'JUSQU' in norm(l['text']) or 'UNIQUEMENT EN AE' in norm(l['text'])]
                reference[('LFI','CP')]=0
                proofs.append(dict(stage='LFI',measure='CP',amount_cents=0,source=source['id'],sha256=source['sha256'],page=12,origin='explicit_RAP_narrative_no_CP_before_2019',source_lines=selected,canonical_fact_missing=True))
    return reference,proofs

def registry_from(rows,totals,scope,source,reference):
    year=scope['years'][0];items=[]
    for r in rows:
        for c in r['cells']:
            if c['amount_cents'] is None:continue
            items.append(dict(id=f'{r["row_id"]}/{c["measure"]}/{c["title"]}/{c["direction"]}',row_id=r['row_id'],year=year,budget='BG',mission=scope['mission'],program=scope['program'],title=c['title'],measure=c['measure'],kind=r['kind'],date=r['date'],date_precision=r['date_precision'],date_kind=r['date_kind'],sign=c['sign'],amount_cents=c['amount_cents'],source=source['id'],sha256=source['sha256'],page=r['page'],field=f'{r["table_title"]} · {r["source_date"]} · {c["direction"]} · {c["measure"]} · {c["title"]}',reconciles_stage=r['reconciles_stage'],linked_act_id=None))
    grand=next(t for t in totals if t['is_grand_total']);recs=[]
    for m in ('AE','CP'):
        chosen=[i for i in items if i['measure']==m];net=sum(x['sign']*x['amount_cents'] for x in chosen)
        printedcells=[c for c in grand['cells'] if c['measure']==m and c['amount_cents'] is not None]
        printed=sum(c['sign']*c['amount_cents'] for c in printedcells)
        lfi=reference.get(('LFI',m));canonical=reference.get(('OUVERT',m))
        if lfi is None or canonical is None:raise ValueError(('canonical_stage_missing',m))
        check=assess_difference(lfi+net,canonical,len(chosen));pc=assess_difference(lfi+printed,canonical,len(printedcells))
        recs.append(dict(year=year,measure=m,stage='OUVERT',status=check['status'],source=source['id'],sha256=source['sha256'],lfi_cents=lfi,reported_net_cents=net,lfi_plus_reported_cents=lfi+net,canonical_cents=canonical,difference_cents=check['difference_cents'],rounding_bound_cents=check['rounding_bound_cents'],materiality_bound_cents=check['materiality_bound_cents'],automatic_limit_cents=check['automatic_limit_cents'],printed_net_cents=printed,printed_difference_cents=pc['difference_cents'],printed_check=pc,printed_rounding_bound_cents=pc['rounding_bound_cents'],note=difference_note(check) if check['difference_cents'] else ''))
    return dict(scope=scope,sources=[source],items=items,evidence_rows=rows,table_totals=totals,reconciliations=recs,grand_total_checks=grand['checks'],source_validation=dict(independent_printed_totals=True,all_table_boundaries_classified=True,continuations_included=True))

def item_signature(reg):
    return sorted((x['kind'],x['date'],x['measure'],x['title'],x['sign'],x['amount_cents']) for x in reg['items'])

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=ROOT/'reports/reconciliation-10-euros-20260923');ap.add_argument('--limit',type=int);ap.add_argument('--retry-failures',action='store_true');args=ap.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    scanfile=ROOT/'reports/historique-2017-2022/mouvements-scan-candidates.json';dbpath=ROOT/'reports/historique-2017-2022/budget-opened-staged.sqlite';oldpath=ROOT/'budget_service/data/mouvements-rap-historique-detail.json'
    scan=json.loads(scanfile.read_text('utf8'))['items'];scan=scan[:args.limit] if args.limit else scan
    old=json.loads(oldpath.read_text('utf8'))['registries'];oldbykey={(r['scope']['years'][0],r['scope']['program']):r for r in old}
    conn=sqlite3.connect(dbpath.as_uri()+'?mode=ro',uri=True)
    contexts=collections.defaultdict(dict);references=collections.defaultdict(dict);otherbudgets=collections.defaultdict(set)
    for y,b,p,m,ml,pl in conn.execute('select distinct year,budget,program,mission,mission_label,program_label from facts'):
        if b=='BG':contexts[(y,str(p))].setdefault(m,set()).add((ml,pl))
        else:otherbudgets[(y,str(p))].add(b)
    for y,p,m,stage,measure,amount in conn.execute("select year,program,mission,stage,measure,sum(cents) from facts where budget='BG' and stage in ('LFI','OUVERT') group by year,program,mission,stage,measure"):
        references[(y,str(p),m)][(stage,measure)]=amount
    bysha={}
    for sid,raw in conn.execute('select id,data from sources'):
        src=json.loads(raw)
        if src.get('sha256'):bysha[src['sha256']]=(sid,src)
    conn.close();valid=collections.defaultdict(list);outcomes=[];counts=collections.Counter();cached_outcomes={};cached_regs={}
    if args.retry_failures:
        previous=json.loads((args.output/'historical-movements-extraction-review.json').read_text('utf8'))
        prior_regs=json.loads((args.output/'historical-movements-corrected-candidates.json').read_text('utf8'))['registries']
        assert previous['inputs']==dict(scan_sha256=digest(scanfile),canonical_db_sha256=digest(dbpath),previous_registry_sha256=digest(oldpath)), 'Inputs changed; run the full extractor instead.'
        cached_outcomes={r['sha256']:r for r in previous['source_outcomes'] if r['status'] not in ('extraction_exception','canonical_reconciliation_requires_review')}
        cached_regs={r['sources'][0]['sha256']:r for r in prior_regs}
    for idx,x in enumerate(scan):
        y,p=int(x['year']),str(x['program']);key=(y,p);context=contexts.get(key,{})
        outcome=dict(year=y,program=p,path=x['path'],sha256=x['source'],old_scan_status=x['status'])
        cached=cached_outcomes.get(x['source'])
        if cached and (cached['status']!='validated_candidate' or x['source'] in cached_regs):
            outcomes.append(cached);counts[cached['status']]+=1
            if cached['status']=='validated_candidate':valid[key].append(cached_regs[x['source']])
            continue
        if 'plf' in Path(x['path']).parts:outcome.update(status='plf_document_not_rap',other_budgets=sorted(otherbudgets.get(key,[])))
        elif not context:outcome.update(status='outside_bg_scope' if otherbudgets.get(key) else 'no_bg_canonical_reference',other_budgets=sorted(otherbudgets.get(key,[])))
        elif len(context)!=1:outcome.update(status='ambiguous_mission_codes',missions=sorted(context))
        elif x['source'] not in bysha:outcome.update(status='source_not_catalogued')
        else:
            mission=next(iter(context));variants=sorted(context[mission]);ml,pl=variants[0]
            if key in oldbykey:ml=oldbykey[key]['scope']['mission_label'];pl=oldbykey[key]['scope']['program_label']
            path=ROOT/x['path'];sid,sd=bysha[x['source']]
            if not path.exists():outcome.update(status='source_file_missing')
            elif digest(path)!=x['source']:outcome.update(status='source_hash_mismatch')
            else:
                outcome.update(source_hash_verified=True,mission=mission,label_variants=[dict(mission_label=a,program_label=b) for a,b in variants])
                try:
                    rows,totals,problems,inspection=parse_document(path,y,mission,p,sid,x['source']);outcome.update(inspection=inspection,rows=len(rows),items=sum(c['amount_cents'] is not None for r in rows for c in r['cells']),tables=len(totals),problems=problems)
                    if problems:outcome.update(status='source_extraction_requires_review',table_checks=[dict(table_id=t['table_id'],page=t['page'],checks=t['checks']) for t in totals if any(not c['accepted'] for c in t['checks'])])
                    else:
                        scope=dict(years=[y],budget='BG',mission=mission,mission_label=ml,program=p,program_label=pl,titles=['2','HT2'])
                        source=dict(id=sid,year=y,sha256=x['source'],title=sd.get('title',''),url=sd.get('url'),download_url='/api/download/'+sid)
                        reference,reference_proofs=recover_missing_reference(path,y,p,references[(y,p,mission)],source)
                        reg=registry_from(rows,totals,scope,source,reference)
                        reg['source_validation']['reference_fallback_proofs']=reference_proofs
                        outcome['reference_fallback_proofs']=reference_proofs
                        reg['source_validation']['table_sections']=inspection['sections']
                        outcome['reconciliations']=reg['reconciliations']
                        if all(abs(r['difference_cents'])<=1000 and r['printed_check']['accepted'] for r in reg['reconciliations']):
                            from budget_service.rap_validation import validate_movements
                            validate_movements(reg)
                            outcome['status']='validated_candidate';valid[key].append(reg)
                        else:outcome['status']='canonical_reconciliation_requires_review'
                except Exception as exc:outcome.update(status='extraction_exception',error=str(exc),error_type=type(exc).__name__)
        counts[outcome['status']]+=1;outcomes.append(outcome)
        if (idx+1)%25==0:print('progress',idx+1,dict(counts),flush=True)
    registries=[];conflicts=[]
    for key,variants in sorted(valid.items()):
        preferred=oldbykey.get(key,{}).get('sources',[{}])[0].get('sha256')
        variants.sort(key=lambda r:r['sources'][0]['sha256']!=preferred)
        chosen=variants[0];signatures=[item_signature(r) for r in variants]
        if any(s!=signatures[0] for s in signatures[1:]):
            conflicts.append(dict(year=key[0],program=key[1],sources=[r['sources'][0] for r in variants],status='different_validated_dated_details',retained_current_source=chosen['sources'][0]['sha256']==preferred))
            if chosen['sources'][0]['sha256']!=preferred:continue
        registries.append(chosen)
    newbykey={(r['scope']['years'][0],r['scope']['program']):r for r in registries};diffs=[]
    for key in sorted(set(oldbykey)|set(newbykey)):
        before=oldbykey.get(key);after=newbykey.get(key)
        row=dict(year=key[0],program=key[1],status='corrected' if before and after else 'new' if after else 'requires_review',previous_rows=len(before['evidence_rows']) if before else 0,candidate_rows=len(after['evidence_rows']) if after else 0,previous_items=len(before['items']) if before else 0,candidate_items=len(after['items']) if after else 0)
        if before and after:
            same=before['sources'][0]['sha256']==after['sources'][0]['sha256'];row['same_source']=same
            if same:
                token=lambda r:(r['page'],tuple(round(v,2) for v in r['bbox']))
                a={token(r):r for r in before['evidence_rows']};b={token(r):r for r in after['evidence_rows']}
                row['added_source_rows']=len(b.keys()-a.keys());row['lost_source_rows']=len(a.keys()-b.keys())
                row['corrected_category_rows']=sum(a[k]['kind']!=b[k]['kind'] for k in a.keys()&b.keys())
                row['changed_source_cells']=sum([c['amount_cents'] for c in a[k]['cells']] != [c['amount_cents'] for c in b[k]['cells']] for k in a.keys()&b.keys())
        diffs.append(row)
    summary=dict(source_candidates=len(scan),source_statuses=dict(counts),validated_registries=len(registries),items=sum(len(r['items']) for r in registries),evidence_rows=sum(len(r['evidence_rows']) for r in registries),table_totals=sum(len(r['table_totals']) for r in registries),previous_registries=len(old),previous_recovered=sum(k in newbykey for k in oldbykey),new_program_years=sum(k not in oldbykey for k in newbykey),source_variants_with_different_details=len(conflicts))
    metadata=dict(generated_at=datetime.datetime.now().isoformat(),extractor_sha256=digest(Path(__file__)),reused_reviewed_source_outcomes=len(cached_outcomes),counts=summary,source_precision='Published EUR converted to integer cents; source cells and totals retain raw text and PDF coordinates.',inputs=dict(scan_sha256=digest(scanfile),canonical_db_sha256=digest(dbpath),previous_registry_sha256=digest(oldpath)))
    (args.output/'historical-movements-corrected-candidates.json').write_text(json.dumps(dict(metadata,registries=registries),ensure_ascii=False,separators=(',',':')),encoding='utf8')
    (args.output/'historical-movements-extraction-review.json').write_text(json.dumps(dict(metadata,source_outcomes=outcomes,registry_changes=diffs,source_conflicts=conflicts),ensure_ascii=False,indent=2),encoding='utf8')
    print('FINAL',json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
