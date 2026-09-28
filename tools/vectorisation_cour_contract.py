"""Raccord Cour en lecture seule et export facultatif séparé du lot GPU principal."""
from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time

ROOT = Path(__file__).resolve().parents[1]
CATALOGUE = Path('D:/LexMachine/NosDeniers/preparation_20260909/checkpoints/after_isolated_merge_20260911_094736.sqlite')
COUR_DATABASE = Path('E:/Marie AN 2026/ccomptes_chunks.sqlite')
OUTPUT = ROOT / 'reports/audit-vectorisation-20260911/cour-live-check/optional-reembedding-input'
HELD_ROUTE = 'existing_cour_pending_connection'
OPTIONAL_STATUS = 'optional_reembedding_input_not_authorized'


def read_only(path):
    path = Path(path).resolve()
    if not path.is_file() or path.stat().st_size < 100:
        raise ValueError('Database unavailable: ' + str(path))
    connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=3)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA query_only=ON')
    return connection


def valid_identity(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{40}', value):
        raise ValueError('An exact 40-character Cour identity is required')
    return value


def main_export_eligible(partition, route):
    return partition == 'public' and route == 'new_bge'


def generation_contract():
    return {'schema': 'nos-deniers-cour-routing/1',
            'main_export_partition': 'public', 'main_export_route': 'new_bge',
            'cour_route': HELD_ROUTE, 'cour_allowed_in_main_export': False,
            'cour_strategy_status': 'reuse_or_reembedding_not_validated',
            'optional_export_status': OPTIONAL_STATUS, 'paid_compute_authorized': False,
            'existing_402_documents': 'Identity/text/dense witnesses checked in historical copy; not a complete canonical-corpus verification.',
            'dense_model': 'BAAI/bge-m3', 'dense_dimension': 1024,
            'dense_model_revision_verified': False, 'sparse_verified': False,
            'local_catalogue_remains_searchable': True, 'delete_existing_vectors': False}


def resolve(document_id, chunk_ids, database=COUR_DATABASE, expected_source_sha256=None):
    """Hydrate exact IDs. A wrong parent blocks all text, never a global fallback."""
    document_id = valid_identity(document_id)
    chunk_ids = list(chunk_ids)
    if not 1 <= len(chunk_ids) <= 2000 or len(chunk_ids) != len(set(chunk_ids)):
        raise ValueError('Supply 1 to 2000 distinct exact chunk IDs')
    for chunk in chunk_ids:
        valid_identity(chunk)
    result = {'status': 'not_found', 'document_id': document_id, 'locked': True,
              'fallback_used': False, 'hits': [], 'missing_chunk_ids': [],
              'allow_automatic_numeric_fact': False, 'database': str(database)}
    with closing(read_only(database)) as connection:
        doc = connection.execute('SELECT * FROM docs WHERE doc=?', (document_id,)).fetchone()
        if doc is None:
            return result
        metadata = json.loads(doc['meta'] or '{}')
        source_sha = metadata.get('document_sha256')
        result.update(title=doc['title'], source_sha256=source_sha,
                      source_url=metadata.get('document_url') or metadata.get('page_url'))
        if expected_source_sha256 and source_sha != expected_source_sha256:
            result['status'] = 'source_identity_conflict'
            return result
        placeholders = ','.join('?' for _ in chunk_ids)
        rows = {row['id']: row for row in connection.execute(
            'SELECT id,doc,ord,text,page_start,page_end,token_count FROM chunks WHERE id IN (' + placeholders + ')', chunk_ids)}
        conflicts = [chunk for chunk in chunk_ids if chunk in rows and rows[chunk]['doc'] != document_id]
        if conflicts:
            result.update(status='parent_identity_conflict', conflicting_chunk_ids=conflicts)
            return result
        for chunk in chunk_ids:
            row = rows.get(chunk)
            if row is None:
                result['missing_chunk_ids'].append(chunk)
                continue
            result['hits'].append({'passage_id': chunk, 'document_id': document_id, 'ordinal': row['ord'],
                'text': row['text'], 'text_sha256': hashlib.sha256(row['text'].encode('utf8')).hexdigest(),
                'page_start': row['page_start'], 'page_end': row['page_end'], 'token_count': row['token_count'],
                'content_truncated': False, 'numeric_status': 'documentary_text_not_validated_budget_fact'})
        result['status'] = 'resolved' if not result['missing_chunk_ids'] else 'partially_resolved'
        return result


def search_document(document_id, query, database=COUR_DATABASE, limit=10):
    """FTS5 literal phrase confined to one exact parent; hydrate through resolve."""
    document_id = valid_identity(document_id)
    if not isinstance(query, str) or not query.strip() or len(query) > 400 or not 1 <= limit <= 20:
        raise ValueError('Short nonempty query and limit 1..20 required')
    fts_query = '"' + query.replace('"', '""') + '"'
    with closing(read_only(database)) as connection:
        if connection.execute('SELECT 1 FROM docs WHERE doc=?', (document_id,)).fetchone() is None:
            return {'status': 'not_found', 'document_id': document_id, 'locked': True, 'hits': [], 'fallback_used': False}
        ids = [row[0] for row in connection.execute('''
            SELECT c.id FROM chunks_fts JOIN chunks c ON c.rowid=chunks_fts.rowid
            WHERE chunks_fts MATCH ? AND c.doc=? ORDER BY bm25(chunks_fts) LIMIT ?''', (fts_query, document_id, limit))]
    if not ids:
        return {'status': 'no_matches', 'document_id': document_id, 'locked': True, 'hits': [], 'fallback_used': False}
    return resolve(document_id, ids, database)


def safe_output(output):
    output = Path(output).resolve()
    report_root = (ROOT / 'reports').resolve()
    if not output.is_relative_to(report_root) or output == report_root:
        raise ValueError('Optional output must stay under this project reports directory')
    return output


def export_optional(catalogue=CATALOGUE, output=OUTPUT):
    """Self-contained texts + all provenance, explicitly excluded from main export."""
    catalogue = Path(catalogue).resolve()
    output = safe_output(output)
    output.mkdir(parents=True, exist_ok=True)
    destination = output / 'cour.optional-reembedding.jsonl'
    receipt_path = output / 'contract.json'
    before = catalogue.stat()
    fingerprint = {'path': str(catalogue), 'bytes': before.st_size, 'mtime_ns': before.st_mtime_ns}
    if destination.exists() or receipt_path.exists():
        if not destination.is_file() or not receipt_path.is_file():
            raise ValueError('Incomplete previous export; preserve it and use a new directory')
        receipt = json.loads(receipt_path.read_text(encoding='utf8'))
        with destination.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if receipt.get('catalogue') != fingerprint or receipt.get('jsonl_sha256') != digest:
            raise ValueError('Existing export differs; preserve it and choose another output directory')
        return receipt
    connection = read_only(catalogue)
    try:
        expected = connection.execute('SELECT count(*),sum(tokens) FROM passages WHERE partition=? AND embedding_route=?', ('public', HELD_ROUTE)).fetchone()
        references = defaultdict(list)
        quality = {row['asset_sha256']: dict(row) for row in connection.execute('SELECT * FROM asset_quality')}
        external = {row['ref_id']: dict(row) for row in connection.execute('SELECT * FROM external_links')}
        for row in connection.execute('SELECT id,asset_sha256,metadata_json FROM refs WHERE partition=?', ('public',)):
            metadata = json.loads(row['metadata_json'])
            link = external.get(row['id'])
            references[row['asset_sha256']].append({'ref_id': row['id'], 'title': metadata.get('title'),
                'url': metadata.get('url'), 'source_page': metadata.get('source_page'),
                'relative_path': metadata.get('export_relative_path'), 'years': metadata.get('years'),
                'documentary_stage': metadata.get('stage_documentaire'),
                'cour_document_id': link['document_id'] if link else None,
                'external_verification': link['verification'] if link else None,
                'is_reconstructed_text': metadata.get('is_reconstructed_text', False)})
        temporary = destination.with_suffix(destination.suffix + '.partial')
        count = tokens = 0
        digest = hashlib.sha256()
        document_ids = set()
        source_assets = set()
        with temporary.open('wb') as stream:
            for passage in connection.execute('SELECT * FROM passages WHERE partition=? AND embedding_route=? ORDER BY id', ('public', HELD_ROUTE)):
                provenance = []
                for occurrence in connection.execute('SELECT * FROM occurrences WHERE passage_id=? ORDER BY id', (passage['id'],)):
                    asset = occurrence['asset_sha256']
                    source_assets.add(asset)
                    refs = references[asset]
                    document_ids.update(ref['cour_document_id'] for ref in refs if ref['cour_document_id'])
                    provenance.append({'occurrence_id': occurrence['id'], 'asset_sha256': asset,
                        'locator': occurrence['locator'], 'section': occurrence['section'], 'kind': occurrence['kind'],
                        'references': refs, 'quality': quality.get(asset, {
                            'table_layout': 'not_certified', 'numeric_status': 'not_validated_budget_fact',
                            'allow_automatic_numeric_fact': 0})})
                if not provenance:
                    raise ValueError('A held passage has no provenance: ' + passage['id'])
                record = {'schema': 'nos-deniers-cour-optional-input/1', 'id': passage['id'],
                    'partition': passage['partition'], 'embedding_route': passage['embedding_route'],
                    'status': OPTIONAL_STATUS, 'included_in_main_export': False,
                    'paid_compute_authorized': False, 'text': passage['text'],
                    'text_sha256': hashlib.sha256(passage['text'].encode('utf8')).hexdigest(),
                    'body_sha256': passage['body_sha256'], 'tokens': passage['tokens'],
                    'token_count_method': 'recorded_catalogue_token_count_not_retokenized',
                    'allow_automatic_numeric_fact': False, 'provenance': provenance}
                encoded = (json.dumps(record, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf8')
                stream.write(encoded)
                digest.update(encoded)
                count += 1
                tokens += passage['tokens']
                if count % 5000 == 0:
                    print(json.dumps({'phase': 'optional_export', 'passages': count, 'expected': expected[0]}), flush=True)
        after = catalogue.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('Catalogue changed during export; partial output not certified')
        if count != expected[0] or tokens != (expected[1] or 0):
            raise ValueError('Export counts differ from catalogue')
        receipt = dict(generation_contract(), catalogue=fingerprint, status=OPTIONAL_STATUS,
            created_at_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            passages=count, recorded_tokens=tokens, source_assets=len(source_assets),
            cour_document_ids=len(document_ids), jsonl_file=destination.name,
            jsonl_bytes=temporary.stat().st_size, jsonl_sha256=digest.hexdigest(),
            catalogue_routes_modified=False, source_modified=False, gpu_launched=False,
            old_vectors_removed=False, standalone_documentary_text_and_provenance=True)
        temporary.replace(destination)
        receipt_temp = receipt_path.with_suffix('.json.partial')
        receipt_temp.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
        receipt_temp.replace(receipt_path)
        return receipt
    finally:
        connection.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    export = commands.add_parser('export-optional')
    export.add_argument('--catalogue', type=Path, default=CATALOGUE)
    export.add_argument('--output', type=Path, default=OUTPUT)
    resolve_parser = commands.add_parser('resolve')
    resolve_parser.add_argument('--document-id', required=True)
    resolve_parser.add_argument('--chunk-id', action='append', required=True)
    resolve_parser.add_argument('--database', type=Path, default=COUR_DATABASE)
    search = commands.add_parser('search-document')
    search.add_argument('--document-id', required=True)
    search.add_argument('--query', required=True)
    search.add_argument('--database', type=Path, default=COUR_DATABASE)
    commands.add_parser('contract')
    args = parser.parse_args()
    if args.command == 'export-optional':
        result = export_optional(args.catalogue, args.output)
    elif args.command == 'resolve':
        result = resolve(args.document_id, args.chunk_id, args.database)
    elif args.command == 'search-document':
        result = search_document(args.document_id, args.query, args.database)
    else:
        result = generation_contract()
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
