from pathlib import Path
import hashlib,json,urllib.request
stage=Path(__file__).resolve().parent
target=Path('/opt/nos-deniers/presentations/budget-refinements.css')
incoming=(stage/'updated.css').read_bytes()
expected=json.loads((stage/'before.json').read_text())['sha256']
digest=lambda data:hashlib.sha256(data).hexdigest()
old=target.read_bytes()
assert digest(old)==expected,'Concurrent stylesheet change'
backup=stage/'before.css'
assert not backup.exists(),'Backup already exists'
backup.write_bytes(old)
temporary=target.with_name('budget-refinements.cards-20261007.tmp')
assert not temporary.exists()
temporary.write_bytes(incoming)
temporary.chmod(target.stat().st_mode & 0o777)
temporary.replace(target)
try:
    served=urllib.request.urlopen('https://budget.lexmachine.net/presentation/budget-refinements.css?v=20261006',timeout=20).read()
    assert served==incoming,'Published CSS mismatch'
except BaseException:
    temporary.write_bytes(old);temporary.replace(target)
    raise
receipt=dict(published=True,file=str(target),backup=str(backup),before_sha256=expected,after_sha256=digest(incoming),only_summary_card_colours_changed=True)
(stage/'PUBLISHED.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps(receipt))
