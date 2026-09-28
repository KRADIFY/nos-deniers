"""Install only the new, hashed audit sources; never overwrite a different file."""
import hashlib,json,os,shutil
from pathlib import Path
stage=Path('/stage');root=Path('/data').resolve()
records=json.loads((stage/'added-sources.json').read_text('utf-8'))
for item in records:
    source=item['source'];path=source['path']
    assert path.startswith('public/audit-20260923/')
    original=stage/'added-data'/path;target=(root/path).resolve()
    assert target.is_relative_to(root/'public/audit-20260923')
    assert hashlib.sha256(original.read_bytes()).hexdigest()==source['sha256']
    if target.exists():
        assert hashlib.sha256(target.read_bytes()).hexdigest()==source['sha256']
        continue
    target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_suffix(target.suffix+'.pending')
    with temporary.open('xb') as out,original.open('rb') as incoming:shutil.copyfileobj(incoming,out)
    temporary.chmod(0o644)
    assert hashlib.sha256(temporary.read_bytes()).hexdigest()==source['sha256']
    os.replace(temporary,target)
print(json.dumps(dict(installed_or_verified=len(records),existing_documents_modified=False)))
