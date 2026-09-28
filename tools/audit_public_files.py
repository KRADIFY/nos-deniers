"""Read every public source file once; emit an inventory for reproducible delivery."""
import hashlib, json, sqlite3
from pathlib import Path
from budget_service import api, topics, events

def main():
    data=api.DATA.resolve()
    with api.connect() as db:
        records=[json.loads(r[0]) for r in db.execute('select data from sources')]+topics.sources()+events.sources(data)
    by_path={}; failures=[]; pdfs=0
    for r in records:
        p=(data/r['path']).resolve()
        if not p.is_relative_to(data) or not p.is_file():
            failures.append(dict(path=r['path'],reason='missing_or_outside_root'));continue
        size=p.stat().st_size
        with p.open('rb') as f:
            prefix=f.read(1024);f.seek(0);sha=hashlib.file_digest(f,'sha256').hexdigest()
        if sha!=r['sha256'] or size!=r['bytes']:
            failures.append(dict(path=r['path'],reason='hash_or_size_mismatch'))
        if r.get('format')=='pdf':
            pdfs+=1
            if b'%PDF-' not in prefix:failures.append(dict(path=r['path'],reason='invalid_pdf_header'))
        record=dict(path=r['path'],bytes=size,sha256=sha)
        if r['path'] in by_path:assert by_path[r['path']]==record
        by_path[r['path']]=record
    for name in ('budget.sqlite','events.sqlite','normalization-report.json','data-audit.json'):
        p=data/'derived'/name
        with p.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
        by_path['derived/'+name]=dict(path='derived/'+name,bytes=p.stat().st_size,sha256=sha)
    print(json.dumps(dict(success=not failures,failures=failures,pdf_headers_checked=pdfs,
        catalogue_records=len(records),files=list(by_path.values()),bytes=sum(r['bytes'] for r in by_path.values())),ensure_ascii=False))

if __name__=='__main__':main()
