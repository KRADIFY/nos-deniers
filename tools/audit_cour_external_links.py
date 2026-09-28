"""Contrôle en lecture seule des identités Cour et des vecteurs déjà existants."""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import struct
import time

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = Path('D:/LexMachine/NosDeniers/preparation_20260909/checkpoints/after_isolated_merge_20260911_094736.sqlite')
DATABASE = Path('E:/Marie AN 2026/ccomptes_chunks.sqlite')
CACHE = Path('E:/Marie AN 2026/semantic_cache_ccomptes')
OUTPUT = ROOT / 'reports/audit-vectorisation-20260911/cour-live-check'


def read_db(path, immutable=False):
    if not Path(path).is_file() or Path(path).stat().st_size < 100:
        raise ValueError('Base absente, vide ou répertoire : ' + str(path))
    c = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro' + ('&immutable=1' if immutable else ''), uri=True, timeout=3)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA query_only=ON')
    return c


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + '.partial')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    temporary.replace(path)


def witnesses(metadata):
    result = set(metadata.get('chunk_ids_witness', []))
    result.update(metadata.get('chunk_ids', []))
    for occurrence in metadata.get('source_occurrences', []):
        result.update(occurrence.get('chunk_ids_witness', []))
    return sorted(result)


def npy_header(stream):
    if stream.read(6) != b'\x93NUMPY':
        raise ValueError('Invalid NPY magic')
    version = stream.read(2)
    if version[0] == 1:
        size = struct.unpack('<H', stream.read(2))[0]
    elif version[0] in (2, 3):
        size = struct.unpack('<I', stream.read(4))[0]
    else:
        raise ValueError('Unsupported NPY version')
    header = ast.literal_eval(stream.read(size).decode('utf8' if version[0] == 3 else 'latin1').strip())
    if header['fortran_order']:
        raise ValueError('Fortran layout unsupported for this control')
    return header, stream.tell()


def audit(snapshot=SNAPSHOT, database=DATABASE, cache=CACHE, output=OUTPUT):
    started = time.monotonic()
    snapshot, database, cache, output = map(Path, (snapshot, database, cache, output))
    output.mkdir(parents=True, exist_ok=True)
    source = read_db(snapshot, immutable=True)
    local = read_db(database)
    refs = [dict(row) for row in source.execute('SELECT e.*,r.asset_sha256 FROM external_links e LEFT JOIN refs r ON r.id=e.ref_id ORDER BY e.document_id')]
    ids = [row['document_id'] for row in refs]
    placeholders = ','.join('?' for _ in ids)
    found_docs = {row['doc']: dict(row) for row in local.execute('SELECT doc,title,path,meta FROM docs WHERE doc IN (' + placeholders + ')', ids)}
    chunk_counts = {}
    print(json.dumps({'phase': 'document_ids', 'expected': len(refs), 'matched': len(found_docs)}), flush=True)
    for row in local.execute('''SELECT c.doc,count(*) AS chunks,
              sum(length(trim(c.text))>0) AS nonempty_text_chunks,
              sum(c.page_start IS NOT NULL AND c.page_end IS NOT NULL) AS cited_chunks,
              sum(e.id IS NOT NULL) AS embedded_chunks,
              min(e.dim) AS min_dim,max(e.dim) AS max_dim,
              min(length(e.vec)) AS min_vector_bytes,max(length(e.vec)) AS max_vector_bytes
              FROM chunks c LEFT JOIN chunk_embeddings e ON e.id=c.id
              WHERE c.doc IN (''' + placeholders + ') GROUP BY c.doc', ids):
        chunk_counts[row['doc']] = dict(row)
    print(json.dumps({'phase': 'chunks', 'documents': len(chunk_counts), 'chunks': sum(r['chunks'] for r in chunk_counts.values())}), flush=True)
    cache_info = {'available': False}
    cache_positions, vectors = {}, None
    vector_offset = 0
    try:
        metadata = json.loads((cache / 'meta.json').read_text(encoding='utf8'))
        with (cache / 'chunk_ids.npy').open('rb') as ids_file:
            id_header, id_offset = npy_header(ids_file)
            if id_header['descr'] != '|S64' or len(id_header['shape']) != 1:
                raise ValueError('Unexpected chunk ID dtype/shape')
            vector_ids = [ids_file.read(64).rstrip(b'\x00').decode('ascii') for _ in range(id_header['shape'][0])]
        cache_positions = {item: i for i, item in enumerate(vector_ids)}
        vectors = (cache / 'bge_m3_vectors.npy').open('rb')
        vector_header, vector_offset = npy_header(vectors)
        if vector_header['descr'] != '<f4' or vector_header['shape'] != (len(vector_ids), 1024):
            raise ValueError('Unexpected vector dtype/shape')
        if (cache / 'bge_m3_vectors.npy').stat().st_size != vector_offset + len(vector_ids) * 4096:
            raise ValueError('Truncated or extended vector file')
        cache_info = {'available': True, 'metadata': metadata, 'vector_shape': list(vector_header['shape']),
                      'vector_dtype': 'float32', 'id_rows': len(vector_ids),
                      'unique_ids': len(cache_positions), 'model': metadata.get('fingerprint', {}).get('model'),
                      'model_revision': metadata.get('fingerprint', {}).get('model_revision'),
                      'cache_database_size_matches': metadata.get('fingerprint', {}).get('size') == database.stat().st_size,
                      'cache_database_mtime_matches': metadata.get('fingerprint', {}).get('mtime_ns') == database.stat().st_mtime_ns,
                      'sparse_store_verified': False}
    except Exception as exc:
        cache_info['error'] = type(exc).__name__ + ': ' + str(exc)
    results = []
    all_witnesses, verified_witnesses, cached_witnesses = 0, 0, 0
    for row in refs:
        metadata = json.loads(row['metadata_json'])
        doc_id = row['document_id']
        doc = found_docs.get(doc_id)
        doc_metadata = json.loads(doc['meta'] or '{}') if doc else {}
        expected_sha = metadata.get('index_source_expected_sha256') or metadata.get('original_pdf_sha256_expected') or metadata.get('sha256')
        observed_sha = doc_metadata.get('document_sha256')
        witness_results = []
        for witness in witnesses(metadata):
            all_witnesses += 1
            chunk = local.execute('SELECT id,doc,text,page_start,page_end,token_count FROM chunks WHERE id=?', (witness,)).fetchone()
            item = {'id': witness, 'found': chunk is not None, 'same_document': bool(chunk and chunk['doc'] == doc_id)}
            if chunk:
                item.update(text_chars=len(chunk['text']), text_sha256=hashlib.sha256(chunk['text'].encode('utf8')).hexdigest(),
                            text_sample=chunk['text'][:280], page_start=chunk['page_start'], page_end=chunk['page_end'], token_count=chunk['token_count'])
                if item['same_document'] and chunk['text'].strip():
                    verified_witnesses += 1
            position = cache_positions.get(witness)
            item['dense_cache_row'] = position
            if position is not None and vectors is not None:
                vectors.seek(vector_offset + position * 4096)
                vector = struct.unpack('<1024f', vectors.read(4096))
                item['dense_finite'] = all(math.isfinite(value) for value in vector)
                item['dense_norm'] = math.sqrt(sum(value * value for value in vector))
                item['dense_dimension'] = len(vector)
                if item['dense_finite'] and 0.98 <= item['dense_norm'] <= 1.02 and item['dense_dimension'] == 1024:
                    cached_witnesses += 1
            witness_results.append(item)
        results.append({'ref_id': row['ref_id'], 'document_id': doc_id, 'asset_sha256': row['asset_sha256'],
                        'title': metadata.get('title'), 'url': metadata.get('url'), 'canonical_database': metadata.get('canonical_database'),
                        'local_document_found': doc is not None, 'expected_source_sha256': expected_sha,
                        'observed_source_sha256': observed_sha,
                        'source_sha256_matches': expected_sha == observed_sha if expected_sha and observed_sha else None,
                        'chunks': chunk_counts.get(doc_id), 'witnesses': witness_results,
                        'old_verification': row['verification'],
                        'live_status': 'local_doc_and_witness_verified' if doc and witness_results and all(w['same_document'] and w.get('text_chars', 0) > 0 for w in witness_results) else 'not_fully_verified',
                        'numeric_status': 'documentary_text_not_validated_budget_fact'})
    missing = [row for row in results if not row['local_document_found']]
    report = {'at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'snapshot': str(snapshot),
              'database_checked': str(database), 'external_links': len(refs), 'unique_document_ids': len(set(ids)),
              'documents_found': len(found_docs), 'documents_missing_from_this_copy': len(missing),
              'source_hash_mismatches': sum(row['source_sha256_matches'] is False for row in results),
              'local_chunks': sum(row['chunks'] for row in chunk_counts.values()),
              'nonempty_text_chunks': sum(row['nonempty_text_chunks'] for row in chunk_counts.values()),
              'embedded_chunks_sqlite': sum(row['embedded_chunks'] for row in chunk_counts.values()),
              'witnesses_expected': all_witnesses, 'witnesses_with_correct_parent_and_text': verified_witnesses,
              'witnesses_with_finite_normalized_dense1024': cached_witnesses, 'cache': cache_info,
              'all_links_live_verified': len(found_docs) == len(refs) and verified_witnesses == all_witnesses,
              'source_modified': False, 'gpu_launched': False,
              'elapsed_seconds': round(time.monotonic() - started, 1),
              'limitation': 'La copie E:/Marie AN 2026 est historique. Les absences ici ne prouvent pas une absence du VHDX canonique actuellement non monté. Le modèle dense est déclaré par le cache ; sa révision et les vecteurs sparse restent non vérifiés.'}
    write_json(output / 'external_links_live_audit.json', report)
    write_json(output / 'references_checked.json', results)
    write_json(output / 'missing_documents.json', missing)
    write_json(output / 'fallback_plan.json', {
        'source_modified': False, 'gpu_launched': False,
        'steps': [
            'Reconnecter en lecture seule le VHDX canonique puis relancer ce contrôle sur la vraie base.',
            'Si une référence reste indisponible, utiliser les passages conservés localement avec leur SHA source, pages et statut qualité, sans supprimer les anciennes références.',
            'Inclure dans une génération vectorielle suivante les seuls passages sans vecteur accessible, avec manifeste de remplacement et sans double comptage.',
            'Ne pas transformer les passages de tableaux aplatis en faits numériques ; utiliser la reconstruction et les références de cellules.'
        ],
        'held_route': 'existing_cour_pending_connection', 'missing_documents_in_checked_copy': len(missing),
        'new_vectorization_authorized': False})
    local.close()
    if vectors is not None:
        vectors.close()
    source.close()
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=SNAPSHOT)
    parser.add_argument('--database', type=Path, default=DATABASE)
    parser.add_argument('--cache', type=Path, default=CACHE)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    audit(args.snapshot, args.database, args.cache, args.output)
