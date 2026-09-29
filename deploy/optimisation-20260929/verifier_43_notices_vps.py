"""Check every historical notice through the optimized HTTP service on the new VPS."""
import json
import subprocess
from pathlib import Path
from urllib.parse import urlencode

REGISTRY = Path(__file__).parents[2] / 'budget_service/data/historical_discrepancy_notices_2017_2022.json'


def main():
    entries = json.loads(REGISTRY.read_text(encoding='utf-8'))['entries']
    cases = []
    for row in entries:
        scope = row['mission'] + '/' + row['program']
        query = urlencode(dict(start=row['year'], end=row['year'], budget=row['budget'],
                               measure=row['measure'], scope=scope, cell_scope=scope,
                               year=row['year'], stage=row['stage']))
        cases.append(dict(id=row['id'], url='/api/provenance?' + query,
                          site_cents=row['site_cents'], other_cents=row['other_publication_cents']))
    remote = '''import concurrent.futures, json, urllib.request
cases = json.loads(%r)
ports = [8552, 8556, 8557, 8558]
def check(item):
    index, expected = item
    with urllib.request.urlopen('http://127.0.0.1:%%s%%s' %% (ports[index %% 4], expected['url']), timeout=90) as response:
        actual = json.load(response)['historical_discrepancy']
    if actual is None or any(actual[field] != expected[field] for field in ('id', 'site_cents')):
        raise AssertionError(expected['id'])
    if actual['other_publication_cents'] != expected['other_cents']:
        raise AssertionError(expected['id'] + ' comparaison')
    return expected['id']
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    verified = list(pool.map(check, enumerate(cases)))
print('Notices vérifiées sur le VPS :', len(verified), '/', len(cases), flush=True)
''' % json.dumps(cases)
    subprocess.run(['ssh', '-o', 'BatchMode=yes', 'root@5.189.145.254', 'python3 -'],
                   input=remote.encode(), check=True)


if __name__ == '__main__':
    main()
