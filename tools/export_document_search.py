"""Create the sanitized, self-contained full-text index published by Nos Deniers."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit


VERSION = 'nos-deniers-document-search-1'
REQUIRED_SOURCE_TABLES = {
    'metadata', 'assets', 'refs', 'extraction', 'indexed', 'passages', 'occurrences',
    'asset_quality', 'source_precedence', 'passages_fts',
}


def read_db(path):
    target = Path(path).resolve()
    if not target.is_file():
        raise FileNotFoundError(target)
    db = sqlite3.connect(target.as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    return db


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def clean(value, limit=600):
    return re.sub(r'\s+', ' ', str(value or '')).strip()[:limit]


def safe_url(value):
    candidate = clean(value, 2000)
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return ''
    return candidate if parsed.scheme in {'http', 'https'} and parsed.netloc else ''


def json_object(value):
    try:
        result = json.loads(value) if isinstance(value, str) else value
    except (TypeError, json.JSONDecodeError):
        return {}
    return result if isinstance(result, dict) else {}


def budget_sources(path):
    by_sha, ids = {}, set()
    with closing(read_db(path)) as db:
        for row in db.execute('SELECT id,data FROM sources'):
            data = json_object(row['data'])
            ids.add(row['id'])
            sha = clean(data.get('sha256'), 64).lower()
            if re.fullmatch(r'[a-f0-9]{64}', sha):
                by_sha[sha] = dict(data, id=row['id'])
    return by_sha, ids


def first(meta, source, *keys):
    for key in keys:
        value = meta.get(key)
        if value not in (None, '', []):
            return value
        value = source.get(key)
        if value not in (None, '', []):
            return value
    return ''


def years_for(meta, source, title):
    values = []
    for key in ('years', 'years_title', 'exercise_years', 'source_years'):
        for container in (meta, source):
            value = container.get(key, [])
            values.extend(value if isinstance(value, list) else [value])
    years = set()
    for value in values:
        years.update(int(match) for match in re.findall(r'(?<!\d)(?:19|20)\d{2}(?!\d)', str(value)))
    if not years:
        years.update(int(match) for match in re.findall(r'(?<!\d)(?:19|20)\d{2}(?!\d)', title))
    return sorted(year for year in years if 1900 <= year <= 2100)


def stage_for(meta, source):
    explicit = first(meta, source, 'stage_documentaire', 'stage')
    if explicit:
        return clean(explicit, 80)
    probe = clean(first(meta, source, 'export_relative_path', 'relative_path'), 1000).lower()
    for marker, label in (
        ('plf-pap', 'PLF / PAP'), ('rap-plrg', 'RAP / PLRG'), ('/lfi/', 'LFI'),
        ('annulation', 'Annulation'), ('mouvement', 'Mouvement'), ('reserve', 'Réserve'),
    ):
        if marker in '/' + probe:
            return label
    return ''


def public_citation(metadata_json, asset_sha, locator, quality, local_by_sha, local_ids):
    meta = json_object(metadata_json)
    source = meta.get('source_metadata') if isinstance(meta.get('source_metadata'), dict) else {}
    local = local_by_sha.get(asset_sha, {})
    raw_id = clean(meta.get('id'), 80)
    source_id = local.get('id') or (raw_id if raw_id in local_ids else '')
    title = clean(first(meta, source, 'title', 'dataset_title', 'original_filename', 'filename'), 500)
    if not title:
        title = clean(local.get('title') or local.get('dataset_title'), 500)
    if not title:
        title = 'Document budgétaire'
    raw_url = first(meta, source, 'url', 'final_url') or local.get('url')
    if not raw_url:
        urls = source.get('collection_urls')
        raw_url = urls[0] if isinstance(urls, list) and urls else ''
    fmt = clean(first(meta, source, 'format') or local.get('format'), 16).lower()
    if not re.fullmatch(r'[a-z0-9]{1,16}', fmt):
        fmt = ''
    years = years_for(meta, source, title)
    return {
        'source_id': source_id,
        'title': title,
        'url': safe_url(raw_url),
        'locator': clean(locator, 120),
        'format': fmt,
        'years_key': '|' + '|'.join(str(year) for year in years) + '|' if years else '',
        'stage': stage_for(meta, source),
        'source_kind': clean(quality['source_kind'], 80),
        'table_layout': clean(quality['table_layout'], 80),
        'numeric_status': clean(quality['numeric_status'], 120),
        'local_available': 1 if source_id else 0,
    }


def create_search_db(source_path, budget_path, output_path, allow_partial=False):
    source_path, budget_path, output_path = map(Path, (source_path, budget_path, output_path))
    local_by_sha, local_ids = budget_sources(budget_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(output_path.name + f'.tmp-{os.getpid()}')
    if temporary.exists():
        temporary.unlink()
    try:
        with closing(read_db(source_path)) as source_db:
            tables = {row[0] for row in source_db.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
            missing = sorted(REQUIRED_SOURCE_TABLES - tables)
            if missing:
                raise ValueError('Index source inachevé : ' + ', '.join(missing))
            failures = source_db.execute('''
                SELECT count(*) FROM assets a
                LEFT JOIN extraction e ON e.asset_sha256=a.sha256
                WHERE a.policy='extract' AND (e.status IS NULL OR e.status!='complete')
            ''').fetchone()[0]
            if failures and not allow_partial:
                raise ValueError(f'Index source incomplet : {failures} extraction(s) non terminée(s)')
            remaining = source_db.execute('''
                SELECT count(*) FROM assets a
                LEFT JOIN extraction e ON e.asset_sha256=a.sha256
                LEFT JOIN indexed i ON i.asset_sha256=a.sha256
                WHERE a.policy='extract' AND (
                    i.asset_sha256 IS NULL OR i.shard_sha256 IS NOT e.shard_sha256
                )
            ''').fetchone()[0]
            if remaining and not allow_partial:
                raise ValueError(f'Index source incomplet : {remaining} document(s) non indexé(s) ou obsolète(s)')
            missing_quality = source_db.execute('''
                SELECT count(*) FROM assets a
                WHERE a.policy='extract'
                  AND EXISTS(SELECT 1 FROM refs r WHERE r.asset_sha256=a.sha256 AND r.partition='public')
                  AND NOT EXISTS(SELECT 1 FROM source_precedence s WHERE s.old_sha256=a.sha256)
                  AND NOT EXISTS(SELECT 1 FROM asset_quality q WHERE q.asset_sha256=a.sha256)
            ''').fetchone()[0]
            if missing_quality and not allow_partial:
                raise ValueError(f'Index source incomplet : {missing_quality} document(s) sans qualification de source')
            ready = not (failures or remaining or missing_quality)
            source_meta = dict(source_db.execute('SELECT key,value FROM metadata'))
            target = sqlite3.connect(temporary)
            try:
                target.executescript('''
                    PRAGMA journal_mode=DELETE;
                    PRAGMA synchronous=FULL;
                    CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                    CREATE TABLE passages(id TEXT PRIMARY KEY,text TEXT NOT NULL,tokens INTEGER NOT NULL);
                    CREATE TABLE citations(
                        id INTEGER PRIMARY KEY,
                        passage_id TEXT NOT NULL,
                        source_id TEXT NOT NULL,
                        title TEXT NOT NULL,
                        url TEXT NOT NULL,
                        locator TEXT NOT NULL,
                        format TEXT NOT NULL,
                        years_key TEXT NOT NULL,
                        stage TEXT NOT NULL,
                        source_kind TEXT NOT NULL,
                        table_layout TEXT NOT NULL,
                        numeric_status TEXT NOT NULL,
                        local_available INTEGER NOT NULL CHECK(local_available IN (0,1)),
                        FOREIGN KEY(passage_id) REFERENCES passages(id)
                    );
                    CREATE UNIQUE INDEX uq_citation ON citations(
                        passage_id,source_id,title,url,locator,format,years_key,stage
                    );
                    CREATE INDEX idx_citations_passage ON citations(passage_id);
                    CREATE INDEX idx_citations_format_year ON citations(format,years_key,passage_id);
                    CREATE VIRTUAL TABLE passages_fts USING fts5(
                        passage_id UNINDEXED,
                        text,
                        tokenize='unicode61 remove_diacritics 2'
                    );
                ''')
                passage_count = 0
                document_ids = set()
                rows = source_db.execute('''
                    SELECT p.id,p.text,p.tokens,o.asset_sha256,o.locator,r.metadata_json,
                           q.source_kind,q.table_layout,q.numeric_status
                      FROM passages p
                      JOIN occurrences o ON o.passage_id=p.id
                      JOIN refs r ON r.asset_sha256=o.asset_sha256 AND r.partition='public'
                      JOIN asset_quality q ON q.asset_sha256=o.asset_sha256
                     WHERE p.partition='public'
                       AND NOT EXISTS(
                           SELECT 1 FROM source_precedence s WHERE s.old_sha256=o.asset_sha256
                       )
                     ORDER BY p.id,o.asset_sha256,r.id,o.locator
                ''')
                current_id = None
                seen = set()
                for row in rows:
                    if row['id'] != current_id:
                        current_id = row['id']
                        seen = set()
                        target.execute('INSERT INTO passages VALUES(?,?,?)', (row['id'], row['text'], row['tokens']))
                        target.execute('INSERT INTO passages_fts VALUES(?,?)', (row['id'], row['text']))
                        passage_count += 1
                    quality = {key: row[key] for key in ('source_kind', 'table_layout', 'numeric_status')}
                    citation = public_citation(
                        row['metadata_json'], row['asset_sha256'], row['locator'], quality,
                        local_by_sha, local_ids,
                    )
                    signature = tuple(citation.values())
                    if signature in seen:
                        continue
                    seen.add(signature)
                    target.execute(
                        '''INSERT OR IGNORE INTO citations(
                               passage_id,source_id,title,url,locator,format,years_key,stage,
                               source_kind,table_layout,numeric_status,local_available
                           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (row['id'], *signature),
                    )
                    document_ids.add(row['asset_sha256'])
                generated_at = datetime.now(timezone.utc).isoformat()
                metadata = {
                    'version': VERSION,
                    'state': 'ready' if ready else 'partial',
                    'message': 'Recherche dans le texte intégral disponible.' if ready else 'Index partiel réservé aux contrôles ; publication indisponible.',
                    'coverage': 'Documents publics extraits ; résultats documentaires, sans agrégation automatique des montants.',
                    'generated_at': generated_at,
                    'document_count': str(len(document_ids)),
                    'passage_count': str(passage_count),
                    'extraction_failures': str(failures),
                    'remaining_documents': str(remaining),
                    'missing_source_quality': str(missing_quality),
                    'inventory_sha256': clean(source_meta.get('inventory_sha256'), 64),
                    'source_database_sha256': sha256_file(source_path),
                }
                target.executemany('INSERT INTO metadata VALUES(?,?)', metadata.items())
                target.execute('PRAGMA optimize')
                target.commit()
                check = target.execute('PRAGMA integrity_check').fetchone()[0]
                if check != 'ok':
                    raise ValueError('Échec du contrôle SQLite : ' + str(check))
            finally:
                target.close()
        os.replace(temporary, output_path)
        return {
            'output': str(output_path),
            'sha256': sha256_file(output_path),
            'documents': len(document_ids),
            'passages': passage_count,
            'source_extraction_failures': failures,
            'source_remaining_documents': remaining,
            'source_missing_quality': missing_quality,
        }
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--budget-db', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--allow-partial', action='store_true')
    args = parser.parse_args()
    result = create_search_db(args.source, args.budget_db, args.output, args.allow_partial)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
