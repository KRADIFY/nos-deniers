"""Read all reserve columns, including cancellations, from verified historical PDFs.

Produces candidates and gaps only. It never overwrites application data.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, re, sqlite3, sys, unicodedata
from decimal import Decimal
from pathlib import Path
import fitz

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from budget_service.reconciliation import AUTOMATIC_DIFFERENCE_LIMIT_CENTS
FIELDS=('initial','surgels','degels','cancellations','remaining')
COLUMNS=('title2_cents','other_titles_cents','total_cents')


def norm(text):
    return ' '.join(unicodedata.normalize('NFKD',text).encode('ascii','ignore').decode().upper().split())


def field(text):
    t=norm(text)
    if t.startswith('MISE EN RESERVE INITIALE'):return 'initial'
    if t.startswith('SURGELS'):return 'surgels'
    if t.startswith('DEGELS'):return 'degels'
    if t.startswith('ANNULATIONS') and 'RESERVE' in t:return 'cancellations'
    if t.startswith('RESERVE DISPONIBLE AVANT'):return 'remaining'


def cents(text):
    text=text.replace('\u2212','-').replace('\u00a0',' ').replace(' ','')
    if not re.fullmatch(r'[+-]?\d+(?:,\d{1,2})?',text):raise ValueError(('not_monetary',text))
    return int(Decimal(text.replace(',','.'))*100)


def lines(page):
    return [dict(text=''.join(s['text'] for s in line['spans']).strip(),bbox=list(line['bbox']))
            for block in page.get_text('dict')['blocks'] for line in block.get('lines',[])]


def extract_tables(page, next_page=None):
    """Preserve blank columns; locate each number by printed header geometry."""
    ls=lines(page);words=page.get_text('words');out=[]
    anchors=[l for l in ls if field(l['text'])=='initial']
    for l in ls:l['page_offset']=0
    if next_page is not None:
        offset=page.rect.height
        for l in lines(next_page):
            l['bbox']=[l['bbox'][0],l['bbox'][1]+offset,l['bbox'][2],l['bbox'][3]+offset]
            l['page_offset']=1;ls.append(l)
        words += [(w[0],w[1]+offset,w[2],w[3]+offset,*w[4:]) for w in next_page.get_text('words')]
    for anchor in sorted(anchors,key=lambda l:l['bbox'][1]):
        y=anchor['bbox'][1]
        headers=[l for l in ls if y-80<l['bbox'][1]<y and norm(l['text']) in ('TITRE 2','AUTRES TITRES','TOTAL')]
        if not headers:
            out.append(dict(error='six_headers_missing',anchor=anchor));continue
        header_y=max(l['bbox'][1] for l in headers)
        headers=sorted((l for l in headers if abs(l['bbox'][1]-header_y)<3),key=lambda l:l['bbox'][0])
        if len(headers)!=6 or [norm(l['text']) for l in headers]!=['TITRE 2','AUTRES TITRES','TOTAL']*2:
            out.append(dict(error='six_headers_ambiguous',anchor=anchor,headers=headers));continue
        centers=[(l['bbox'][0]+l['bbox'][2])/2 for l in headers]
        boundaries=[(a+b)/2 for a,b in zip(centers,centers[1:])]
        left=centers[0]-(centers[1]-centers[0])/2
        limit=page.rect.height+(250 if y>page.rect.height-150 and next_page is not None else 0)
        next_initial=min((l['bbox'][1] for l in ls if field(l['text'])=='initial' and l['bbox'][1]>y+3),default=limit)
        next_initial=min(next_initial,limit)
        remaining=sorted((l for l in ls if field(l['text'])=='remaining' and y<l['bbox'][1]<next_initial),key=lambda l:l['bbox'][1])
        if not remaining:
            out.append(dict(error='remaining_row_missing',anchor=anchor));continue
        end=remaining[0]['bbox'][1]
        labels=sorted((l for l in ls if y-1<=l['bbox'][1]<=end+1 and l['bbox'][0]<left and field(l['text'])),key=lambda l:l['bbox'][1])
        extracted={};proofs={};failure=None
        for label in labels:
            key=field(label['text']);yc=(label['bbox'][1]+label['bbox'][3])/2
            row_headers=headers
            if label['page_offset']:
                preceding=[l for l in ls if l['page_offset']==label['page_offset'] and l['bbox'][1]<label['bbox'][1] and norm(l['text']) in ('TITRE 2','AUTRES TITRES','TOTAL')]
                if not preceding:
                    failure='continuation_headers_missing';break
                hy=max(l['bbox'][1] for l in preceding)
                row_headers=sorted((l for l in preceding if abs(l['bbox'][1]-hy)<3),key=lambda l:l['bbox'][0])
                if len(row_headers)!=6 or [norm(l['text']) for l in row_headers]!=['TITRE 2','AUTRES TITRES','TOTAL']*2:
                    failure='continuation_headers_ambiguous';break
            row_centers=[(l['bbox'][0]+l['bbox'][2])/2 for l in row_headers]
            row_boundaries=[(a+b)/2 for a,b in zip(row_centers,row_centers[1:])]
            row_left=row_centers[0]-(row_centers[1]-row_centers[0])/2
            if key in extracted:
                failure='duplicate_field';break
            buckets=[[] for _ in range(6)]
            for word in words:
                wx=(word[0]+word[2])/2;wy=(word[1]+word[3])/2
                if wx<row_left or abs(wy-yc)>3:continue
                j=sum(wx>b for b in row_boundaries);buckets[j].append(word)
            values=[];cellproof=[]
            try:
                for bucket in buckets:
                    bucket.sort(key=lambda w:w[0]);raw=' '.join(w[4] for w in bucket)
                    values.append(cents(raw) if bucket else None)
                    box=[min(w[0] for w in bucket),min(w[1] for w in bucket),max(w[2] for w in bucket),max(w[3] for w in bucket)] if bucket else None
                    cellproof.append(dict(raw_text=raw if bucket else None,bbox=box))
            except ValueError:
                failure='unrecognized_numeric_cell';break
            offset=label['page_offset']*page.rect.height
            def localbox(box):return [box[0],box[1]-offset,box[2],box[3]-offset] if box else None
            for proof in cellproof:proof['bbox']=localbox(proof['bbox'])
            extracted[key]=values;proofs[key]=dict(label=label['text'],label_bbox=localbox(label['bbox']),page_offset=label['page_offset'],cells=cellproof)
        if failure or not {'initial','surgels','degels','remaining'}<=extracted.keys():
            out.append(dict(error=failure or 'required_rows_missing',anchor=anchor,fields=list(extracted)));continue
        out.append(dict(values=extracted,proofs=proofs,headers=headers,anchor=anchor))
    return out


def checked_records(table,base):
    rows=[]
    for measure,offset in [('AE',0),('CP',3)]:
        cells={key:dict(zip(COLUMNS,vals[offset:offset+3])) for key,vals in table['values'].items()}
        if all(v is None for c in cells.values() for v in c.values()):
            continue  # Entire measure is blank in the PDF: no invented zero observation.
        checks=[]
        for key,c in cells.items():
            if c['total_cents'] is None:raise ValueError(('printed_total_blank',key,measure))
            delta=c['total_cents']-sum(c[k] or 0 for k in COLUMNS[:2])
            checks.append(dict(check='printed_columns',field=key,difference_cents=delta,passed=delta==0,
                accepted=abs(delta)<=AUTOMATIC_DIFFERENCE_LIMIT_CENTS,blank_title2_preserved=c['title2_cents'] is None))
        for col in COLUMNS:
            if any(c[col] is None for c in cells.values()):
                checks.append(dict(check='printed_balance',field=col,difference_cents=None,passed=False,accepted=None,status='blank_column_preserved'))
                continue
            delta=cells['remaining'][col]-sum(c[col] for k,c in cells.items() if k!='remaining')
            checks.append(dict(check='printed_balance',field=col,difference_cents=delta,passed=delta==0,
                accepted=abs(delta)<=AUTOMATIC_DIFFERENCE_LIMIT_CENTS))
        differences=[c for c in checks if c['difference_cents'] not in (0,None)]
        rejected=any(c['accepted'] is False for c in checks)
        largest=max((abs(c['difference_cents']) for c in differences),default=0)
        note="Tableau RAP publié au niveau du programme ; aucune ventilation par action ou dispositif déduite."
        if differences:
            note+=f" Écart arithmétique imprimé maximal de {largest/100:.2f} € ; les montants publiés sont conservés sans correction."
        if rejected:note+=" Analyse requise avant validation : écart supérieur à 10 €."
        rows.append(dict(**base,measure=measure,cells=cells,checks=checks,
            raw_lines={k:p['label']+' | '+' | '.join(c['raw_text'] if c['raw_text'] is not None else '[vide]' for c in p['cells']) for k,p in table['proofs'].items()},
            source_geometry=table['proofs'],headers=table['headers'],
            field_pages={k:base['page']+table['proofs'][k]['page_offset'] for k in cells},context_pages=sorted({base['page']+p['page_offset'] for p in table['proofs'].values()}),
            remaining_label='Réserve disponible avant mise en place du schéma de fin de gestion',
            numeric_validation='requires_investigation' if rejected else 'published_with_balance_difference' if differences else 'published_columns_and_balance_reconciled',
            review_required=rejected,note=note))
    return rows


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=ROOT/'reports/reserves-correction-20260923')
    args=ap.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    scan=json.loads((ROOT/'reports/historique-2017-2022/reserves-scan-candidates.json').read_text(encoding='utf-8'))
    db=sqlite3.connect((ROOT/'reports/historique-2017-2022/budget-opened-staged.sqlite').as_uri()+'?mode=ro',uri=True)
    sources={};maps=collections.defaultdict(list)
    for sid,raw in db.execute('SELECT id,data FROM sources'):
        source=json.loads(raw);sources[source.get('sha256')]=(sid,source)
    for row in db.execute("SELECT DISTINCT year,program,mission,program_label FROM facts WHERE budget='BG' AND year BETWEEN 2017 AND 2022"):
        maps[row[:2]].append(row[2:])
    records={};gaps=[];all_sources={};counts=collections.Counter()
    for item in scan['items']:
        if not item.get('hits'):continue
        key=(item['year'],str(item.get('program') or ''));poss=maps[key]
        if len({v[0] for v in poss})!=1:
            gaps.append(dict(year=key[0],program=key[1],reason='canonical_mapping_unresolved',path=item['path']));continue
        source_pair=sources.get(item['source'])
        if source_pair is None:
            gaps.append(dict(year=key[0],program=key[1],reason='source_missing'));continue
        sid,source=source_pair;path=ROOT/item['path']
        sha=hashlib.sha256(path.read_bytes()).hexdigest()
        if sha!=source['sha256']:raise ValueError(('sha_mismatch',str(path)))
        counts['pdf_checked']+=1
        with fitz.open(path) as doc:
            for number in sorted({hit['page'] for hit in item['hits']}):
                counts['pages_checked']+=1
                for table in extract_tables(doc[number-1],doc[number] if number<len(doc) else None):
                    base=dict(year=key[0],program=key[1],budget='BG',mission=poss[0][0],program_label=poss[0][1],source=sid,source_sha256=sha,page=number)
                    if table.get('error'):
                        gaps.append(dict(**base,reason=table['error'],details=table));continue
                    try:rows=checked_records(table,base)
                    except ValueError as exc:
                        gaps.append(dict(**base,reason='invalid_table',detail=str(exc)));continue
                    for row in rows:
                        k=(row['year'],row['mission'],row['program'],row['measure'])
                        if k in records:
                            if records[k]['cells']!=row['cells']:
                                gaps.append(dict(**base,measure=row['measure'],reason='conflicting_tables',earlier=records[k]['page']))
                                records[k]['review_required']=True;records[k]['numeric_validation']='requires_investigation'
                            else:counts['identical_duplicate_tables']+=1
                            continue
                        records[k]=row
                    all_sources[sid]=dict(id=sid,sha256=sha,title=source.get('title',''),path=source.get('path'),url=source.get('url'))
    old=json.loads((ROOT/'budget_service/data/reserves-historique-2017-2022.json').read_text(encoding='utf-8'))
    old_rows={(r['year'],r['mission'],r['program'],r['measure']):r for r in old['records']}
    diffs=[]
    for key,row in records.items():
        before=old_rows.get(key)
        if not before:
            diffs.append(dict(key=key,kind='new_table'));continue
        for fld,c in row['cells'].items():
            if before['cells'].get(fld)!=c:
                diffs.append(dict(key=key,field=fld,before=before['cells'].get(fld),after=c,source=row['source'],page=row['page']))
    missing=[dict(key=k,source=r['source'],page=r['page']) for k,r in old_rows.items() if k not in records]
    rows=list(records.values())
    summary=dict(counts,records=len(rows),tables=len({(r['year'],r['mission'],r['program']) for r in rows}),
        qualified_for_promotion=sum(not r['review_required'] for r in rows),needs_review=sum(r['review_required'] for r in rows),
        rows_with_cancellations=sum('cancellations' in r['cells'] for r in rows),gaps=len(gaps),
        changed_fields=len(diffs),old_records_not_recovered=len(missing),gap_reasons=dict(collections.Counter(g['reason'] for g in gaps)))
    result=dict(updated_at='2026-09-23',coverage='Réserves historiques : lignes imprimées, annulations et soldes contrôlés ; écarts supérieurs à 10 € à analyser.',field_labels=list(FIELDS),sources=list(all_sources.values()),records=rows,checks=[],notes=['Les blancs sont conservés. Les PDF ne sont pas modifiés.'],summary=summary)
    for name,obj in [('candidates.json',result),('gaps.json',gaps),('changes.json',diffs),('old-not-recovered.json',missing),('summary.json',summary)]:
        (args.output/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
