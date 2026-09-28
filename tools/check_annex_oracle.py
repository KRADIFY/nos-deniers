"""Independent arithmetic against the local HTTP service, including new stages."""
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports/integration-annexes-20260928'
sys.path.insert(0, str(ROOT / 'auditeur-independant'))
from prepare_reference import prepare
from oracle import Reference, compare_cells

folder = OUT / 'independent-reference'
if not folder.exists():
    prepare(OUT / 'data/derived/budget.sqlite', ROOT / 'budget_service/data', folder)
ref = Reference(folder)
params = dict(start=2017, end=2026, budget='BG', measure='CP', scope='', exclude=[],
              constant=False, base=2025, topic='', topic_mode='only', denominator='LFI')
scenarios = [dict(params, budget=b, measure=m) for b in ('BG', 'BA', 'CAS', 'CCF') for m in ('AE', 'CP')]
scenarios += [dict(params, scope='TA', exclude=['TA/159']),
              dict(params, scope='TA', constant=True),
              dict(params, topic='maprimerenov'),
              dict(params, scope='TA', topic='maprimerenov', topic_mode='without')]
errors, checks, amounts = [], [], 0
for p in scenarios:
    query = dict(p, exclude=json.dumps(p['exclude']), constant=str(int(p['constant'])))
    with urllib.request.urlopen('http://127.0.0.1:8552/api/explorer?' + urllib.parse.urlencode(query), timeout=120) as response:
        data = json.load(response)
    assert data['data_version'] == ref.meta['data_version']
    result = compare_cells(ref, p, data)
    errors.extend(result['errors']); amounts += result['amounts']
    check = dict(parameters=p, amounts=result['amounts'], errors=len(result['errors']))
    checks.append(check)
    print(json.dumps(check, ensure_ascii=False), flush=True)
report = dict(passed=not errors, scenarios=len(checks), numeric_cells=amounts, errors=errors,
              checks=checks, data_version=ref.meta['data_version'])
(OUT / 'independent-oracle.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
print(json.dumps({k: v for k, v in report.items() if k != 'checks'}, ensure_ascii=False)[:4000])
assert not errors
