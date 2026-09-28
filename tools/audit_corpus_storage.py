"""Read-only, full SHA-256 inventory check for the budget Docker volume."""
import collections
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

records = json.loads(Path('/inputs/MANIFEST-COLLECTE.json').read_text())
topics = json.loads(Path('/app/budget_service/data/maprimerenov.json').read_text())['sources']
checks = []
for record in records + topics:
    path = Path(record['path'])
    if not path.is_absolute():
        path = Path('/data') / path
    row = {'path': str(path), 'ok': False}
    try:
        if not path.resolve().is_relative_to(Path('/data')):
            raise ValueError('Outside data volume')
        with path.open('rb') as stream:
            sha = hashlib.file_digest(stream, 'sha256').hexdigest()
        row.update(bytes=path.stat().st_size, sha256=sha)
        row['ok'] = sha == record['sha256'] and (record.get('bytes') is None or row['bytes'] == record['bytes'])
    except Exception as error:
        row['error'] = str(error)
    checks.append(row)
counter = collections.Counter(r.get('sha256') for r in checks if r['ok'])
print(json.dumps({
    'at': datetime.now(timezone.utc).isoformat(),
    'files': len(checks), 'valid': sum(r['ok'] for r in checks),
    'total_bytes': sum(r.get('bytes', 0) for r in checks),
    'unique_sha256': len(counter),
    'duplicate_sha256_groups': {key: value for key, value in counter.items() if value > 1},
    'formats': dict(collections.Counter(r.get('format') for r in records + topics)),
    'problems': [r for r in checks if not r['ok']],
}, ensure_ascii=False))
