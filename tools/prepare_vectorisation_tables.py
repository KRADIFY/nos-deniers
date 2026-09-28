"""Resumable, lossless PDF table staging. Does not alter the active preparation.

One compressed document is committed at a time. Native words and blocks remain
available beside reconstructed candidates; extracted numbers are never facts.
No network, encoder, GPU or automatic publication is implemented here.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
import unicodedata

from vectorisation_table_geometry import recovery_candidates
from vectorisation_table_text import serialize_table

ROOT = Path(__file__).resolve().parents[1]
PREPARATION = Path('D:/LexMachine/NosDeniers/preparation_20260909')
SNAPSHOT = PREPARATION/'checkpoints/after_isolated_merge_20260911_094736.sqlite'
SOURCE_CODE = ROOT.parent.parent/'Mises à jour auto/nos_deniers_preparation_20260909'
STAGE = PREPARATION/'tables_revision_20260911'
VERSION = 'lossless-pdf-table-staging-v1'
ALERT = 'grid_candidate_not_resolved'


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def replace_file_safely(source, target):
    """Windows readers/antivirus may briefly deny rename; never lose a checkpoint."""
    for attempt in range(30):
        try:
            Path(source).replace(target)
            return
        except PermissionError:
            if attempt == 29:
                raise
            time.sleep(0.1+attempt*0.01)


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+'.partial')
    temporary.write_text(canonical(value)+'\n', encoding='utf-8')
    replace_file_safely(temporary,path)


def read_db(path, *, immutable=False):
    con = sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro'+('&immutable=1' if immutable else ''), uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA query_only=ON')
    return con


def lexical(text):
    return Counter(re.findall(r'\w+', unicodedata.normalize('NFC', str(text)).casefold()))


def raw_chunks(record, source_sha, tokenizer, maximum=800):
    """Preserve every source block character and any word absent from blocks.

    Token boundaries are NOT used as character boundaries: byte fallback and
    Unicode normalization must not remove a source character. Chunk fragments
    carry exact source block offsets. The original record preserves coordinates.
    """
    blocks = [str(b.get('text', '')) for b in record.get('blocks', [])]
    represented = sum((lexical(x) for x in blocks), Counter())
    source_words = record.get('words', [])
    remaining = sum((lexical(w[4]) for w in source_words), Counter())-represented
    if remaining:
        # Rare extractor divergence: keep the complete positioned-word reading,
        # rather than inventing placement for just the missing fragments.
        blocks.append(' '.join(str(w[4]) for w in source_words))
    prefix = (f'Source {source_sha} · page physique {record["page"]}\n'
              'Texte source intégral. Coordonnées et tableaux dans le dossier de preuve de cette page. '
              'Les associations de colonnes nécessitent un contrôle ; aucun fait financier automatiquement validé.\n\n')
    def count(text):
        return len(tokenizer.encode(text, add_special_tokens=True).ids)
    if count(prefix)+24 >= maximum:
        raise ValueError('Raw context exceeds the token budget')
    chunks, pending = [], []
    def rendered(items):
        return '\n\n'.join(x['text'] for x in items)
    def fits(items):
        return count(prefix+rendered(items)) <= maximum
    def flush():
        if not pending:
            return
        body = rendered(pending)
        text = prefix+body
        chunks.append({'text':text, 'body':body, 'tokens':count(text),
                       'locator':f'page:{record["page"]}/raw/part:{len(chunks)+1}',
                       'segments':[dict(x) for x in pending], 'kind':'page_source_text'})
        pending.clear()
    for block_no, text in enumerate(blocks):
        if not text:
            continue
        item = {'block':block_no, 'char_start':0, 'char_end':len(text), 'text':text}
        if fits(pending+[item]):
            pending.append(item)
            continue
        flush()
        if fits([item]):
            pending.append(item)
            continue
        start = 0
        while start < len(text):
            low, high, end = start+1, len(text), None
            while low <= high:
                trial = (low+high)//2
                fragment = dict(item, char_start=start, char_end=trial, text=text[start:trial])
                if fits([fragment]):
                    end = trial
                    low = trial+1
                else:
                    high = trial-1
            if end is None:
                raise ValueError('A source character cannot fit without truncation')
            if end < len(text):
                boundaries = list(re.finditer(r'\s+', text[start:end]))
                if boundaries:
                    end = start+boundaries[-1].end()
            pending.append(dict(item, char_start=start, char_end=end, text=text[start:end]))
            flush()
            start = end
    flush()
    recovered = ['' for _ in blocks]
    for chunk in chunks:
        for segment in chunk['segments']:
            n = segment['block']
            if len(recovered[n]) != segment['char_start']:
                raise ValueError('Gap or overlap in raw text')
            recovered[n] += segment['text']
    if recovered != blocks:
        raise ValueError('Raw source text was lost')
    if sum((lexical(w[4]) for w in source_words), Counter())-sum((lexical(x) for x in recovered), Counter()):
        raise ValueError('Source words are absent from the indexed raw text')
    return chunks


def page_payload(record, page, source_sha, tokenizer, documentary_context):
    needed = bool(record.get('tables')) or ALERT in record.get('issues', [])
    base = {'page':record['page'], 'raw_record_sha256':digest(canonical(record)),
            'grid_alert':int(ALERT in record.get('issues', [])), 'has_table':int(bool(record.get('tables'))),
            'review_required':needed}
    if not needed:
        return base
    recovered = recovery_candidates(page, record)
    raw = raw_chunks(record, source_sha, tokenizer)
    candidates, tables, chunks = recovered['tables'], [], list(raw)
    # Accepted regions augment the raw text. Original extraction tables stay in
    # the full record; an accepted region never erases another table or paragraph.
    for index, table in enumerate(candidates, 1):
        context = {'source_sha256':source_sha, 'page':record['page'], 'table_id':f'recovered-{index}',
                   'documentary_context':documentary_context,
                   'preceding_text':'\n'.join(x['text'] for x in table.get('context_before', []))}
        result = serialize_table(table, context, tokenizer)
        tables.append(result['raw_table'])
        for chunk in result['chunks']:
            chunk['kind'] = 'table_candidate'
            chunks.append(chunk)
    # Original cells outside accepted regions are retained as explicitly raw
    # tables too. The original page text, not these cells, proves numeric coverage.
    for index, table in enumerate(record.get('tables', []), 1):
        box = table.get('bbox')
        contained = box and any(box[0] >= c['bbox'][0]-2 and box[1] >= c['bbox'][1]-2
                  and box[2] <= c['bbox'][2]+2 and box[3] <= c['bbox'][3]+2 for c in candidates)
        if contained:
            continue
        context = {'source_sha256':source_sha, 'page':record['page'], 'table_id':f'original-{index}',
                   'documentary_context':documentary_context,
                   'layout_status':'Original extraction; columns unverified; consult raw page.'}
        result = serialize_table(table, context, tokenizer)
        tables.append(result['raw_table'])
        for chunk in result['chunks']:
            chunk['kind'] = 'table_candidate'
            chunks.append(chunk)
    return base | {'record':record, 'status':'positioned_source_retained_review_required',
                   'raw_segments':[c['body'] for c in raw], 'chunks':chunks,
                   'tables':tables, 'reconstruction':{
                       'method':recovered['method'], 'accepted':len(candidates),
                       'rejected':len(recovered['rejected_candidates']),
                       'diagnostics':recovered['diagnostics'],
                       'rejected_candidates':recovered['rejected_candidates']},
                   'numeric_fact_certified':False, 'allow_automatic_numeric_fact':False}


def document_job(item, settings):
    """Worker writes only its own compressed staging file and receipt."""
    import fitz
    from tokenizers import Tokenizer
    started = time.monotonic()
    sha = item['sha256']
    out = Path(settings['stage'])/'documents'/sha[:2]/(sha+'.jsonl.gz')
    receipt_path = out.with_suffix('.receipt.json')
    out.parent.mkdir(parents=True, exist_ok=True)
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        if (receipt['source_shard_sha256'] == item['shard_sha256']
            and receipt['contract'] == settings['contract'] and file_hash(out) == receipt['sha256']):
            return receipt
        raise ValueError('Existing staged document differs; preserve it in another revision')
    source = Path(item['path'])
    if file_hash(source) != sha:
        raise ValueError('Physical PDF differs from its registered source SHA')
    shard = Path(settings['preparation'])/'extracted'/sha[:2]/(sha+'.jsonl.gz')
    if file_hash(shard) != item['shard_sha256']:
        raise ValueError('Extraction shard changed; await final OCR state and restage this document')
    tokenizer = Tokenizer.from_file(settings['config']['tokenizer'])
    tokenizer.no_truncation()
    tokenizer.no_padding()
    temporary = out.with_suffix('.partial')
    totals = {'pages':0, 'grid_alert_pages':0, 'review_pages':0, 'table_candidates':0,
              'chunks':0, 'tokens':0, 'max_tokens':0}
    doc = fitz.open(source)
    try:
        with gzip.open(shard, 'rt', encoding='utf-8') as inp, gzip.open(temporary, 'wt', encoding='utf-8', compresslevel=4) as target:
            for line in inp:
                record = json.loads(line)
                if record.get('kind') != 'page':
                    continue
                page_no = record['page']
                if page_no != totals['pages']+1:
                    raise ValueError('Missing or reordered source page')
                payload = page_payload(record, doc[page_no-1], sha, tokenizer, item['context'])
                target.write(canonical(payload)+'\n')
                totals['pages'] += 1
                totals['grid_alert_pages'] += payload['grid_alert']
                if payload['review_required']:
                    totals['review_pages'] += 1
                    totals['table_candidates'] += payload['reconstruction']['accepted']
                    totals['chunks'] += len(payload['chunks'])
                    totals['tokens'] += sum(c['tokens'] for c in payload['chunks'])
                    totals['max_tokens'] = max(totals['max_tokens'], max((c['tokens'] for c in payload['chunks']), default=0))
                if page_no % 20 == 0:
                    atomic_json(out.with_suffix('.progress.json'), {'sha256':sha, **totals,
                                'elapsed_seconds':round(time.monotonic()-started, 1)})
        if totals['pages'] != item['pages'] or totals['pages'] != len(doc):
            raise ValueError('Page count differs from the source PDF/receipt')
        if file_hash(shard) != item['shard_sha256']:
            raise ValueError('Extraction changed during this document')
        replace_file_safely(temporary,out)
        receipt = {'source_sha256':sha, 'source_shard_sha256':item['shard_sha256'],
                   'source_pdf':str(source), 'file':str(out), 'sha256':file_hash(out),
                   'bytes':out.stat().st_size, 'contract':settings['contract'], **totals,
                   'elapsed_seconds':round(time.monotonic()-started, 1),
                   'automatic_numeric_fact':False, 'gpu_launched':False}
        atomic_json(receipt_path, receipt)
        return receipt
    finally:
        doc.close()


def stage(snapshot=SNAPSHOT, preparation=PREPARATION, stage_root=STAGE, workers=2, only_sha=None, limit=0):
    sys.path.insert(0, str(SOURCE_CODE))
    from common import single_instance
    stage_root = Path(stage_root)
    stage_root.mkdir(parents=True, exist_ok=True)
    config = json.loads((SOURCE_CODE/'config.json').read_text(encoding='utf-8'))
    if file_hash(config['tokenizer']) != config['tokenizer_sha256']:
        raise ValueError('Tokenizer changed')
    code = {name:file_hash(Path(__file__).parent/name) for name in
            ('prepare_vectorisation_tables.py', 'vectorisation_table_geometry.py', 'vectorisation_table_text.py')}
    contract = digest(canonical({'version':VERSION, 'code':code, 'tokenizer':config['tokenizer_sha256']}))
    settings = {'stage':str(stage_root), 'preparation':str(preparation), 'config':config, 'contract':contract}
    con = read_db(snapshot,immutable=True)
    items = []
    try:
        for row in con.execute("SELECT a.*,e.shard_sha256,e.receipt_json FROM assets a JOIN extraction e ON e.asset_sha256=a.sha256 WHERE a.kind='pdf' AND e.status='complete' ORDER BY a.sha256"):
            if only_sha and row['sha256'] not in only_sha:
                continue
            refs = [json.loads(r[0]) for r in con.execute('SELECT metadata_json FROM refs WHERE asset_sha256=?', (row['sha256'],))]
            years = sorted({str(y) for r in refs for y in (r.get('years') or [])})
            stages = sorted({str(r.get('stage_documentaire')) for r in refs if r.get('stage_documentaire')})
            items.append(dict(row) | {'pages':json.loads(row['receipt_json'])['counts']['pages'],
                 'context':'Étapes documentaires : '+', '.join(stages)+'. Années documentaires : '+', '.join(years)+'. Les années des montants doivent être vérifiées dans les en-têtes.'})
    finally:
        con.close()
    if limit:
        items = items[:limit]
    with single_instance(stage_root/'staging.lock'):
        atomic_json(stage_root/'staging_contract.json', {'version':VERSION, 'code':code, 'contract':contract,
                    'snapshot':str(snapshot), 'config':config, 'gpu_launched':False})
        started = time.monotonic()
        completed, errors, pending = [], [], iter(items)
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {}
            def submit_one():
                item = next(pending, None)
                if item is not None:
                    futures[pool.submit(document_job, item, settings)] = item
            for _ in range(workers):
                submit_one()
            while futures:
                done, _ = wait(futures, timeout=15, return_when=FIRST_COMPLETED)
                for future in done:
                    item = futures.pop(future)
                    try:
                        completed.append(future.result())
                    except Exception as exc:
                        errors.append({'source_sha256':item['sha256'], 'error':type(exc).__name__+': '+str(exc)})
                    submit_one()
                totals = {k:sum(r[k] for r in completed) for k in
                          ('pages','grid_alert_pages','review_pages','table_candidates','chunks','tokens','bytes')}
                status = {'phase':'staging', 'complete':False, 'documents_complete':len(completed),
                          'documents_expected':len(items), **totals, 'errors':errors,
                          'active':[{'sha256':i['sha256'], 'file':i['path']} for i in futures.values()],
                          'elapsed_seconds':round(time.monotonic()-started, 1),
                          'source_modified':False, 'gpu_launched':False}
                atomic_json(stage_root/'status.json', status)
        status.update(phase='staged', complete=len(completed)==len(items) and not errors, active=[])
        atomic_json(stage_root/'status.json', status)
        atomic_json(stage_root/'receipts.json', completed)
        print(canonical(status), flush=True)
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=SNAPSHOT)
    parser.add_argument('--preparation', type=Path, default=PREPARATION)
    parser.add_argument('--stage', type=Path, default=STAGE)
    parser.add_argument('--workers', type=int, default=2, choices=range(1,5))
    parser.add_argument('--sha', action='append')
    parser.add_argument('--limit', type=int, default=0)
    args = parser.parse_args()
    stage(args.snapshot, args.preparation, args.stage, args.workers, args.sha, args.limit)


if __name__ == '__main__':
    main()
