"""Read-only audit of the site's numeric base and referenced source files."""
from pathlib import Path
import json,hashlib,sqlite3
from datetime import datetime,timezone
from collections import Counter
from budget_service import api,topics
from budget_service.normalize import read_table
from budget_service.audit_data import original_cents

def audit():
    db=api.connect(); failures=[]; warnings=[]
    report={'checked_at':datetime.now(timezone.utc).isoformat(),'scope':'Current numeric SQL base, registries and referenced physical sources; no automatic certification of vector passages'}
    report['integrity']=db.execute('PRAGMA integrity_check').fetchone()[0]
    if report['integrity']!='ok':failures.append('SQLite integrity')
    sources={r['id']:json.loads(r['data']) for r in db.execute('SELECT id,data FROM sources')}
    sources.update({s['id']:s for s in topics.sources()})
    used={r[0] for r in db.execute('SELECT DISTINCT source FROM facts')}
    pages=[];registries={}
    def walk(x):
        if isinstance(x,dict):
            if isinstance(x.get('source'),str):
                used.add(x['source'])
                if isinstance(x.get('page'),int):pages.append((x['source'],x['page']))
            for key,v in x.items():
                if key=='sources' and isinstance(v,list):
                    for e in v:
                        if isinstance(e,dict) and e.get('id'):used.add(e['id'])
                walk(v)
        elif isinstance(x,list):
            for v in x:walk(v)
    for path in (Path(api.__file__).parent/'data').glob('*.json'):
        data=json.loads(path.read_text(encoding='utf8'));walk(data)
        registries[path.name]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    verified=[]
    for sid in sorted(used):
        source=sources.get(sid)
        if not source:failures.append('Missing source '+sid);continue
        path=(api.DATA/source['path']).resolve()
        if not path.is_relative_to(api.DATA.resolve()) or not path.is_file():failures.append('Missing file '+sid);continue
        with path.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
        if actual!=source['sha256']:failures.append('Hash mismatch '+sid)
        verified.append({'id':sid,'sha256':actual,'bytes':path.stat().st_size})
    for sid,page in pages:
        count=sources.get(sid,{}).get('pages')
        if page<1 or (count and page>count):failures.append(f'Invalid page {sid}:{page}')
    invalid=db.execute("SELECT count(*) FROM facts WHERE typeof(cents)!='integer' OR measure NOT IN ('AE','CP') OR year NOT BETWEEN 2017 AND 2026 OR cents IS NULL").fetchone()[0]
    if invalid:failures.append(f'{invalid} invalid facts')
    coverage=[dict(r) for r in db.execute('SELECT year,stage,measure,budget,count(*) AS observations,count(DISTINCT mission) AS missions,count(DISTINCT program) AS programmes FROM facts GROUP BY year,stage,measure,budget')]
    reconciliations=[]
    for source in sources.values():
        name=source.get('title','')
        if name not in ('Annexe1-Etat_AE_CP-2024.csv','Annexe1-Etat_AE_CP-2025.csv'):continue
        year=int(name[-8:-4])
        for number,row in enumerate(read_table(source)[1:],2):
            for stage,measure,column in [('OUVERT','AE',1),('EXEC','AE',2),('OUVERT','CP',3),('EXEC','CP',4)]:
                expected=original_cents(row[column])
                actual=db.execute('SELECT sum(cents) FROM facts WHERE year=? AND stage=? AND measure=? AND budget=? AND mission_label=?',(year,stage,measure,'BG',row[0])).fetchone()[0]
                difference=None if actual is None else actual-expected
                if difference is None or abs(difference)>2:failures.append(f'Mission mismatch {year}:{row[0]}:{stage}:{measure}:{difference}')
                reconciliations.append(dict(year=year,mission=row[0],stage=stage,measure=measure,difference_cents=difference))
    if not reconciliations:failures.append('Missing independent mission control tables')
    meta=api.metadata(db)
    anomalies=Counter(i['kind'] for i in meta.get('issues',[]))
    material=[i for i in meta.get('issues',[]) if abs(i.get('difference_cents',0))>100]
    report.update(success=not failures,fact_count=db.execute('SELECT count(*) FROM facts').fetchone()[0],source_count=len(sources),source_hashes_verified=len(verified),source_files=verified,registry_hashes=registries,page_references_checked=len(pages),mission_reconciliations=reconciliations,coverage=coverage,failures=failures,warnings=warnings,known_source_issues=dict(anomalies),material_source_issues=material)
    db.close();return report

if __name__=='__main__':print(json.dumps(audit(),ensure_ascii=False,indent=2))