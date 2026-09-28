"""Build a small, resumable BGE-M3 supplement; never opens the main index for writing."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from budget_service.retrieval_contract import VERSION, MODEL, REVISION, DIMENSION, digest, write_json


def prepare(source, output):
    from transformers import AutoTokenizer
    identity = digest(source)
    payload = json.loads(source.read_text(encoding='utf-8-sig'))
    tokenizer = AutoTokenizer.from_pretrained('/opt/lexmachine-models/models--BAAI--bge-m3/snapshots/' + REVISION, local_files_only=True)
    output.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(output / 'search.sqlite')
    db.executescript('''
      CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS passages(seq INTEGER PRIMARY KEY,id TEXT UNIQUE NOT NULL,
        text TEXT NOT NULL,tokens INTEGER NOT NULL,text_sha256 TEXT NOT NULL,
        sparse_ids BLOB NOT NULL,sparse_weights BLOB NOT NULL);
      CREATE TABLE IF NOT EXISTS vectors(seq INTEGER PRIMARY KEY,dense BLOB NOT NULL);
      CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY,reference_id TEXT UNIQUE NOT NULL,
        source_sha256 TEXT NOT NULL,source_id TEXT NOT NULL,title TEXT NOT NULL,url TEXT NOT NULL,
        format TEXT NOT NULL,years_key TEXT NOT NULL,stage TEXT NOT NULL,source_kind TEXT NOT NULL,
        table_layout TEXT NOT NULL,numeric_status TEXT NOT NULL,local_available INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS citations(seq INTEGER NOT NULL,document_id INTEGER NOT NULL,
        locator TEXT NOT NULL,PRIMARY KEY(seq,document_id,locator));
      CREATE INDEX IF NOT EXISTS document_citations ON citations(document_id,seq);
      CREATE VIRTUAL TABLE IF NOT EXISTS passages_fts USING fts5(text,content='passages',content_rowid='seq',tokenize='unicode61 remove_diacritics 2');
    ''')
    previous = dict(db.execute('SELECT key,value FROM metadata'))
    if previous:
        if previous.get('input_sha256') != identity:
            raise ValueError('Output belongs to another input; preserve it and choose another directory')
        db.close()
        return
    sources = {s['id']: s for s in payload['sources']}
    for number, source_record in enumerate(sources.values(), 1):
        db.execute('INSERT INTO documents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)', (
            number, 'supplement:' + source_record['sha256'], source_record['sha256'], source_record['id'],
            source_record['title'], source_record['url'], 'pdf', '|' + '|'.join(source_record['years_title']) + '|',
            'NEB' if 'ccomptes.fr' in source_record['url'] else 'rapport-PLF', 'source_pdf',
            'not_certified', 'raw_not_validated_facts', 1))
    document_ids = dict(db.execute('SELECT source_id,id FROM documents'))
    seq = tokens_total = 0
    page_counts = {}
    for page in payload['pages']:
        text = page['text']
        spans = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)['offset_mapping']
        if not spans:
            continue
        page_counts[page['source_id']] = page_counts.get(page['source_id'], 0) + 1
        for part, start in enumerate(range(0, len(spans), 384), 1):
            stop = min(start + 448, len(spans))
            chunk = text[spans[start][0]:spans[stop - 1][1]]
            token_count = len(tokenizer(chunk, add_special_tokens=True)['input_ids'])
            if token_count > 512:
                raise ValueError('Unexpected retokenization above 512 tokens')
            sha = hashlib.sha256(chunk.encode()).hexdigest()
            ident = hashlib.sha256(f"{page['source_sha256']}:{page['page']}:{part}:{sha}".encode()).hexdigest()
            seq += 1
            tokens_total += token_count
            db.execute('INSERT INTO passages VALUES(?,?,?,?,?,?,?)', (seq, ident, chunk, token_count, sha, b'', b''))
            db.execute('INSERT INTO passages_fts(rowid,text) VALUES(?,?)', (seq, chunk))
            db.execute('INSERT INTO citations VALUES(?,?,?)', (seq, document_ids[page['source_id']], f"page:{page['page']}/raw/part:{part}"))
            if stop == len(spans):
                break
    db.executemany('INSERT INTO metadata VALUES(?,?)', [('input_sha256', identity), ('state', 'prepared'), ('version', VERSION)])
    db.commit()
    db.close()
    write_json(output / 'preparation.json', dict(input_sha256=identity, documents=len(sources), passages=seq,
        tokens=tokens_total, source_pages=len(payload['pages']), nonempty_pages=sum(page_counts.values()),
        pages_by_source=page_counts, source_sha256s=[s['sha256'] for s in sources.values()],
        extraction='PyMuPDF sorted text, page boundaries preserved; overlapping tokenizer spans',
        automatic_numeric_import=False))


def encode(output, base_identity, threads):
    import faiss
    import numpy as np
    import torch
    from transformers import AutoModel, AutoTokenizer
    start = time.monotonic()
    torch.set_num_threads(threads)
    model_path = '/opt/lexmachine-models/models--BAAI--bge-m3/snapshots/' + REVISION
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    model = AutoModel.from_pretrained(model_path, local_files_only=True, dtype=torch.float32).eval()
    linear = torch.nn.Linear(DIMENSION, 1)
    linear.load_state_dict(torch.load(Path(model_path) / 'sparse_linear.pt', map_location='cpu', weights_only=True))
    linear.eval()
    specials = set(tokenizer.all_special_ids)
    db = sqlite3.connect(output / 'search.sqlite')
    db.row_factory = sqlite3.Row
    rows = db.execute('SELECT p.* FROM passages p LEFT JOIN vectors v ON v.seq=p.seq WHERE v.seq IS NULL ORDER BY p.seq').fetchall()
    total = db.execute('SELECT count(*) FROM passages').fetchone()[0]
    already = total - len(rows)
    for number, row in enumerate(rows, 1):
        inputs = tokenizer(row['text'], return_tensors='pt', truncation=False)
        if inputs['input_ids'].shape[1] > 512:
            raise ValueError('Passage exceeds validated token window')
        with torch.inference_mode():
            hidden = model(**inputs).last_hidden_state
            dense = torch.nn.functional.normalize(hidden[:, 0].float(), p=2, dim=1).numpy()[0]
            weights = torch.relu(linear(hidden)).squeeze(-1)[0].tolist()
        sparse = {}
        for token, weight in zip(inputs['input_ids'][0].tolist(), weights):
            if token not in specials and weight > 0:
                sparse[token] = max(weight, sparse.get(token, 0))
        ids = np.array(sorted(sparse), dtype='<i4')
        values = np.array([sparse[int(token)] for token in ids], dtype='<f4')
        if not np.isfinite(dense).all() or abs(float(np.linalg.norm(dense)) - 1) > 1e-5:
            raise ValueError('Invalid generated dense vector')
        with db:
            db.execute('INSERT INTO vectors VALUES(?,?)', (row['seq'], dense.astype('<f4').tobytes()))
            db.execute('UPDATE passages SET sparse_ids=?,sparse_weights=? WHERE seq=?', (ids.tobytes(), values.tobytes(), row['seq']))
        if number % 20 == 0 or number == len(rows):
            elapsed = time.monotonic() - start
            progress = dict(state='encoding', completed=already + number, total=total,
                session_seconds=round(elapsed, 1), estimated_remaining_seconds=round(elapsed / number * (len(rows) - number)),
                model=MODEL, revision=REVISION, dtype='float32', cpu_only=True, threads=threads)
            write_json(output / 'progress.json', progress)
            print(json.dumps(progress), flush=True)
    encoded = db.execute('SELECT seq,dense FROM vectors ORDER BY seq').fetchall()
    if len(encoded) != total:
        raise ValueError('Incomplete encoded set')
    dense = np.vstack([np.frombuffer(r['dense'], dtype='<f4') for r in encoded])
    index = faiss.IndexIDMap(faiss.IndexFlatIP(DIMENSION))
    index.add_with_ids(dense, np.array([r['seq'] for r in encoded], dtype='int64'))
    faiss.write_index(index, str(output / 'dense.faiss'))
    documents = db.execute('SELECT count(*) FROM documents').fetchone()[0]
    identity = db.execute("SELECT value FROM metadata WHERE key='input_sha256'").fetchone()[0]
    db.execute("UPDATE metadata SET value='ready' WHERE key='state'")
    db.commit()
    if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise ValueError('Supplement integrity check failed')
    db.close()
    manifest = dict(version=VERSION, state='ready', input_sha256=identity, base_input_sha256=base_identity,
        model=MODEL, revision=REVISION, dimension=DIMENSION, passages=total, documents=documents,
        quantization='none/float32', sparse='candidate_reranking', encoder_dtype='float32',
        numeric_facts_certified=False, generated_at=datetime.now(timezone.utc).isoformat(), files=[])
    for name in ['search.sqlite', 'dense.faiss']:
        path = output / name
        manifest['files'].append(dict(path=name, bytes=path.stat().st_size, sha256=digest(path)))
    write_json(output / 'manifest.json', manifest)
    write_json(output / 'progress.json', dict(state='ready', completed=total, total=total, session_seconds=round(time.monotonic() - start, 1)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--base-identity', required=True)
    parser.add_argument('--encode', action='store_true')
    parser.add_argument('--threads', type=int, default=4)
    args = parser.parse_args()
    prepare(args.input, args.output)
    if args.encode:
        encode(args.output, args.base_identity, args.threads)
