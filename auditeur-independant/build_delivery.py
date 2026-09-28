"""Package only the independent service and its targeted entry link."""
import hashlib,json,shutil,datetime
from pathlib import Path
source=Path(__file__).resolve().parent
target=source.parent/'deploy'/'audit-20260928'
files=['audit.py','oracle.py','management.py','zeros.py','document_zeros.py','document-zero-proofs.json','prepare_reference.py','service.py','zero_api.py','worker.py','browser.cjs','Dockerfile','.dockerignore','install.py','site_link.py',
 'test_auditeur.py','test_service.py','test_zeros.py','test_recovery.py','test_zero_api.py','test_document_zeros.py','test_install.py']
files += [p.relative_to(source).as_posix() for p in (source/'web').iterdir() if p.is_file()]
target.mkdir(parents=True,exist_ok=True)
for name in files:
 p=target/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/name,p)
manifest={name:hashlib.sha256((target/name).read_bytes()).hexdigest() for name in files}
(target/'FILES.json').write_text(json.dumps(manifest,indent=2),'utf-8')
(target/'READY.json').write_text(json.dumps(dict(at=datetime.datetime.now().astimezone().isoformat(),files=len(files),domain='auditnosdeniers.lexmachine.net',local_unit_tests=39,server_installation='sudo required',site_change='Navigation link only',data_modified=False),indent=2),'utf-8')
print(json.dumps(dict(folder=str(target),files=len(files),bytes=sum((target/n).stat().st_size for n in files))))
