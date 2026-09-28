"""Activate only an audited local database, retaining the previous exact bytes."""
import hashlib,json,os,shutil,sqlite3
from pathlib import Path
from budget_service.data_signature import signature
stage=Path('/stage');root=Path('/data/derived');source=stage/'budget.sqlite';target=root/'budget.sqlite'
def sha(p):
    with p.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
audit=json.loads((stage/'data-audit.json').read_text('utf-8'))
assert audit['success'] and audit['data_signature']==signature(source)
with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)as db:
    assert db.execute('pragma integrity_check').fetchone()[0]=='ok'
    assert db.execute('select count(*)from facts').fetchone()[0]==audit['fact_count']
old_hash=sha(target);new_hash=sha(source)
backup=root/'backups/audit-20260923-before';backup.mkdir(parents=True,exist_ok=True)
if old_hash!=new_hash:
    assert old_hash=='c2501c1bba6b95fdab0cb16ee050da93b240a13343dabba337bb4bb6027e5936','Active database changed: recheck before promotion'
    previous=backup/'budget.sqlite'
    if previous.exists():assert sha(previous)==old_hash
    else:shutil.copyfile(target,previous);previous.chmod(0o644)
    previous_audit=root/'data-audit.json'
    if previous_audit.exists()and not(backup/'data-audit.json').exists():shutil.copyfile(previous_audit,backup/'data-audit.json')
    pending=root/'budget-audit-20260923.pending'
    shutil.copyfile(source,pending);pending.chmod(0o644)
    assert sha(pending)==new_hash
    os.replace(pending,target)
pending=root/'data-audit-20260923.pending'
shutil.copyfile(stage/'data-audit.json',pending);pending.chmod(0o644)
os.replace(pending,root/'data-audit.json')
receipt=dict(previous_database_sha256=old_hash,database_sha256=sha(target),certificate_sha256=sha(root/'data-audit.json'),backup=str(backup),public_modified=False)
(stage/'local-database-promotion.json').write_text(json.dumps(receipt,indent=2),'utf-8')
print(json.dumps(receipt))
