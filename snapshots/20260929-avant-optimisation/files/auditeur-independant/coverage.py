"""Read-only document-to-data audit, independent of website extractors.

Scope: catalog traceability for all files; direct PDF re-reading for the explicitly
listed historical annexes. Other documents remain unassessed, never 'complete'.
"""
import argparse,collections,datetime,hashlib,json,re,sqlite3,statistics,subprocess,unicodedata,xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path
from oracle import Reference

STAGES=('LFI','LEGIS','REPORT_ENTRANT','REGLEMENT','FDC','FONGIBILITE','OUVERT','EXEC','PLRG_OUVERTURE','PLRG_ANNULATION','REPORT_SORTANT')
STATUS={
 'matched':'Montant et case rapprochés de la source',
 'documented_pending':'Donnée repérée, non intégrée, écart documenté',
 'not_applicable':'Ancien programme hors périmètre après changement de nomenclature',
 'missing':'Donnée repérée, sans intégration ni justification',
 'different':'Divergence à qualifier entre la source et la base',
 'unmapped':'Programme publié non rattaché à la base',
 'ambiguous':'Plusieurs valeurs pour la même case',
}

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def normalized(s):return ''.join(c for c in unicodedata.normalize('NFKD',s).upper() if not unicodedata.combining(c))
def save(p,data):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),'utf-8');tmp.replace(p)
def lines(words):
    groups=[]
    for w in sorted(words,key=lambda w:(w['yMin'],w['xMin'])):
        if not groups or abs(groups[-1][0]-w['yMin'])>1.2:groups.append((w['yMin'],[w]))
        else:groups[-1][1].append(w)
    return [(y,sorted(ws,key=lambda w:w['xMin'])) for y,ws in groups]
def text(words):return ' '.join(w['text'] for w in words)
def numeric_cells(words,anchors=None):
    if anchors is not None:
        ws=sorted([w for w in words if re.fullmatch(r'-?\d[\d ,]*',w['text'])],key=lambda w:w['xMin'])
        groups=[];start=0
        for end in anchors:
            matches=[i for i,w in enumerate(ws) if i>=start and abs(w['xMax']-end)<1.5]
            if len(matches)!=1:raise ValueError('Fin de colonne ambiguë ou vide')
            stop=matches[0]+1;groups.append(ws[start:stop]);start=stop
        if start!=len(ws):raise ValueError('Nombre en dehors des colonnes')
    else:
        groups=[]
    for w in ([] if anchors is not None else sorted(words,key=lambda w:w['xMin'])):
        if not re.fullmatch(r'-?\d[\d ,]*',w['text']):continue
        if not groups or w['xMin']-groups[-1][-1]['xMax']>4:groups.append([w])
        else:groups[-1].append(w)
    output=[]
    for ws in groups:
        raw=text(ws)
        if not re.fullmatch(r'-?\d+(?: \d{3})*(?:,\d{2})?',raw):raise ValueError('Nombre ambigu : '+raw)
        output.append(dict(cents=int(Decimal(raw.replace(' ','').replace(',','.'))*100),raw=raw,bbox=[min(w['xMin'] for w in ws),min(w['yMin'] for w in ws),max(w['xMax'] for w in ws),max(w['yMax'] for w in ws)]))
    return output

def column_ends(words,start_x,min_y,allowed):
    candidates=collections.defaultdict(list)
    for y,ws in lines(words):
        if y<=min_y:continue
        try:
            a=numeric_cells([w for w in ws if w['xMin']>start_x])
            if len(a) in allowed:candidates[len(a)].append([v['bbox'][2] for v in a])
        except ValueError:pass
    if not candidates:raise ValueError('Colonnes non repérables indépendamment')
    n=max(candidates,key=lambda n:len(candidates[n]));sample=candidates[n]
    if len(sample)<3:raise ValueError('Pas assez de lignes pour repérer les colonnes')
    return [statistics.median(row[j] for row in sample) for j in range(n)]

def code_from_documented_title(source, page, label):
    # The 2017 annexe omits the printed code on two P190 rows. Its 2017 RAP
    # identifies this exact programme title and number independently.
    if (source['id']=='b53d0a4a0ba89d8680dd' and page in (25,41)
            and 'RECHERCHE DANS LES DOMAINES DE L' in normalized(label)):
        return '190'
    return None

def scan_annex(path,source):
    options={'creationflags':subprocess.CREATE_NO_WINDOW} if hasattr(subprocess,'CREATE_NO_WINDOW') else {}
    r=subprocess.run(['pdftotext','-bbox-layout',str(path),'-'],capture_output=True,check=True,timeout=120,**options)
    # PDF page-number glyphs sometimes contain XML-forbidden control characters.
    root=ET.fromstring(re.sub(rb'[\x00-\x08\x0b\x0c\x0e-\x1f]',b'',r.stdout))
    pages=[[dict(text=w.text or '',**{k:float(v) for k,v in w.attrib.items()}) for w in p.iter() if w.tag.endswith('}word')] for p in root.iter() if p.tag.endswith('}page')]
    rows=[];problems=[];table_pages=[];measure=None
    for i,words in enumerate(pages):
        header=normalized(text([w for w in words if w['yMin']<105]))
        if 'AUTORISATIONS' in header and 'ENGAGEMENT' in header:measure='AE'
        elif 'CREDITS DE PAIEMENT' in header:measure='CP'
        labels={w['text'] for w in words if w['yMin']<120}
        if not {'Programme','Titre','LFI','LFR'}.issubset(labels):continue
        table_pages.append(i+1)
        if measure is None:problems.append(dict(page=i+1,reason='AE/CP non démontré par un en-tête'));continue
        title_x=min(w['xMin'] for w in words if w['text']=='Titre')
        header_y=next(w['yMax'] for w in words if w['text']=='Programme')
        ends=column_ends(words,title_x+45,header_y,(3,11))
        right_ends=column_ends(pages[i+1],0,header_y,(8,)) if len(ends)==3 and i+1<len(pages) else None
        program=None;program_markers=0;totals=0;title_code=None
        for y,ws in lines(words):
            if y<=header_y:continue
            label=text([w for w in ws if w['xMin']<title_x])
            if inferred:=code_from_documented_title(source,i+1,label):title_code=inferred
            codes=[w['text'] for w in ws if w['xMin']<title_x and re.fullmatch(r'\d{3}',w['text'])]
            if len(codes)==1:program=codes[0];program_markers+=1
            elif len(codes)>1:program=None;problems.append(dict(page=i+1,reason='Plusieurs codes dans la colonne programme'))
            if label!='Total':continue
            totals+=1
            if program is None and title_code:
                program=title_code;program_markers+=1
            if program is None:problems.append(dict(page=i+1,reason='Ligne Total sans programme explicite'));continue
            try:
                amounts=numeric_cells([w for w in ws if w['xMin']>title_x+45],ends)
                loc=[i+1]*len(amounts)
                if len(amounts)==3 and i+1<len(pages):
                    other=numeric_cells([w for w in pages[i+1] if abs(w['yMin']-y)<1.2],right_ends);amounts+=other;loc += [i+2]*len(other)
                if len(amounts)!=11:raise ValueError(f'{len(amounts)} colonnes lisibles, 11 attendues')
                row=dict(source=source['id'],sha256=source['sha256'],year=source['year'],budget='BG',program=program,measure=measure,page=i+1,unit='EUR',cells={s:dict(a,page=p) for s,a,p in zip(STAGES,amounts,loc)})
                c=[a['cents'] for a in amounts]
                row['opening_gap_cents']=sum(c[:6])-c[6];row['closing_gap_cents']=c[6]+c[8]-c[7]-c[9]-c[10]
                rows.append(row)
            except Exception as e:problems.append(dict(page=i+1,program=program,measure=measure,reason=str(e)))
            program=None;title_code=None
        if program_markers!=totals:problems.append(dict(page=i+1,reason=f'{program_markers} programmes identifiés pour {totals} lignes Total'))
    if not table_pages:problems.append(dict(reason='Aucun tableau reconnu ; absence de résultat non assimilée à une absence de données'))
    duplicates=collections.Counter((r['year'],r['program'],r['measure']) for r in rows)
    for k,n in duplicates.items():
        if n>1:problems.append(dict(key=k,reason='Total de programme répété : rapprochement ambigu'))
    rows=[r for r in rows if duplicates[(r['year'],r['program'],r['measure'])]==1]
    return dict(source=source,table_pages=table_pages,rows=rows,problems=problems,pdf_pages=len(pages),reader='pdftotext -bbox-layout',scope='Totaux de programme AE/CP des tableaux LFI/LFR et gestion du budget général ; autres tableaux non certifiés')

def compare_rows(rows,facts,reviews):
    known=collections.defaultdict(list);reviewed=collections.defaultdict(list)
    for f in facts:
        if not f.get('action') and not f.get('subaction') and not f.get('category') and not f.get('title'):
            known[f['year'],f['budget'],f['program'],f['measure'],f['stage']].append(f)
    for r in reviews:reviewed[r['year'],r['budget'],r['path'].split('/')[-1],r['measure'],r['stage']].append(r)
    results=[]
    for row in rows:
        for stage,cell in row['cells'].items():
            key=(row['year'],row['budget'],row['program'],row['measure'],stage);found=known.get(key,[])
            proof=[r for r in reviewed.get(key,[]) if r.get('source_cents')==cell['cents'] and any(p.get('source_id')==row['source'] and p.get('sha256')==row['sha256'] for p in r.get('proofs',[]))]
            values=sorted({f['cents'] for f in found})
            if len(found)>1:status='ambiguous'
            elif values==[cell['cents']]:status='matched'
            elif proof and all(r.get('status')=='not_applicable' for r in proof) and cell['cents']==0:status='not_applicable'
            elif proof and all(r.get('status')=='pending' for r in proof):status='documented_pending'
            elif found:status='different'
            else:status='missing'
            results.append(dict(gap_cents=(values[0]-cell['cents']) if len(values)==1 and cell['cents'] is not None else None,gap_percent=(str(Decimal(values[0]-cell['cents'])/abs(Decimal(cell['cents']))*100) if len(values)==1 and cell['cents'] else None),year=row['year'],budget=row['budget'],program=row['program'],measure=row['measure'],stage=stage,status=status,expected_cents=cell['cents'],actual_cents=values,source=row['source'],sha256=row['sha256'],page=cell['page'],raw=cell['raw'],bbox=cell['bbox'],unit='EUR',opening_gap_cents=row['opening_gap_cents'],closing_gap_cents=row['closing_gap_cents'],explanation=' '.join(r.get('explanation','') for r in proof)))
    return results

def catalog_inventory(sources,facts,registries):
    counts=collections.Counter(f['source'] for f in facts);mentions=collections.defaultdict(set)
    def walk(v,name):
        if isinstance(v,dict):
            for k,x in v.items():
                if k in ('source','source_id') and isinstance(x,str):mentions[x].add(name)
                if isinstance(x,(dict,list)):walk(x,name)
        elif isinstance(v,list):
            for x in v:walk(x,name)
    for p in Path(registries).glob('*.json'):walk(json.loads(p.read_text('utf-8')),p.name)
    return [dict(source=s['id'],title=s.get('title',''),path=s.get('path',''),url=s.get('url',''),sha256=s.get('sha256',''),format=s.get('format',''),facts=counts[s['id']],registries=sorted(mentions[s['id']]),status='trace_dans_base' if counts[s['id']] else 'citation_dans_registre' if mentions[s['id']] else 'exploitation_non_demontree',meaning='Une trace ou citation ne prouve pas que tous les tableaux de ce document sont exploités.') for s in sources]

def run(reference,corpus_roots,out,config=None):
    reader_hash=sha(__file__)
    reference=Path(reference);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    config=Path(config) if config else Path(__file__).with_name('document-coverage.json')
    contract=json.loads(config.read_text('utf-8'));dbpath=reference/'budget.sqlite';dbsha=sha(dbpath)
    with sqlite3.connect(dbpath.resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row;facts=[dict(r) for r in db.execute('select * from facts')];sources=[json.loads(r['data']) for r in db.execute('select * from sources')]
        reviews=[dict(json.loads(r['data']),**{k:r[k] for k in ('year','stage','measure','budget','path')}) for r in db.execute('select * from cell_reviews')] if db.execute("select 1 from sqlite_master where name='cell_reviews'").fetchone() else []
    ref=Reference(reference)
    program_facts=[dict(year=y,budget=b,program=path.split('/')[1],measure=m,stage=stage,cents=cents,action='',subaction='',category='',title='',source='reference_aggregate') for (b,m,y,stage,path),cents in ref.amounts.items() if path.count('/')==1]
    catalog=catalog_inventory(sources,facts,reference/'registries');save(out/'catalogue-exploitation.json',catalog)
    byid={s['id']:s for s in sources};scans=[];issues=[]
    for source in contract['sources']:
        try:
            source=dict(source);source['path']=byid.get(source['id'],{}).get('path',source['path'])
            if source['id'] in byid and byid[source['id']].get('sha256')!=source['sha256']:raise ValueError('Empreinte du catalogue différente du document attendu')
            candidates=[Path(c)/source['path'] for c in corpus_roots]
            path=next((p for p in candidates if p.is_file()),None)
            if path is None:raise ValueError('Document attendu non accessible dans les racines montées')
            if not any(path.resolve().is_relative_to(Path(c).resolve()) for c in corpus_roots):raise ValueError('Chemin hors corpus')
            if sha(path)!=source['sha256']:raise ValueError('Empreinte du PDF différente')
            cache=out/'pages'/f"{source['id']}-{source['sha256'][:12]}-{reader_hash[:12]}.json"
            scan=json.loads(cache.read_text('utf-8')) if cache.exists() else scan_annex(path,source)
            if sha(path)!=source['sha256']:raise ValueError('PDF modifié pendant la relecture')
            if not cache.exists():save(cache,scan)
            scans.append(scan)
            issues.extend(dict(source=source['id'],**p) for p in scan['problems'])
            save(out/'progress.json',dict(done=len(scans),expected=len(contract['sources']),source=source['id']))
        except Exception as e:issues.append(dict(source=source['id'],reason=str(e)))
    cells=compare_rows([r for s in scans for r in s['rows']],program_facts,reviews)
    save(out/'cells.json',cells)
    bands=dict(collections.Counter('≤ 1 €' if abs(c['gap_cents'])<=100 else 'De 1 à 10 €' if abs(c['gap_cents'])<=1000 else '> 10 €' for c in cells if c['status']=='different'))
    counts=dict(collections.Counter(c['status'] for c in cells));inventory_counts=dict(collections.Counter(c['status'] for c in catalog))
    report=dict(at=datetime.datetime.now().astimezone().isoformat(),scope=contract['scope'],global_coverage_complete=False,database_sha256=dbsha,contract_sha256=sha(config),reader_sha256=reader_hash,documents_expected=len(contract['sources']),documents_read=len(scans),tables_pages=sum(len(s['table_pages']) for s in scans),programme_credit_rows=sum(len(s['rows']) for s in scans),cells=len(cells),counts=counts,difference_bands=bands,parse_issues=issues,catalog_documents=len(catalog),catalog_counts=inventory_counts,labels=STATUS,limits=['Le catalogue est contrôlé pour sa traçabilité, pas comparé à un catalogue officiel exhaustif.','La relecture indépendante des cellules couvre uniquement les six annexes 2017–2022 décrites dans le contrat.','Une citation, un téléchargement ou une vectorisation ne prouve pas une extraction complète.','Une divergence est conservée et ne modifie pas automatiquement les chiffres du site.'],read_only=True)
    if sha(__file__)!=reader_hash:raise ValueError('Lecteur modifié pendant le contrôle')
    if sha(dbpath)!=dbsha:raise ValueError('La référence a changé pendant le contrôle')
    save(out/'coverage.json',report)
    from coverage_report import write_report
    write_report(out,report,catalog,cells)
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--reference',required=True);p.add_argument('--corpus',action='append',required=True);p.add_argument('--output',required=True);a=p.parse_args();r=run(a.reference,a.corpus,a.output);print(json.dumps({k:r[k] for k in ('documents_read','programme_credit_rows','cells','counts','catalog_counts')},ensure_ascii=False));print('Lecture à vérifier :',len(r['parse_issues']))

