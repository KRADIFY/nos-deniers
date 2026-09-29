"""Compare the isolated optimized image with the exact active-image staging."""
import json
import subprocess
from urllib.parse import urlencode

HOST = 'root@5.189.145.254'


def check():
    cases = {
        'overview': ('/api/explorer', dict(start=2023, end=2025)),
        'history': ('/api/explorer', dict(start=2017, end=2022, measure='CP', budget='BG')),
        'inflation': ('/api/explorer', dict(start=2020, end=2022, measure='CP', budget='BG', constant='1', base=2025)),
        'exclusions': ('/api/explorer', dict(start=2023, end=2025, measure='CP', budget='BG', exclude='["TA/174"]')),
    }
    notices = [
        ('E01', 2020, 'AE', 'SB/176', 'EXEC'),
        ('E02', 2022, 'CP', 'CA/126', 'EXEC'),
        ('E03', 2022, 'AE', 'CA/126', 'EXEC'),
        ('E18', 2022, 'CP', 'EB/344', 'OUVERT'),
    ]
    for ident, year, measure, scope, stage in notices:
        cases[ident] = ('/api/provenance', dict(start=year, end=year, measure=measure,
                         budget='BG', scope=scope, year=year, stage=stage, cell_scope=scope))
    spec = json.dumps({key: path + '?' + urlencode(params) for key, (path, params) in cases.items()})
    remote = '''import json, urllib.request
cases = json.loads(%r)
for label, path in cases.items():
    replies = []
    for port in (8552, 8560):
        with urllib.request.urlopen('http://127.0.0.1:%%s%%s' %% (port, path), timeout=90) as response:
            replies.append(json.load(response))
    original, optimized = replies
    if label.startswith('E'):
        notice = optimized.pop('historical_discrepancy', None)
        if notice is None or notice['id'] != label:
            raise AssertionError((label, 'notice absente ou incorrecte'))
    if original != optimized:
        raise AssertionError((label, 'réponse chiffrée modifiée'))
    print(label, 'montants inchangés' + (' ; notice visible' if label.startswith('E') else ''), flush=True)
with urllib.request.urlopen('http://127.0.0.1:8560/', timeout=20) as response:
    html = response.read().decode()
assert 'id="request-elapsed"' in html
with urllib.request.urlopen('http://127.0.0.1:8560/assets/explorer.js', timeout=20) as response:
    javascript = response.read().decode()
assert "$('request-elapsed')" in javascript
print('Compteur orange présent', flush=True)
''' % spec
    subprocess.run(['ssh', '-o', 'BatchMode=yes', HOST, 'python3 -'], input=remote.encode(), check=True)


if __name__ == '__main__':
    check()
