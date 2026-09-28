import json
from pathlib import Path
from oracle import Reference
from zeros import source_ledger
r=Reference(Path('references/20260924-final'))
out=Path('resultats/controle-zeros');out.mkdir(exist_ok=True)
print(json.dumps(source_ledger(r,Path('references/physical-sources'),out),ensure_ascii=False,indent=2))
