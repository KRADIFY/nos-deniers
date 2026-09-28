import collections,hashlib,json,sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/integration-classeurs-20260928';OUT.mkdir(parents=True,exist_ok=True)
DB=ROOT/'reports/release-20260924-working/data/derived/budget.sqlite'
db=sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
sources={r['id']:json.loads(r['data']) for r in db.execute('select * from sources')}
seen={};summary=collections.Counter();conflicts=[];pending=[];reclass=[];needed={};allrows=[]
for n in (10,11):
    folder=ROOT/f'outputs/verification-classeur{n}-20260928';audit=json.loads((folder/'audit_results.json').read_text('utf-8'))
    supplied=Path.home()/'Downloads'/f'Nos Deniers - Verification de Classeur{n} - 28 septembre 2026.xlsx'
    assert supplied.read_bytes()==(folder/supplied.name).read_bytes()
    catalog=json.loads((folder/'sources.json').read_text('utf-8'))
    if isinstance(catalog,list):catalog={s['id']:s for s in catalog}
    for r in audit['rows']:
        r=dict(r,workbook=n);allrows.append(r)
        for proof in r['proofs']:
            sid=proof['source_id'];record=sources.get(sid) or catalog.get(sid)
            if record:assert record['sha256']==proof['sha256'],sid
            needed[sid]=dict(record=record,registered=sid in sources,proof=proof,workbook=n)
        if r['status']=='À confirmer':pending.append(r);continue
        if r['status'] in ('Absent du PLF initial','Périmètre à reclasser'):reclass.append(r);continue
        for measure in r['measures']:
            value=r[measure];assert isinstance(value,(int,float)),r
            key=(r['year'],r['stage'],measure,r['budget'],*r['path'].split('/'))
            summary['numeric_cells']+=1
            if key in seen:
                summary['duplicates']+=1
                if seen[key]!=value:conflicts.append(dict(key=key,duplicate=True,values=[seen[key],value]))
            seen[key]=value
            existing=[dict(x) for x in db.execute('select * from facts where year=? and stage=? and measure=? and budget=? and mission=? and program=?',key)]
            if existing:summary['already_has_rows']+=1;conflicts.append(dict(key=key,wanted=value,existing=existing))
            else:summary['absent']+=1
    if n==10:print('CATALOGUE ANOMALIES',audit.get('catalogue_anomalies'))
code=json.loads((ROOT/'deploy/update-20260924-final/image-code-manifest.json').read_text('utf-8'))
drift=[]
for r in code['files']:
    path=ROOT/r['path']
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest()!=r['sha256']:drift.append(r['path'])
out=dict(database=str(DB),counts=dict(summary),conflicts=conflicts,reclass=reclass,pending=pending,needed=needed,code_drift=drift,rows=allrows)
(OUT/'inventory.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),'utf-8')
print('COUNTS',summary,'code drift',drift)
print('NEW SOURCES',[(sid,d['proof']['title'],bool(d['record'])) for sid,d in needed.items() if not d['registered']])
print('CONFLICTS',json.dumps(conflicts,ensure_ascii=False)[:4500])
print('RECLASS',[(r['year'],r['budget'],r['path'],r['stage'],r['measures'],r['explanation'][:70]) for r in reclass])
