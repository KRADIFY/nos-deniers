"""Validate files left in failed Selenium batches without deleting originals."""
import hashlib,json,sys,time,unicodedata
from collections import Counter
from pathlib import Path
from collect_budget_selenium import validate,digest,name_key,atomic_json

out=Path(sys.argv[1]).resolve()
state_path=out/'state.json'
original=state_path.read_bytes()
state=json.loads(original)
report={'started':time.strftime('%Y-%m-%dT%H:%M:%S'),'resolved':[],'unresolved':[]}
known={r['sha256']:r['path'] for r in json.loads((Path(__file__).resolve().parents[1]/'reports/MANIFEST-COLLECTE.json').read_text(encoding='utf-8')) if r.get('sha256')}
for item in state['documents'].values():
    if item.get('sha256') and item.get('local_path') and item['status'] in {'downloaded','duplicate'}:
        known.setdefault(item['sha256'],item['local_path'])
for url,item in state['documents'].items():
    if item['status']!='failed':continue
    folder=out/'downloads'/hashlib.sha256(url.encode()).hexdigest()[:16]
    files=sorted((p for p in folder.glob('*') if p.is_file() and not p.name.endswith(('.tmp','.crdownload'))),key=lambda p:(len(p.name),p.name))
    candidates=[p for p in files if name_key(p.name)==name_key(item['filename'])]
    if not candidates:
        fold=lambda value: unicodedata.normalize('NFKD',name_key(value)).encode('ascii','ignore').decode()
        candidates=[p for p in files if fold(p.name)==fold(item['filename'])]
    record={'url':url,'expected':item['filename'],'files':[p.name for p in files]}
    hashes={digest(p) for p in candidates}
    if not candidates or len(hashes)!=1:
        record['reason']='Expected filename absent or candidate contents differ'
        report['unresolved'].append(record);continue
    selected=candidates[0]
    try:
        details=validate(selected);sha=digest(selected)
        old_error=item.pop('error',None)
        item.update(details,status='duplicate' if sha in known else 'downloaded',local_path=str(selected),sha256=sha,bytes=selected.stat().st_size,reconciliation='Filename matched, identical candidate hashes, full validation',previous_error=old_error)
        if sha in known:item['duplicate_of']=known[sha]
        known.setdefault(sha,str(selected))
        record.update(sha256=sha,selected=selected.name,status=item['status'])
        report['resolved'].append(record)
    except Exception as error:
        record['reason']=str(error);report['unresolved'].append(record)
    atomic_json(out/'reconciliation-report.json',report)
    print('Validated',item['filename'],flush=True)
report['counts']=dict(Counter(item['status'] for item in state['documents'].values()))
atomic_json(out/'reconciliation-report.json',report)
atomic_json(out/'state-reconciled.json',state)
if '--apply' in sys.argv:
    if state_path.read_bytes()!=original:raise RuntimeError('State changed during reconciliation; no update applied')
    backup=out/('state-before-reconciliation-'+time.strftime('%Y%m%dT%H%M%S')+'.json')
    backup.write_bytes(original)
    atomic_json(state_path,state)
print(json.dumps({'resolved':len(report['resolved']),'unresolved':len(report['unresolved']),'counts':report['counts']}),flush=True)

