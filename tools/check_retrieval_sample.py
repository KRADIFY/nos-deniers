"""Small deterministic retrieval check against original RunPod vectors."""
from pathlib import Path
import json,sqlite3,time,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.runtime/retrieval-libs'))
import faiss,numpy as np
root=Path('D:/LexMachine/NosDeniers/search_20260919')
parts=Path('F:/LexMachine/NosDeniers/generation_tables_20260911/runpod_bge_m3_20260912/parts/lexmachine-nos-deniers-5089bcdcd395-h100-r1')
faiss.omp_set_num_threads(2)
t=time.monotonic();idx=faiss.read_index(str(root/'dense.faiss'));idx.nprobe=64
rows=[]
for number in [0,123,247,370,494]:
 p=parts/f'part-{number:06d}.sqlite';con=sqlite3.connect(p.as_uri()+'?mode=ro&immutable=1',uri=True)
 for seq,vec in con.execute('SELECT seq,dense FROM vectors ORDER BY seq LIMIT 3 OFFSET 59'):
  v=np.frombuffer(vec,dtype='<f2').astype('float32')[None,:];scores,ids=idx.search(v,20)
  rows.append(dict(seq=seq+1,self_in_top20=int(seq+1) in ids[0],best_score=float(scores[0][0]),best_id=int(ids[0][0])))
 con.close()
report=dict(index_vectors=idx.ntotal,dimension=idx.d,sample=len(rows),self_in_top20=sum(r['self_in_top20'] for r in rows),seconds=round(time.monotonic()-t,2),checks=rows,scope='15 deterministic self-retrieval samples; not exhaustive recall certification')
Path('reports/finalisation-20260919/vector-recall-sample.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report,indent=2))