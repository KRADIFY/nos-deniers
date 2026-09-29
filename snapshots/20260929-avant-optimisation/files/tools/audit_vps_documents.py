"""Read-only comparison of the active document catalogue with VPS files."""
import hashlib
import json
import sys
import urllib.request
from collections import Counter
from pathlib import Path

DEPLOYMENT = Path('/opt/lexmachine-budget/deployment.json')
deployment = json.loads(DEPLOYMENT.read_text(encoding='utf-8'))
data = (Path(deployment['release']) / 'data').resolve()
with urllib.request.urlopen('http://127.0.0.1:8552/api/documents?format=', timeout=60) as response:
    catalogue = json.load(response)
items = catalogue['items']
issues = []
status_counts = Counter()
checks = Counter()
total_bytes = 0
for number, entry in enumerate(items, 1):
    status_counts[str(entry.get('status', 'non précisé'))] += 1
    relative = entry.get('path')
    if not relative:
        checks['sans_chemin_local'] += 1
        continue
    path = (data / relative).resolve()
    if not path.is_relative_to(data):
        checks['chemin_invalide'] += 1
        issues.append({'id': entry.get('id'), 'title': entry.get('title'), 'path': relative, 'problem': 'chemin_invalide'})
        continue
    if not path.is_file():
        checks['fichier_absent'] += 1
        issues.append({'id': entry.get('id'), 'title': entry.get('title'), 'path': relative, 'status': entry.get('status'), 'url': entry.get('url'), 'problem': 'fichier_absent'})
        continue
    expected_bytes = entry.get('bytes')
    actual_bytes = path.stat().st_size
    total_bytes += actual_bytes
    if isinstance(expected_bytes, int) and expected_bytes != actual_bytes:
        checks['taille_differente'] += 1
        issues.append({'id': entry.get('id'), 'title': entry.get('title'), 'path': relative, 'problem': 'taille_differente', 'expected': expected_bytes, 'actual': actual_bytes})
        continue
    if entry.get('format') == 'pdf':
        with path.open('rb') as stream:
            if not stream.read(1024).lstrip().startswith(b'%PDF-'):
                checks['signature_pdf_invalide'] += 1
                issues.append({'id': entry.get('id'), 'title': entry.get('title'), 'path': relative, 'problem': 'signature_pdf_invalide'})
                continue
    expected_sha = entry.get('sha256')
    if isinstance(expected_sha, str) and len(expected_sha) == 64:
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        if digest.hexdigest() != expected_sha.lower():
            checks['empreinte_differente'] += 1
            issues.append({'id': entry.get('id'), 'title': entry.get('title'), 'path': relative, 'problem': 'empreinte_differente', 'expected': expected_sha, 'actual': digest.hexdigest()})
            continue
        checks['fichier_identique_au_catalogue'] += 1
    else:
        checks['fichier_present_sans_empreinte'] += 1
    if number % 500 == 0:
        print(f'{number}/{len(items)} références vérifiées', file=sys.stderr, flush=True)

print(json.dumps({
    'release': str(data),
    'catalogue_count': catalogue.get('count'),
    'items_examined': len(items),
    'catalogue_statuses': dict(status_counts),
    'checks': dict(checks),
    'bytes_read': total_bytes,
    'issues': issues,
}, ensure_ascii=False, indent=2))
