"""Extend a copied small supplement; reuse every previous vector byte for byte."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_retrieval_supplement as original
from budget_service.retrieval_contract import VERSION, MODEL, REVISION, DIMENSION, digest, write_json, read_db


def compare_previous(previous_root, output):
    previous = read_db(previous_root / 'search.sqlite')
    current = read_db(output / 'search.sqlite')
    checked = []
    aggregate = hashlib.sha256()
    for row in previous.execute('SELECT p.*,v.dense FROM passages p JOIN vectors v ON v.seq=p.seq ORDER BY p.seq'):
        copied = current.execute('SELECT p.*,v.dense FROM passages p JOIN vectors v ON v.seq=p.seq WHERE p.seq=?', (row['seq'],)).fetchone()
        if copied is None or tuple(copied) != tuple(row):
            raise ValueError('Previously encoded passage changed: ' + str(row['seq']))
        old_cites = previous.execute('SELECT * FROM citations WHERE seq=? ORDER BY document_id,locator', (row['seq'],)).fetchall()
        new_cites = current.execute('SELECT * FROM citations WHERE seq=? ORDER BY document_id,locator', (row['seq'],)).fetchall()
        if [tuple(item) for item in old_cites] != [tuple(item) for item in new_cites]:
            raise ValueError('Previous citations changed')
        dense_sha = hashlib.sha256(row['dense']).hexdigest()
        sparse_sha = hashlib.sha256(row['sparse_ids'] + row['sparse_weights']).hexdigest()
        aggregate.update((str(row['seq']) + ':' + row['id'] + ':' + dense_sha + ':' + sparse_sha).encode())
        checked.append(dict(seq=row['seq'], id=row['id'], text_sha256=row['text_sha256'],
                            dense_sha256=dense_sha, sparse_sha256=sparse_sha))
    for row in previous.execute('SELECT * FROM documents ORDER BY id'):
        copied = current.execute('SELECT * FROM documents WHERE id=?', (row['id'],)).fetchone()
        if tuple(row) != tuple(copied):
            raise ValueError('Previous document metadata changed')
    previous.close()
    current.close()
    proof = dict(passed=True, reused_passages=len(checked), aggregate_sha256=aggregate.hexdigest(),
                 dense_sparse_text_metadata_citations_identical=True, passages=checked)
    write_json(output / 'preserved-vectors.json', proof)
    return proof


def prepare(previous_root, source, output, expected_manifest, base_identity):
    if digest(previous_root / 'manifest.json') != expected_manifest:
        raise ValueError('Unexpected previous supplement manifest')
    manifest = json.loads((previous_root / 'manifest.json').read_text())
    if (manifest['version'], manifest['state'], manifest['model'], manifest['revision'], manifest['dimension']) != (VERSION, 'ready', MODEL, REVISION, DIMENSION):
        raise ValueError('Incompatible previous supplement')
    if manifest.get('base_input_sha256') != base_identity:
        raise ValueError('Extension belongs to another main generation')
    previous_database = (previous_root / 'search.sqlite').resolve()
    target_database = output / 'search.sqlite'
    if target_database.resolve() == previous_database or (target_database.exists() and target_database.samefile(previous_database)):
        raise ValueError('Output must be a separate copy of the previous supplement')
    for item in manifest['files']:
        if digest(previous_root / item['path']) != item['sha256']:
            raise ValueError('Previous supplement checksum mismatch')
    output.mkdir(parents=True, exist_ok=True)
    target = output / 'search.sqlite'
    if not target.exists():
        temporary = output / 'search.sqlite.copying'
        shutil.copyfile(previous_root / 'search.sqlite', temporary)
        if digest(temporary) != digest(previous_root / 'search.sqlite'):
            raise ValueError('Supplement copy checksum mismatch')
        temporary.replace(target)
    identity = digest(source)
    db = sqlite3.connect(target)
    metadata = dict(db.execute('SELECT key,value FROM metadata'))
    if metadata.get('extension_input_sha256'):
        if metadata['extension_input_sha256'] != identity or metadata.get('previous_manifest_sha256') != expected_manifest:
            raise ValueError('Extension output belongs to another input')
        db.close()
        return compare_previous(previous_root, output)
    if digest(target) != digest(previous_root / 'search.sqlite'):
        db.close()
        raise ValueError('Unrecognized output database; preserve it and choose a new directory')
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained('/opt/lexmachine-models/models--BAAI--bge-m3/snapshots/' + REVISION, local_files_only=True)
    payload = json.loads(source.read_text(encoding='utf-8-sig'))
    seq = db.execute('SELECT max(seq) FROM passages').fetchone()[0]
    previous_passages = seq
    document_id = db.execute('SELECT max(id) FROM documents').fetchone()[0]
    document_ids = {}
    tokens_total = 0
    by_source = {}
    with db:
        for source_record in payload['sources']:
            if db.execute('SELECT 1 FROM documents WHERE source_sha256=?', (source_record['sha256'],)).fetchone():
                raise ValueError('Source already exists in previous supplement')
            document_id += 1
            document_ids[source_record['id']] = document_id
            db.execute('INSERT INTO documents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)', (
                document_id, 'supplement:' + source_record['sha256'], source_record['sha256'], source_record['id'],
                source_record['title'], source_record['url'], source_record['format'],
                '|' + '|'.join(str(year) for year in source_record['years_title']) + '|',
                source_record['stage'], 'source_' + source_record['format'],
                'not_certified', 'raw_not_validated_facts', 1))
        for segment in payload['segments']:
            text = segment['text']
            spans = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)['offset_mapping']
            for part, start in enumerate(range(0, len(spans), 384), 1):
                stop = min(start + 448, len(spans))
                first_char, last_char = spans[start][0], spans[stop - 1][1]
                chunk = text[first_char:last_char]
                token_count = len(tokenizer(chunk, add_special_tokens=True)['input_ids'])
                if token_count > 512:
                    raise ValueError('Unexpected retokenization above 512 tokens')
                locator = segment['locator'] + '/raw/part:' + str(part)
                if segment['format'] == 'html':
                    notes = [anchor for anchor in segment['anchors'] if anchor['kind'] == 'note'
                             and anchor['text_start'] <= first_char < anchor['element_text_end']]
                    sections = [anchor for anchor in segment['anchors'] if anchor['kind'] == 'section'
                                and anchor['title'] and anchor['text_start'] <= first_char]
                    anchor = (notes or sections or [None])[-1]
                    prefix = '#' + anchor['anchor'] if anchor else 'body'
                    title = anchor['title'] if anchor else 'Document HTML'
                    locator = 'html:' + prefix + '/section:' + quote(title, safe='') + '/chars:' + str(first_char) + '-' + str(last_char) + '/part:' + str(part)
                sha = hashlib.sha256(chunk.encode()).hexdigest()
                ident = hashlib.sha256((segment['source_sha256'] + ':' + locator + ':' + sha).encode()).hexdigest()
                seq += 1
                tokens_total += token_count
                by_source[segment['source_id']] = by_source.get(segment['source_id'], 0) + 1
                db.execute('INSERT INTO passages VALUES(?,?,?,?,?,?,?)', (seq, ident, chunk, token_count, sha, b'', b''))
                db.execute('INSERT INTO passages_fts(rowid,text) VALUES(?,?)', (seq, chunk))
                db.execute('INSERT INTO citations VALUES(?,?,?)', (seq, document_ids[segment['source_id']], locator))
                if stop == len(spans):
                    break
        db.executemany('INSERT OR REPLACE INTO metadata VALUES(?,?)', [
            ('input_sha256', identity), ('extension_input_sha256', identity),
            ('previous_manifest_sha256', expected_manifest), ('state', 'prepared'),
            ('previous_passages_reused', str(previous_passages))])
    db.close()
    write_json(output / 'preparation.json', dict(input_sha256=identity,
        previous_manifest_sha256=expected_manifest, reused_passages=previous_passages,
        added_passages=seq - previous_passages, passages=seq, added_documents=len(document_ids),
        encoded_tokens=tokens_total, passages_by_source=by_source, no_main_index_mounted=True))
    return compare_previous(previous_root, output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous-root', type=Path, required=True)
    parser.add_argument('--previous-manifest-sha256', required=True)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--base-identity', required=True)
    parser.add_argument('--encode', action='store_true')
    parser.add_argument('--threads', type=int, default=4)
    args = parser.parse_args()
    proof = prepare(args.previous_root, args.input, args.output, args.previous_manifest_sha256, args.base_identity)
    print(json.dumps(dict(reused_passages=proof['reused_passages'], unchanged_sha256=proof['aggregate_sha256'])), flush=True)
    if args.encode:
        original.encode(args.output, args.base_identity, args.threads)
        proof = compare_previous(args.previous_root, args.output)
        print(json.dumps(dict(passed=True, reused_passages=proof['reused_passages'], unchanged_sha256=proof['aggregate_sha256'])), flush=True)
