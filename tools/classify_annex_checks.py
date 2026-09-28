"""Retain all independent findings; identify pre-existing issues without waivers."""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'auditeur-independant'))
from budget_service import api
from oracle import Reference, compare_cells
from tools.integrate_researched_annexes import OUT, BASE, read, dump

report = read(OUT / 'independent-oracle.json')
reference = Reference(ROOT / 'reports/integration-classeurs-20260928/independent-reference-final')
db = sqlite3.connect((BASE / 'derived/budget.sqlite').resolve().as_uri() + '?mode=ro', uri=True)
db.row_factory = sqlite3.Row
before = []
for scenario in report['checks']:
    if not scenario['errors']:
        continue
    p = scenario['parameters']
    result = compare_cells(reference, p, api.explorer(db, p))
    before.extend(result['errors'])
db.close()
serialize = lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False)
previous = {serialize(x) for x in before}
new = [e for e in report['errors'] if serialize(e) not in previous]
assert not new, new
assert len(before) == 2 and len(report['errors']) == 2
result = dict(new_integration_passed=True, full_audit_passed=False,
              numeric_cells=report['numeric_cells'], arithmetic_errors=0,
              preexisting_source_alerts=before, new_errors=new,
              meaning='Deux cellules MaPrimeRénov’ PR/2024 sont affichées à zéro sans source attachée dans la réponse de calcul ; même résultat avant le lot. Elles ne sont pas corrigées ni validées par cet import.',
              data_version=report['data_version'])
dump(OUT / 'independent-classification.json', result)
print(json.dumps(result, ensure_ascii=False))
