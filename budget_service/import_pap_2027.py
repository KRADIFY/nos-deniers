"""Add reviewed PLF 2027 figures without changing any historical observation."""
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

FIELDS='year stage measure budget mission mission_label program program_label action action_label subaction subaction_label category title cents source line field approximate'.split()
KEYS='year stage measure budget mission program action subaction'.split()

def digest_rows(db, last):
    value=hashlib.sha256()
    for row in db.execute('SELECT * FROM facts WHERE rowid<=? ORDER BY rowid',(last,)):
        value.update(json.dumps(tuple(row),ensure_ascii=False,separators=(',',':')).encode());value.update(b'\n')
    return value.hexdigest()

def validate(plan):
    if plan.get('version')!='pap-2027-reviewed-1':raise ValueError('Unknown 2027 plan')
    rows=plan['rows'];keys=set();sources={s['id']:s for s in plan['sources']}
    sums=defaultdict(int)
    for row in rows:
        key=tuple(row[k] for k in KEYS)
        if key in keys:raise ValueError('Duplicate financial cell')
        keys.add(key)
        if row['year']!=2027 or row['stage'] not in {'PLF','FDC_PREVU'} or row['measure'] not in {'AE','CP'} or row['budget'] not in {'BG','BA','CAS','CCF'}:raise ValueError('Invalid financial coordinates')
        if type(row['cents']) is not int or row['cents']<0 or row['cents']%100 or row['action'] or row['subaction']:raise ValueError('Invalid amount or grain')
        if row['source'] not in sources or type(row['line']) is not int or row['line']<=0 or row['approximate']!=0:raise ValueError('Missing exact source location')
        for path in ('',row['mission']):sums[(row['stage'],row['measure'],row['budget'],path)]+=row['cents']
    for item in plan['reconciled_totals']:
        if item['year']!=2027 or sums[(item['stage'],item['measure'],item['budget'],item['path'])]!=item['cents']:raise ValueError('Published total mismatch')
    if not all(c['passed'] for c in plan['checks']):raise ValueError('Unchecked source total')
    proofs={tuple(p['key']):p for p in plan['proofs']}
    for row in rows:
        proof=proofs.get(tuple(row[k] for k in KEYS[:6]))
        if not proof or proof['source_id']!=row['source'] or proof['physical_page']!=row['line'] or proof['explicit_zero']!=(row['cents']==0):raise ValueError('Unproved cell/zero')
        evidence=proof['evidence']
        if row['stage']=='PLF':printed=evidence.get('amount')
        elif 'fdc_euros' in evidence:printed=evidence['fdc_euros']
        elif 'values' in evidence:printed=evidence['values'].get('fdc_prevu_'+row['measure'].lower())
        else:printed=evidence.get(row['measure'].lower())
        if type(printed) is not int or printed*100!=row['cents']:raise ValueError('Amount differs from printed evidence')
    return rows

def install_copy(source_data, target_database, plan_path):
    source_data=Path(source_data).resolve();target_database=Path(target_database).resolve();plan_path=Path(plan_path)
    plan=json.loads(plan_path.read_text('utf-8'));rows=validate(plan)
    if target_database.exists():raise ValueError('Candidate already exists; inspect before replacing')
    original=source_data/'derived/budget.sqlite'
    db=sqlite3.connect(original.as_uri()+'?mode=ro',uri=True)
    if db.execute('SELECT count(*) FROM facts WHERE year=2027').fetchone()[0]:raise ValueError('2027 already present; review differences first')
    for source in plan['sources']:
        stored=db.execute('SELECT data FROM sources WHERE id=?',(source['id'],)).fetchone()
        if not stored:raise ValueError('Missing source')
        metadata=json.loads(stored[0]);path=(source_data/metadata['path']).resolve()
        if not path.is_relative_to(source_data) or metadata['sha256']!=source['sha256']:raise ValueError('Source identity mismatch')
        with path.open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest()!=source['sha256']:raise ValueError('Source content changed')
    count,last=db.execute('SELECT count(*),max(rowid) FROM facts').fetchone();before=digest_rows(db,last)
    meta={k:json.loads(v) for k,v in db.execute('SELECT key,value FROM meta')}
    target_database.parent.mkdir(parents=True,exist_ok=True)
    new=sqlite3.connect(target_database);db.backup(new)
    try:
        new.executemany('INSERT INTO facts('+','.join(FIELDS)+') VALUES('+','.join('?' for _ in FIELDS)+')',[tuple(r[k] for k in FIELDS) for r in rows])
        new.executemany('INSERT INTO reconciled_totals VALUES(?,?,?,?,?,?,?)',[tuple(r[k] for k in ['year','stage','measure','budget','path','cents','source']) for r in plan['reconciled_totals']])
        newly_used=0
        for s in plan['sources']:
            metadata=json.loads(new.execute('SELECT data FROM sources WHERE id=?',(s['id'],)).fetchone()[0])
            newly_used+=not metadata.get('imported',False);metadata['imported']=True
            metadata['checked_at']=s['checked_at']
            metadata['numeric_status']='reviewed_2027_cells_with_physical_proofs'
            new.execute('UPDATE sources SET data=? WHERE id=?',(json.dumps(metadata,ensure_ascii=False),s['id']))
        now=datetime.now(timezone.utc).isoformat();plan_sha=hashlib.sha256(plan_path.read_bytes()).hexdigest()
        updates=dict(fact_count=count+len(rows),built_at=now,data_version=hashlib.sha256((meta['data_version']+plan_sha).encode()).hexdigest(),imported_source_count=meta['imported_source_count']+newly_used,stats=dict(new.execute("SELECT year||'/'||stage||'/'||budget,count(*) FROM facts GROUP BY year,stage,budget")),pap2027=dict(plan_sha256=plan_sha,summary=plan['summary'],limits=plan['limitations'],source_precision='EUR',blank_is_zero=False))
        for k,v in updates.items():new.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',(k,json.dumps(v,ensure_ascii=False)))
        if digest_rows(new,last)!=before:raise ValueError('Historical facts changed')
        if new.execute('SELECT count(*) FROM facts').fetchone()[0]!=count+len(rows):raise ValueError('Fact count mismatch')
        new.commit()
        if new.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('SQLite integrity error')
        receipt=dict(passed=True,installed_at=now,source_database=str(original),candidate_database=str(target_database),previous_facts=count,added_facts=len(rows),candidate_facts=count+len(rows),previous_facts_sha256=before,old_facts_preserved=True,plan_sha256=plan_sha,public_site_modified=False)
    finally:new.close();db.close()
    receipt['candidate_sha256']=hashlib.sha256(target_database.read_bytes()).hexdigest()
    target_database.with_suffix('.receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return receipt
