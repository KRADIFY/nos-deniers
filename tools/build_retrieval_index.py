"""Build a resumable public search index from completed RunPod parts, without encoding.

Each part is SHA checked, matched to the exact public catalogue text, committed
independently and indexed with the same trained IVF/SQ8 quantizer. Source files
are never changed. Quantization changes retrieval ranking only, never amounts.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from budget_service.retrieval_contract import VERSION, MODEL, REVISION, DIMENSION, read_db, digest, write_json
from tools.export_document_search import public_citation, budget_sources


def progress(out, phase, **values):
    item = dict(at=datetime.now(timezone.utc).isoformat(), phase=phase, **values)
    write_json(out/'progress.json', item)
    stamp=datetime.now().astimezone().strftime('%d/%m/%Y %H:%M:%S')
    count=values.get('completed',0); total=values.get('expected',values.get('vectors',0))
    text=f'{stamp} - {phase}\nPassages : {count:,} / {total:,}\n'.replace(',', ' ')
    (out/'ETAT.txt').write_text(text+'Reprise : relancer LANCER_INDEX_NOS_DENIERS.cmd. Aucun calcul RunPod.\n',encoding='utf-8')
    print(json.dumps(item, ensure_ascii=False), flush=True)


def schema(db):
    db.executescript('''
        PRAGMA journal_mode=DELETE;
        PRAGMA synchronous=FULL;
        PRAGMA temp_store=MEMORY;
        CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS parts(name TEXT PRIMARY KEY,sha256 TEXT NOT NULL,count INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS passages(seq INTEGER PRIMARY KEY,id TEXT UNIQUE NOT NULL,
          text TEXT NOT NULL,tokens INTEGER NOT NULL,text_sha256 TEXT NOT NULL,
          sparse_ids BLOB NOT NULL,sparse_weights BLOB NOT NULL);
        CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY,reference_id TEXT UNIQUE NOT NULL,
          source_sha256 TEXT NOT NULL,source_id TEXT NOT NULL,title TEXT NOT NULL,url TEXT NOT NULL,
          format TEXT NOT NULL,years_key TEXT NOT NULL,stage TEXT NOT NULL,source_kind TEXT NOT NULL,
          table_layout TEXT NOT NULL,numeric_status TEXT NOT NULL,local_available INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS citations(seq INTEGER NOT NULL,document_id INTEGER NOT NULL,
          locator TEXT NOT NULL,PRIMARY KEY(seq,document_id,locator));
        CREATE INDEX IF NOT EXISTS document_citations ON citations(document_id,seq);
        CREATE VIRTUAL TABLE IF NOT EXISTS passages_fts USING fts5(text,
          content='passages',content_rowid='seq',tokenize='unicode61 remove_diacritics 2');
    ''')


def check_vectors(rows, np):
    dense = np.vstack([np.frombuffer(r['dense'], dtype='<f2') for r in rows]).astype('float32')
    if dense.shape != (len(rows),DIMENSION) or not np.isfinite(dense).all():
        raise ValueError('Invalid dense vectors')
    if not np.all(np.abs(np.linalg.norm(dense,axis=1)-1) < .006):
        raise ValueError('Dense vectors are not normalized')
    for r in rows:
        ids=np.frombuffer(r['sparse_ids'],dtype='<i4')
        weights=np.frombuffer(r['sparse_weights'],dtype='<f4')
        if len(ids)!=r['nnz'] or len(weights)!=r['nnz'] or len(set(ids))!=len(ids) or not np.isfinite(weights).all() or (weights<0).any() or (ids<0).any():
            raise ValueError('Invalid sparse vector')
    return dense


def build(args):
    import numpy as np
    import faiss
    faiss.omp_set_num_threads(args.threads)
    out=args.output.resolve(); out.mkdir(parents=True,exist_ok=True)
    (out/'shards').mkdir(exist_ok=True)
    receipt=json.loads((args.run/'LOCAL_BACKUP_VERIFIED.json').read_text())
    terminal=receipt['terminal']; parts=terminal['parts']
    expected=receipt['verified_count']; identity=receipt['input_sha256']
    if terminal['status']!='complete' or terminal['unpublished_rows'] or terminal['produced_count']!=expected:
        raise ValueError('Incomplete RunPod receipt')
    ready=out/'manifest.json'
    if ready.exists():
        saved=json.loads(ready.read_text(encoding='utf-8'))
        if saved.get('state')=='ready' and saved.get('input_sha256')==identity and saved.get('passages')==expected and all((out/f['path']).stat().st_size==f['bytes'] for f in saved['files']):
            progress(out,'complete',completed=expected,expected=expected,already_complete=True)
            return
    current=0
    for p in parts:
        if p['start_line']!=current or p['end_line']-current!=p['count'] or p['input_sha256']!=identity or Path(p['file']).name!=p['file']:
            raise ValueError('Non-contiguous or mixed generation')
        current=p['end_line']
    if current!=expected: raise ValueError('Coverage mismatch')
    part_dir=args.run/'parts'/terminal['job_name']
    db=sqlite3.connect(out/'search.sqlite'); db.row_factory=sqlite3.Row; schema(db)
    old=dict(db.execute('SELECT key,value FROM metadata'))
    if old and (old.get('input_sha256')!=identity or old.get('version')!=VERSION):
        raise ValueError('Output belongs to another generation')
    db.executemany('INSERT OR REPLACE INTO metadata VALUES(?,?)', [('input_sha256',identity),('version',VERSION),('state','building')]);db.commit()
    source=read_db(args.catalogue)
    local,ids=budget_sources(args.budget)
    superseded={r[0] for r in source.execute('SELECT old_sha256 FROM source_precedence')}
    quality={r['asset_sha256']:dict(r) for r in source.execute('SELECT * FROM asset_quality')}
    references={}
    for r in source.execute("SELECT * FROM refs WHERE partition='public' ORDER BY id"):
        sha=r['asset_sha256']
        if sha in superseded: continue
        if sha not in quality: raise ValueError('Missing public source qualification')
        c=public_citation(r['metadata_json'],sha,'',quality[sha],local,ids)
        fields=['source_id','title','url','format','years_key','stage','source_kind','table_layout','numeric_status','local_available']
        db.execute('INSERT OR IGNORE INTO documents(reference_id,source_sha256,'+','.join(fields)+') VALUES('+','.join('?' for _ in range(12))+')',[r['id'],sha]+[c[k] for k in fields])
        docid=db.execute('SELECT id FROM documents WHERE reference_id=?',(r['id'],)).fetchone()[0]
        references.setdefault(sha,[]).append(docid)
    db.commit()
    trained=out/'trained.faiss'
    if not trained.exists():
        progress(out,'training_search_index',vectors=expected,encoding=False)
        samples=[]
        for part_number,p in enumerate(parts):
            with closing(read_db(part_dir/p['file'])) as con:
                meta=dict(con.execute('SELECT key,value FROM metadata'))
                if meta.get('model')!=MODEL or meta.get('revision')!=REVISION or meta.get('input_sha256')!=identity:
                    raise ValueError('Model or input mismatch')
                positions=list(range(p['start_line'],p['end_line'],64))
                samples.extend(np.frombuffer(r[0],dtype='<f2') for r in con.execute('SELECT dense FROM vectors WHERE seq IN ('+','.join('?' for _ in positions)+')',positions))
            if part_number%20==0:progress(out,'sampling',completed=part_number+1,expected=len(parts),encoding=False)
        sample=np.asarray(samples,dtype='float32'); del samples
        progress(out,'training_search_index',sample_vectors=len(sample),vectors=expected,encoding=False)
        nlist=min(1024,max(1,len(sample)//48))
        index=faiss.IndexIVFScalarQuantizer(faiss.IndexFlatIP(DIMENSION),DIMENSION,nlist,faiss.ScalarQuantizer.QT_8bit,faiss.METRIC_INNER_PRODUCT)
        index.cp.niter=12;index.cp.seed=20260919
        index.train(sample);faiss.write_index(index,str(trained));del sample,index
    complete=dict(db.execute('SELECT name,sha256 FROM parts'))
    for p in parts:
        name=p['file']; shard=out/'shards'/(name+'.faiss')
        if name in complete:
            if complete[name]!=p['sha256'] or not shard.is_file(): raise ValueError('Inconsistent checkpoint')
            continue
        path=part_dir/name
        if digest(path)!=p['sha256']: raise ValueError('Part hash mismatch: '+name)
        with closing(read_db(path)) as con:
            meta=dict(con.execute('SELECT key,value FROM metadata'))
            if meta.get('model')!=MODEL or meta.get('revision')!=REVISION or meta.get('input_sha256')!=identity:
                raise ValueError('Part model mismatch')
            rows=con.execute('SELECT * FROM vectors ORDER BY seq').fetchall()
        if len(rows)!=p['count'] or [r['seq'] for r in rows]!=list(range(p['start_line'],p['end_line'])):
            raise ValueError('Wrong sequence range')
        dense=check_vectors(rows,np)
        index=faiss.read_index(str(trained));index.add_with_ids(dense,np.array([r['seq']+1 for r in rows],dtype='int64'))
        temp=shard.with_suffix('.tmp');faiss.write_index(index,str(temp));temp.replace(shard)
        del dense,index
        with db:
            for start in range(0,len(rows),400):
                batch=rows[start:start+400]; by_id={r['chunk_id']:r for r in batch}
                placeholders=','.join('?' for _ in batch)
                retrieved=source.execute('SELECT id,text,tokens,partition FROM passages WHERE id IN ('+placeholders+')',list(by_id)).fetchall()
                if len(retrieved)!=len(batch): raise ValueError('Missing source text')
                for r in retrieved:
                    v=by_id[r['id']]
                    if r['partition']!='public' or hashlib.sha256(r['text'].encode()).hexdigest()!=v['text_sha256']:
                        raise ValueError('Public text/hash mismatch')
                    db.execute('INSERT INTO passages VALUES(?,?,?,?,?,?,?)',(v['seq']+1,r['id'],r['text'],r['tokens'],v['text_sha256'],v['sparse_ids'],v['sparse_weights']))
                    db.execute('INSERT INTO passages_fts(rowid,text) VALUES(?,?)',(v['seq']+1,r['text']))
                cited=set()
                for occ in source.execute('SELECT passage_id,asset_sha256,locator FROM occurrences WHERE passage_id IN ('+placeholders+')',list(by_id)):
                    for docid in references.get(occ['asset_sha256'],[]):
                        seq=by_id[occ['passage_id']]['seq']+1
                        db.execute('INSERT OR IGNORE INTO citations VALUES(?,?,?)',(seq,docid,occ['locator']))
                        cited.add(occ['passage_id'])
                if cited!=set(by_id): raise ValueError('Passage without active public citation')
            db.execute('INSERT INTO parts VALUES(?,?,?)',(name,p['sha256'],p['count']))
        progress(out,'indexing',completed=p['end_line'],expected=expected,part=name,encoding=False)
    index_path=out/'dense.faiss'
    if not index_path.exists():
        progress(out,'merging_search_index',completed=expected,expected=expected)
        index=faiss.read_index(str(trained))
        for p in parts:
            shard=faiss.read_index(str(out/'shards'/(p['file']+'.faiss')))
            index.merge_from(shard,0)
        if index.ntotal!=expected: raise ValueError('Dense count mismatch')
        index.nprobe=min(64,index.nlist)
        faiss.write_index(index,str(out/'dense.faiss.tmp')); (out/'dense.faiss.tmp').replace(index_path)
        del index
    if db.execute('SELECT count(*) FROM passages').fetchone()[0]!=expected: raise ValueError('Text count mismatch')
    documents=db.execute('SELECT count(DISTINCT document_id) FROM citations').fetchone()[0]
    with db:
        db.executemany('INSERT OR REPLACE INTO metadata VALUES(?,?)', [('state','ready'),('passage_count',str(expected)),('document_count',str(documents))])
    db.close();source.close()
    manifest=dict(version=VERSION,state='ready',input_sha256=identity,model=MODEL,revision=REVISION,dimension=DIMENSION,
        passages=expected,documents=documents,quantization='IVF/SQ8',sparse='candidate_reranking',
        numeric_facts_certified=False,generated_at=datetime.now(timezone.utc).isoformat(),files=[])
    progress(out,'checksums',completed=expected,expected=expected)
    for name in ['search.sqlite','dense.faiss']:
        path=out/name
        manifest['files'].append(dict(path=name,bytes=path.stat().st_size,sha256=digest(path)))
    write_json(out/'manifest.json',manifest)
    progress(out,'complete',completed=expected,expected=expected,files=manifest['files'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['run','catalogue','budget','output']:parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--threads',type=int,default=4)
    build(parser.parse_args())
