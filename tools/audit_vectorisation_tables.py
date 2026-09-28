"""Inventory PDF page alerts and probe recovery without modifying the source corpus."""
from __future__ import annotations

import argparse
import collections
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import time

PREPARATION = Path('D:/LexMachine/NosDeniers/preparation_20260909')
SNAPSHOT = PREPARATION / 'checkpoints/after_isolated_merge_20260911_094736.sqlite'
OUTPUT = Path(__file__).resolve().parents[1] / 'reports/audit-vectorisation-20260911'
ALERT = 'grid_candidate_not_resolved'


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.partial')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def source_db():
    connection = sqlite3.connect(SNAPSHOT.as_uri() + '?mode=ro', uri=True, timeout=3)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA query_only=ON')
    return connection


def documents(connection):
    result = []
    for row in connection.execute('SELECT e.*,a.path FROM extraction e JOIN assets a ON a.sha256=e.asset_sha256 WHERE e.status=?', ('complete',)):
        receipt = json.loads(row['receipt_json'])
        count = receipt.get('issues', {}).get(ALERT, 0)
        if count:
            result.append(dict(sha=row['asset_sha256'], source_path=row['path'], expected_alerts=count,
                               shard_sha256=row['shard_sha256'], expected_pages=receipt['counts']['pages']))
    return result


def shard_path(sha):
    return PREPARATION / 'extracted' / sha[:2] / (sha + '.jsonl.gz')


def inventory(limit=0):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    source = source_db()
    selected = documents(source)
    target = sqlite3.connect(OUTPUT / 'page_inventory.sqlite')
    target.execute('PRAGMA synchronous=FULL')
    target.executescript('''
        CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS documents(sha TEXT PRIMARY KEY,source_path TEXT,shard_sha256 TEXT,
            pages INTEGER,expected_alerts INTEGER,actual_alerts INTEGER,completed_at REAL);
        CREATE TABLE IF NOT EXISTS pages(sha TEXT,page INTEGER,page_label TEXT,record_sha256 TEXT,
            words INTEGER,blocks INTEGER,text_characters INTEGER,digit_words INTEGER,
            PRIMARY KEY(sha,page));
    ''')
    contract = json.dumps({'snapshot': str(SNAPSHOT), 'size': SNAPSHOT.stat().st_size,
                           'mtime_ns': SNAPSHOT.stat().st_mtime_ns, 'alert': ALERT}, sort_keys=True)
    old = target.execute('SELECT value FROM metadata WHERE key=?', ('contract',)).fetchone()
    if old and old[0] != contract:
        raise ValueError('Inventory snapshot changed; preserve this inventory and use a new output directory.')
    target.execute('INSERT OR IGNORE INTO metadata VALUES(?,?)', ('contract', contract))
    target.commit()
    total_alerts = sum(item['expected_alerts'] for item in selected)
    errors = []
    done_this_run = 0
    started = time.monotonic()
    try:
        for item in selected:
            if target.execute('SELECT 1 FROM documents WHERE sha=?', (item['sha'],)).fetchone():
                continue
            if limit and done_this_run >= limit:
                break
            path = shard_path(item['sha'])
            try:
                with path.open('rb') as stream:
                    actual_sha = hashlib.file_digest(stream, 'sha256').hexdigest()
                if actual_sha != item['shard_sha256']:
                    raise ValueError('Shard changed since snapshot: ' + item['sha'])
                records = []
                page_count = 0
                with gzip.open(path, 'rt', encoding='utf-8') as stream:
                    for line in stream:
                        page = json.loads(line)
                        if page.get('kind') != 'page':
                            continue
                        page_count += 1
                        if ALERT not in page.get('issues', []):
                            continue
                        words = page.get('words', [])
                        text = '\n'.join(block['text'] for block in page.get('blocks', []))
                        records.append((item['sha'], page['page'], page.get('page_label'),
                            hashlib.sha256(line.encode('utf-8')).hexdigest(), len(words),
                            len(page.get('blocks', [])), len(text),
                            sum(any(character.isdigit() for character in str(word[4])) for word in words)))
                if len(records) != item['expected_alerts'] or page_count != item['expected_pages']:
                    raise ValueError('Receipt/page count mismatch: ' + item['sha'])
                with target:
                    target.executemany('INSERT INTO pages VALUES(?,?,?,?,?,?,?,?)', records)
                    target.execute('INSERT INTO documents VALUES(?,?,?,?,?,?,?)',
                        (item['sha'], item['source_path'], actual_sha, page_count,
                         item['expected_alerts'], len(records), time.time()))
                done_this_run += 1
            except Exception as exc:
                errors.append({'sha': item['sha'], 'error': str(exc)})
            if done_this_run % 25 == 0 or errors:
                progress = {'documents_complete': target.execute('SELECT count(*) FROM documents').fetchone()[0],
                    'documents_expected': len(selected), 'alerts_inventoried': target.execute('SELECT count(*) FROM pages').fetchone()[0],
                    'alerts_expected': total_alerts, 'errors': errors, 'elapsed_seconds': round(time.monotonic()-started, 1),
                    'source_modified': False, 'gpu_launched': False}
                dump(OUTPUT / 'inventory_status.json', progress)
                print(json.dumps(progress, ensure_ascii=False), flush=True)
        done = target.execute('SELECT count(*) FROM documents').fetchone()[0]
        pages = target.execute('SELECT count(*) FROM pages').fetchone()[0]
        report = {'complete': done == len(selected) and pages == total_alerts and not errors,
            'documents_complete': done, 'documents_expected': len(selected),
            'alerts_inventoried': pages, 'alerts_expected': total_alerts,
            'errors': errors, 'source_modified': False, 'gpu_launched': False,
            'scope': 'Inventory only; no table or financial certification',
            'elapsed_seconds': round(time.monotonic()-started, 1)}
        dump(OUTPUT / 'inventory_status.json', report)
        print(json.dumps(report, ensure_ascii=False), flush=True)
    finally:
        target.close()
        source.close()


def probe(sha, page_number):
    import fitz
    source = source_db()
    row = source.execute('SELECT path FROM assets WHERE sha256=?', (sha,)).fetchone()
    if row is None:
        raise ValueError('Unknown source')
    result = {'sha256': sha, 'source_path': row['path'], 'physical_page': page_number,
              'methods': {}, 'status': 'candidates_for_visual_review_only', 'automatic_numeric_fact': False}
    destination = OUTPUT / 'probes' / (sha[:12] + '-p' + str(page_number))
    destination.mkdir(parents=True, exist_ok=True)
    with fitz.open(row['path']) as document:
        page = document[page_number - 1]
        page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False).save(destination / 'page.png')
        result['native_words'] = len(page.get_text('words'))
        for strategy in ['lines_strict', 'lines', 'text']:
            start = time.monotonic()
            found = page.find_tables(strategy=strategy)
            result['methods'][strategy] = {'seconds': round(time.monotonic()-start, 3), 'tables': [
                {'bbox': list(table.bbox), 'rows': table.extract(),
                 'cells': [list(cell) if cell else None for cell in table.cells],
                 'header': {'names': table.header.names, 'external': table.header.external}}
                for table in found.tables]}
        result['region_candidates'] = []
        for bounds in page.cluster_drawings():
            if bounds.width < 80 or bounds.height < 20:
                continue
            clip = fitz.Rect(bounds)
            clip.x0 -= 1
            clip.y0 -= 1
            clip.x1 += 1
            clip.y1 += 1
            outer = [((bounds.x0, bounds.y0), (bounds.x1, bounds.y0)),
                     ((bounds.x0, bounds.y1), (bounds.x1, bounds.y1)),
                     ((bounds.x0, bounds.y0), (bounds.x0, bounds.y1)),
                     ((bounds.x1, bounds.y0), (bounds.x1, bounds.y1))]
            found = page.find_tables(strategy='lines', clip=clip, add_lines=outer)
            for table in found.tables:
                result['region_candidates'].append({'bbox': list(table.bbox), 'rows': table.extract(),
                    'cells': [list(cell) if cell else None for cell in table.cells],
                    'header': {'names': table.header.names, 'external': table.header.external},
                    'method': 'drawing_region_candidate_with_inferred_outer_border',
                    'numeric_certification': False})
    dump(destination / 'candidates.json', result)
    print(json.dumps({'directory': str(destination), 'methods': {key: len(value['tables']) for key, value in result['methods'].items()}}, ensure_ascii=False))
    source.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    inv = sub.add_parser('inventory')
    inv.add_argument('--limit', type=int, default=0)
    sample = sub.add_parser('probe')
    sample.add_argument('--sha', required=True)
    sample.add_argument('--page', required=True, type=int)
    args = parser.parse_args()
    if args.mode == 'inventory':
        inventory(args.limit)
    else:
        probe(args.sha, args.page)
