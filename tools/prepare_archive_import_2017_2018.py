"""Archive the verified 2017-2018 downloads without trusting filename matches."""
import collections
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN = ROOT / 'reports/selenium-budget/scan-2017-2018-verification-20260909'
OUT = ROOT / 'reports/import-selenium-2017-2018-20260909'
OUT.mkdir(exist_ok=True)
source_manifest = ROOT / 'reports/MANIFEST-COLLECTE.json'
records = json.loads(source_manifest.read_text(encoding='utf-8'))
known = {r['sha256']: r for r in records}
original_hashes = set(known)
state = json.loads((SCAN / 'state.json').read_text(encoding='utf-8'))
now = datetime.now(timezone.utc).isoformat()
items, new, nominal = [], [], []
for url, item in state['documents'].items():
    if not item.get('local_path'):
        nominal.append({'url': url, 'status': item['status'], 'path': item.get('path'),
                        'sha256': item.get('sha256'), 'equivalence_confirmed_by_this_import': False})
        continue
    path = Path(item['local_path']).resolve()
    if not path.is_relative_to((SCAN / 'downloads').resolve()):
        raise ValueError('Unexpected incoming path')
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    if path.stat().st_size != item['bytes'] or sha != item['sha256']:
        raise ValueError('File changed after validation: ' + path.name)
    if item['format'] != 'pdf' or not item.get('pages'):
        raise ValueError('PDF validation evidence missing')
    record = known.get(sha)
    if record is None:
        match = re.search(r'/ressources/(2017|2018)/(lfi|pap|plr|rap)/', url)
        if match:
            year, stage = match.groups()
            stage = 'rap' if stage == 'plr' else stage
            years, basis = [year], 'official_resource_url'
            folder = year
        elif item['filename'] == 'Pstab_2016_2019_5p.pdf':
            years, stage, folder, basis = ['2016', '2017', '2018', '2019'], 'stabilite', '2016-2019', 'explicit_document_period'
        else:
            raise ValueError('Unreviewed exercise or stage: ' + url)
        stem = unicodedata.normalize('NFKD', Path(item['filename']).stem).encode('ascii', 'ignore').decode()
        stem = re.sub('[^A-Za-z0-9_-]+', '-', stem).strip('-')[:110]
        label = item.get('title') or Path(item['filename']).stem.replace('_', ' ')
        record = {
            'path': f'public/selenium/{stage}/{folder}/{stem}-{sha[:12]}.pdf',
            'title': f'{stage.upper()} {folder} — {label}',
            'years_title': years, 'format': 'pdf', 'role': 'official_document',
            'status': 'downloaded', 'checked_at': now, 'bytes': item['bytes'],
            'sha256': sha, 'pages': item['pages'],
            'text_extractable': bool(item.get('head_text', '').strip()),
            'text_validation_scope': 'first_three_pages_only',
            'original_filename': item['filename'],
            'provenance': 'Catalogue budget.gouv.fr, téléchargement Selenium et validation locale',
            'url': url, 'url_match': 'official_download_link',
            'source_pages': item.get('source_pages', []),
            'import_batch': 'selenium-2017-2018-20260909',
            'metadata_basis': basis, 'numeric_import': False,
        }
        records.append(record)
        new.append(record)
        known[sha] = record
        kind = 'new'
    else:
        kind = 'already_present' if sha in original_hashes else 'duplicate_in_batch'
    for key, value in [('collection_urls', url), ('collection_aliases', item['filename'])]:
        if value not in record.setdefault(key, []):
            record[key].append(value)
    items.append({'filename': path.relative_to(SCAN / 'downloads').as_posix(),
                  'path': record['path'], 'sha256': sha, 'bytes': item['bytes'], 'disposition': kind})

summary = {
    'dispositions': dict(collections.Counter(x['disposition'] for x in items)),
    'new_years': dict(collections.Counter(','.join(r['years_title']) for r in new)),
    'new_stages': dict(collections.Counter(r['path'].split('/')[2] for r in new)),
    'new_formats': dict(collections.Counter(r['format'] for r in new)),
    'new_pages': sum(r['pages'] for r in new),
    'new_bytes': sum(r['bytes'] for r in new),
    'old_sources': len(records) - len(new), 'new_sources': len(records),
    'reference_only_not_revalidated': len(nominal),
}
plan = {'at': now, 'base_manifest_sha256': hashlib.sha256(source_manifest.read_bytes()).hexdigest(),
        'items': items, 'new_records': new, 'summary': summary}
for filename, value in [('plan.json', plan), ('manifest-merged.json', records), ('references-not-revalidated.json', nominal)]:
    (OUT / filename).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False))
