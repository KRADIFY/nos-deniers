"""Promote the audited historical additions locally, preserving their predecessor."""
import hashlib,json,os,shutil,sqlite3
from pathlib import Path
from budget_service.data_signature import signature

stage=Path('/stage');root=Path('/data/derived')
source=stage/'stagehistorical-final.sqlite';target=root/'budget.sqlite'
expected_old='7bbdc2cca1279d008c73a4ff2c7b278af24df0a5663d332205d88ef3742fb113'
expected_new='88a132bd77a0868fbeb5f59c8147d827c2eeb25da2f5c562f1967bfd6bcaa931'

def sha(path):
    with path.open('rb')as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

audit=json.loads((stage/'data-audit.json').read_text('utf8'))
assert audit['success'] and audit['data_signature']==signature(source)
assert sha(source)==expected_new
with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)as db:
    assert db.execute('pragma integrity_check').fetchone()[0]=='ok'
    assert db.execute('select count(*)from facts').fetchone()[0]==audit['fact_count']==122747
assert audit['historical_canonical_facts']['facts']==366
old_hash=sha(target)
assert old_hash in (expected_old,expected_new),'Active database changed: recheck before promotion'
backup=root/'backups/audit-20260923-before-historical';backup.mkdir(parents=True,exist_ok=True)
previous=backup/'budget.sqlite'
if old_hash!=expected_new:
    if previous.exists():assert sha(previous)==expected_old
    else:shutil.copyfile(target,previous);previous.chmod(0o644)
    previous_audit=root/'data-audit.json'
    if previous_audit.exists()and not(backup/'data-audit.json').exists():
        shutil.copyfile(previous_audit,backup/'data-audit.json')
        (backup/'data-audit.json').chmod(0o644)
    pending=root/'budget-historical-audit-20260923.pending'
    shutil.copyfile(source,pending);pending.chmod(0o644)
    assert sha(pending)==expected_new
    os.replace(pending,target)
assert previous.exists()and sha(previous)==expected_old
pending=root/'data-audit-historical-20260923.pending'
shutil.copyfile(stage/'data-audit.json',pending);pending.chmod(0o644)
assert sha(pending)==sha(stage/'data-audit.json')
os.replace(pending,root/'data-audit.json')
receipt=dict(previous_database_sha256=expected_old,database_sha256=sha(target),
    certificate_sha256=sha(root/'data-audit.json'),backup=str(backup),public_modified=False)
(stage/'local-historical-database-promotion.json').write_text(json.dumps(receipt,indent=2),'utf8')
print(json.dumps(receipt))
