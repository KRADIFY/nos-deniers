"""Audit reprenable de la couverture PDF, sans modifier les sources ni produire de faits."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time
import unicodedata

from prepare_vectorisation_tables import replace_file_safely

PREPARATION = Path('D:/LexMachine/NosDeniers/preparation_20260909')
SNAPSHOT = PREPARATION / 'checkpoints/after_isolated_merge_20260911_094736.sqlite'
OUTPUT = Path(__file__).resolve().parents[1] / 'reports/audit-vectorisation-20260911'
VERSION = 'pdf-render-coverage-v2'
ALERT = 'grid_candidate_not_resolved'
NUMBER = re.compile(r'(?<!\w)[+\-−]?(?:\d{1,3}(?:[ \u00a0\u202f]\d{3})+|\d+)(?:[,.]\d+)?(?:[ \u00a0\u202f]*%)?')


def clean(value):
    return '' if value is None else unicodedata.normalize('NFC', str(value)).replace('\x00', '').strip()


def table_lines(table):
    """Reproduit prepare.table_lines pour les tables PDF (sans en-têtes de classeur)."""
    labels = table.get('header', {}).get('names') or []
    for number, row in enumerate(table['rows'], table.get('row_start', 1)):
        values = []
        for column, value in enumerate(row, 1):
            if value is None or value == '':
                continue
            label = clean(labels[column - 1]) if column <= len(labels) else ''
            rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')) if isinstance(value, (dict, list)) else str(value)
            values.append(f'Colonne {column}' + (f' [{label}]' if label else '') + ' : ' + rendered)
        if values:
            yield f'Ligne {number}. ' + ' | '.join(values)


def inside(block, table):
    a, b = block['bbox'], table['bbox']
    return a[0] >= b[0] - 1 and a[1] >= b[1] - 1 and a[2] <= b[2] + 1 and a[3] <= b[3] + 1


def numbers(texts):
    # Lexical comparison only: no float conversion, sum, scale or AE/CP inference.
    return Counter(re.sub(r'[ \u00a0\u202f]', '', match.group()).replace('−', '-')
                   for text in texts for match in NUMBER.finditer(clean(text)))


def words(texts):
    return Counter(word.casefold() for text in texts for word in re.findall(r'\w+', clean(text))
                   if any(c.isalpha() for c in word))


def content(table):
    # Values and the header labels actually injected in table_lines. Avoid generated
    # column/row numbers concealing a missing source number.
    labels = table.get('header', {}).get('names') or []
    result = []
    for row in table['rows']:
        for column, value in enumerate(row):
            if value is None or value == '':
                continue
            if column < len(labels):
                result.append(clean(labels[column]))
            result.append(clean(value))
    return result


def excerpt_missing(texts, missing, limit=3):
    result = []
    for text in texts:
        if numbers([text]) & missing:
            result.append(clean(text)[:1600])
            if len(result) >= limit:
                break
    return result


def inspect_page(record):
    tables = record.get('tables', [])
    blocks = record.get('blocks', [])
    removed = [block for block in blocks if any(inside(block, table) for table in tables)]
    retained = [block['text'] for block in blocks if not any(inside(block, table) for table in tables)]
    rendered_content = [text for table in tables for text in content(table)]
    # Retained blocks also count: a second copy still present on this page is not lost.
    raw_texts = [b['text'] for b in blocks]
    output_texts = retained + rendered_content
    missing_numbers = numbers(raw_texts) - numbers(output_texts)
    compact_output = [re.sub(r'\s', '', clean(text)).replace('−', '-') for text in output_texts]
    # A value may survive inside a merged AE/CP cell: ambiguity, not character loss.
    ambiguous_numbers = {value: count for value, count in missing_numbers.items()
                         if any(value in text for text in compact_output)}
    unlocated_numbers = {value: count for value, count in missing_numbers.items()
                         if value not in ambiguous_numbers}
    missing_words = words(raw_texts) - words(output_texts)
    header_words = {w: n for w, n in missing_words.items()
                    if w in {'ae', 'cp', 'autorisations', 'engagement', 'engagements',
                             'crédits', 'paiement', 'paiements', 'prévision', 'consommation',
                             'exécution', 'réalisation', 'total', 'lfi', 'plf'}}
    details = []
    collisions = 0
    for i, table in enumerate(tables, 1):
        table_blocks = [b['text'] for b in blocks if inside(b, table)]
        missing = numbers(table_blocks) - numbers(content(table))
        cell_boxes = Counter(tuple(cell) for cell in table.get('cells', []) if cell is not None)
        duplicated_boxes = [{'bbox': list(bbox), 'occurrences': n} for bbox, n in cell_boxes.items() if n > 1]
        collisions += sum(item['occurrences'] - 1 for item in duplicated_boxes)
        details.append({'table': i, 'bbox': table.get('bbox'), 'rows': len(table['rows']),
                        'row_widths': dict(Counter(len(row) for row in table['rows'])),
                        'null_cell_boxes': sum(cell is None for cell in table.get('cells', [])),
                        'duplicate_cell_boxes': duplicated_boxes[:12],
                        'missing_numbers_in_table': dict(missing),
                        'header': table.get('header'),
                        'rendered_sample': '\n'.join(table_lines(table))[:1800] if missing else None})
    unresolved = ALERT in record.get('issues', [])
    severity = 'chiffres_non_retrouves_dans_rendu' if unlocated_numbers else (
        'entetes_omis_du_rendu' if header_words else (
        'mots_omis_du_rendu' if missing_words else (
        'chiffres_presents_structure_ambigue' if ambiguous_numbers else (
        'geometrie_cellules_a_verifier' if collisions else (
        'structure_non_resolue' if unresolved else 'aucune_omission_detectee')))))
    return {'page': record['page'], 'page_label': record.get('page_label'),
            'issues': record.get('issues', []), 'method': record.get('method'),
            'blocks': len(blocks), 'words': len(record.get('words', [])), 'tables': len(tables),
            'blocks_removed_by_current_indexer': len(removed),
            'missing_numbers': dict(missing_numbers), 'missing_words': dict(missing_words),
            'unlocated_numbers': unlocated_numbers, 'ambiguous_numbers': ambiguous_numbers,
            'missing_header_words': header_words, 'duplicate_cell_boxes': collisions,
            'severity': severity, 'missing_number_source_samples': excerpt_missing(raw_texts, missing_numbers),
            'tables_detail': details, 'automatic_numeric_fact': False,
            'limitation': 'Couverture lexicale seulement ; une absence est à examiner. Une couverture complète ne valide pas les associations ligne/colonne/année/AE-CP.'}


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + '.partial')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    replace_file_safely(temporary, path)


def audit(snapshot=SNAPSHOT, preparation=PREPARATION, output=OUTPUT, only_sha=None, limit=0):
    snapshot, preparation, output = Path(snapshot), Path(preparation), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(snapshot.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
    source.row_factory = sqlite3.Row
    source.execute('PRAGMA query_only=ON')
    documents = []
    for row in source.execute('SELECT e.*,a.path FROM extraction e JOIN assets a ON a.sha256=e.asset_sha256 WHERE e.status=? ORDER BY e.asset_sha256', ('complete',)):
        receipt = json.loads(row['receipt_json'])
        pages = receipt.get('counts', {}).get('pages', 0)
        if pages:
            documents.append({'sha': row['asset_sha256'], 'path': row['path'], 'pages': pages,
                              'shard_sha256': row['shard_sha256'],
                              'expected_alerts': receipt.get('issues', {}).get(ALERT, 0)})
    target = sqlite3.connect(output / 'coverage.sqlite')
    target.execute('PRAGMA synchronous=FULL')
    target.executescript('''
        CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS documents(sha TEXT PRIMARY KEY,source_path TEXT,shard_sha256 TEXT,
            pages INTEGER,alerts INTEGER,completed_at REAL);
        CREATE TABLE IF NOT EXISTS pages(sha TEXT,page INTEGER,page_label TEXT,record_sha256 TEXT,
            tables_count INTEGER,alert INTEGER,severity TEXT,missing_number_count INTEGER,
            missing_word_count INTEGER,missing_header_count INTEGER,cell_collision_count INTEGER,numeric_ambiguity_count INTEGER,detail_json TEXT,
            PRIMARY KEY(sha,page));
        CREATE TABLE IF NOT EXISTS errors(sha TEXT PRIMARY KEY,error TEXT,at REAL);
    ''')
    contract = json.dumps({'version': VERSION, 'snapshot': str(snapshot.resolve()),
                          'snapshot_size': snapshot.stat().st_size, 'snapshot_mtime_ns': snapshot.stat().st_mtime_ns}, sort_keys=True)
    saved = target.execute("SELECT value FROM metadata WHERE key='contract'").fetchone()
    if saved and saved[0] != contract:
        raise ValueError('Snapshot/contrat modifié : conserver cet audit et employer un nouveau dossier de sortie.')
    target.execute('INSERT OR IGNORE INTO metadata VALUES(?,?)', ('contract', contract))
    target.commit()
    selected = [doc for doc in documents if not only_sha or doc['sha'] == only_sha]
    if only_sha and not selected:
        raise ValueError('Document absent du snapshot PDF')
    started = time.monotonic()
    processed = 0

    def status(current=None):
        done = target.execute('SELECT count(*) FROM documents').fetchone()[0]
        totals = target.execute('SELECT count(*),coalesce(sum(alert),0),coalesce(sum(missing_number_count>0),0),coalesce(sum(missing_header_count>0),0),coalesce(sum(numeric_ambiguity_count>0),0) FROM pages').fetchone()
        errors = [dict(sha=r[0], error=r[1]) for r in target.execute('SELECT sha,error FROM errors')]
        result = {'version': VERSION, 'complete': done == len(documents) and not errors,
                  'documents_complete': done, 'documents_expected': len(documents),
                  'pages_inventoried': totals[0], 'pages_expected': sum(d['pages'] for d in documents),
                  'alert_pages': totals[1], 'pages_with_missing_numbers': totals[2],
                  'pages_with_missing_headers': totals[3], 'errors': errors,
                  'pages_with_numeric_ambiguities': totals[4],
                  'current_document': current, 'elapsed_seconds': round(time.monotonic() - started, 1),
                  'source_modified': False, 'gpu_launched': False, 'automatic_numeric_fact': False,
                  'scope': 'Toutes les pages PDF ; chiffres omis, en-têtes, structure et géométrie. Un résultat sans omission ne certifie pas un tableau.'}
        atomic_json(output / 'status.json', result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return result

    try:
        for item in selected:
            sha = item['sha']
            existing = target.execute('SELECT shard_sha256 FROM documents WHERE sha=?', (sha,)).fetchone()
            if existing:
                if existing[0] != item['shard_sha256']:
                    raise ValueError('Empreinte de reprise incohérente : ' + sha)
                continue
            if limit and processed >= limit:
                break
            status(sha)
            shard = preparation / 'extracted' / sha[:2] / (sha + '.jsonl.gz')
            try:
                before = shard.stat()
                with shard.open('rb') as stream:
                    actual_sha = hashlib.file_digest(stream, 'sha256').hexdigest()
                if actual_sha != item['shard_sha256']:
                    raise ValueError('Shard différent du snapshot : ' + sha)
                seen, alerts = set(), 0
                with target:
                    with gzip.open(shard, 'rt', encoding='utf-8') as stream:
                        for line in stream:
                            record = json.loads(line)
                            if record.get('kind') != 'page':
                                continue
                            if record['page'] in seen:
                                raise ValueError('Page physique répétée : ' + str(record['page']))
                            seen.add(record['page'])
                            if record.get('page_count') != item['pages']:
                                raise ValueError('Nombre de pages interne divergent')
                            details = inspect_page(record)
                            alert = int(ALERT in record.get('issues', []))
                            alerts += alert
                            target.execute('INSERT INTO pages VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                                (sha, record['page'], record.get('page_label'), hashlib.sha256(line.encode('utf-8')).hexdigest(),
                                 details['tables'], alert, details['severity'], sum(details['unlocated_numbers'].values()),
                                 sum(details['missing_words'].values()), sum(details['missing_header_words'].values()),
                                 details['duplicate_cell_boxes'], sum(details['ambiguous_numbers'].values()), json.dumps(details, ensure_ascii=False, separators=(',', ':'))))
                    after = shard.stat()
                    if (after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns):
                        raise ValueError('Shard modifié durant sa lecture')
                    if seen != set(range(1, item['pages'] + 1)) or alerts != item['expected_alerts']:
                        raise ValueError('Couverture des pages ou alertes différente du reçu extraction')
                    target.execute('INSERT INTO documents VALUES(?,?,?,?,?,?)', (sha, item['path'], actual_sha, len(seen), alerts, time.time()))
                    target.execute('DELETE FROM errors WHERE sha=?', (sha,))
                processed += 1
            except Exception as exc:
                with target:
                    target.execute('INSERT OR REPLACE INTO errors VALUES(?,?,?)', (sha, str(exc), time.time()))
                status(sha)
        result = status()
        findings = target.execute('SELECT sha,page,severity,detail_json FROM pages WHERE missing_number_count>0 ORDER BY sha,page LIMIT 20').fetchall()
        report = dict(result, examples=[{'sha': r[0], 'page': r[1], 'severity': r[2],
                      'detail': json.loads(r[3])} for r in findings],
                      guidance='Ne pas supprimer les anciennes sources. Les montants signalés restent dans les blocs/mots du shard ; conserver ce texte et corriger la structure avant de créer le nouvel export vectoriel.')
        atomic_json(output / 'coverage_report.json', report)
        return result
    finally:
        target.close()
        source.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=SNAPSHOT)
    parser.add_argument('--preparation', type=Path, default=PREPARATION)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--sha')
    parser.add_argument('--limit', type=int, default=0)
    args = parser.parse_args()
    audit(args.snapshot, args.preparation, args.output, args.sha, args.limit)
