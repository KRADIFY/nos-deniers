"""Publish a new incremental input with Nos Deniers evidence; no GPU or live writes."""
from pathlib import Path
import sys,json,gzip,hashlib,sqlite3,collections,importlib.util,re,os,datetime
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import prepare_complement_final_contract as prep
B=prep.BUNDLE;O=prep.OUT

def canonical(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def h(s):return hashlib.sha256(s.encode()).hexdigest()
def save(p,v):prep.save(p,v)
def boundary_errors(chunks):
 fields=collections.defaultdict(list)
 for c in chunks:
  for s in c.get('segments',[]):fields[(c.get('table_ref',''),s.get('field_ref',s.get('block')))].append(s)
 errors=[]
 for key,segs in fields.items():
  for a,b in zip(segs,segs[1:]):
   if a['text'] and b['text'] and not (a['text'][-1].isspace() or b['text'][0].isspace()):errors.append(key)
 return errors

def fix_table_boundaries(obj,tk,serializer):
 bad={ref for ref,field in boundary_errors(obj['chunks'])}
 if not bad:return obj['chunks'],[]
 if '' in bad:raise ValueError('In-word source block boundary: '+obj['record']['locator'])
 tables={t['table_ref']:t for t in obj['record'].get('review',{}).get('tables',[])}
 replacements={ref:serializer(tables[ref]['table'],tables[ref]['context'],tk)['chunks'] for ref in bad}
 chunks=[];seen=set()
 for c in obj['chunks']:
  ref=c.get('table_ref')
  if ref not in bad:chunks.append(c);continue
  if ref in seen:continue
  seen.add(ref)
  for x in replacements[ref]:
   x.update({k:c[k] for k in ('page','page_label','paragraph_number_kind','record_ref','kind') if k in c})
   x['quality']=c['quality']|x['quality'];chunks.append(x)
 assert not boundary_errors(chunks)
 return chunks,sorted(bad)

def db_schema(c):
 c.executescript('''PRAGMA journal_mode=DELETE; PRAGMA synchronous=FULL; PRAGMA foreign_keys=ON;
 CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS assets(sha256 TEXT PRIMARY KEY,path TEXT NOT NULL,bytes INTEGER NOT NULL,kind TEXT NOT NULL,policy TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS refs(id TEXT PRIMARY KEY,asset_sha256 TEXT NOT NULL,partition TEXT NOT NULL,metadata_json TEXT NOT NULL,FOREIGN KEY(asset_sha256) REFERENCES assets(sha256));
 CREATE TABLE IF NOT EXISTS asset_quality(asset_sha256 TEXT PRIMARY KEY,source_kind TEXT NOT NULL,table_layout TEXT NOT NULL,numeric_status TEXT NOT NULL,allow_automatic_numeric_fact INTEGER NOT NULL CHECK(allow_automatic_numeric_fact=0),origin TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS source_precedence(old_sha256 TEXT PRIMARY KEY,preferred_sha256 TEXT NOT NULL,reason TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS passages(id TEXT PRIMARY KEY,partition TEXT NOT NULL,body_sha256 TEXT NOT NULL,text TEXT NOT NULL,tokens INTEGER NOT NULL,embedding_route TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS occurrences(id TEXT PRIMARY KEY,passage_id TEXT NOT NULL,asset_sha256 TEXT NOT NULL,locator TEXT NOT NULL,section TEXT,kind TEXT NOT NULL,FOREIGN KEY(passage_id) REFERENCES passages(id));
 CREATE INDEX IF NOT EXISTS occurrences_passage ON occurrences(passage_id);
 CREATE TABLE IF NOT EXISTS evidence(id TEXT PRIMARY KEY,asset_sha256 TEXT NOT NULL,record_no INTEGER NOT NULL,locator TEXT NOT NULL,kind TEXT NOT NULL,table_no INTEGER,summary_json TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS occurrence_proof(occurrence_id TEXT PRIMARY KEY,evidence_id TEXT NOT NULL,chunk_json TEXT NOT NULL,quality_json TEXT NOT NULL,FOREIGN KEY(evidence_id) REFERENCES evidence(id),FOREIGN KEY(occurrence_id) REFERENCES occurrences(id));
 CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY,source_id TEXT NOT NULL,record_no INTEGER NOT NULL,record_json TEXT NOT NULL,staged_file TEXT NOT NULL,staged_sha256 TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS page_reviews(asset_sha256 TEXT NOT NULL,page INTEGER NOT NULL,record_ref TEXT NOT NULL,method TEXT NOT NULL,issues_json TEXT NOT NULL,table_count INTEGER NOT NULL,review_required INTEGER NOT NULL,PRIMARY KEY(asset_sha256,page));
 CREATE TABLE IF NOT EXISTS completed_documents(source_id TEXT PRIMARY KEY,receipt_json TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS boundary_corrections(evidence_id TEXT NOT NULL,table_ref TEXT NOT NULL,reason TEXT NOT NULL,PRIMARY KEY(evidence_id,table_ref));
 ''')

def export():
 tk=prep.config();sources=prep.SOURCES;external=json.loads((O/'external_routes.json').read_text('utf-8'));external={r['source_id']:r for r in external}
 code=O/'code/vectorisation_table_text_word_safe.py';spec=importlib.util.spec_from_file_location('word_safe_table',code);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 c=sqlite3.connect(O/'catalogue.sqlite');db_schema(c)
 identity=h(prep.CONTRACT_ID+prep.sha(code)+prep.sha(Path(__file__)))
 old=dict(c.execute('select key,value from metadata'))
 if old and old.get('preparation_identity')!=identity:raise ValueError('Existing export belongs to another implementation; preserve it')
 c.execute('insert or ignore into metadata values(?,?)',('preparation_identity',identity));c.commit()
 completed={r[0] for r in c.execute('select source_id from completed_documents')}
 pending=[]
 for r in sources:
  sid=r['id'];route='existing_cour' if sid in external else 'bge_m3_new' if r['action']=='index' and r['source_tier']=='official' else 'internal_hold' if r['action'] in ('index','context_only') else r['action']
  partition='public' if route=='bge_m3_new' else 'existing_external' if route=='existing_cour' else 'internal' if route=='internal_hold' else 'not_exported'
  meta=r|dict(source_metadata=r,embedding_route=route,existing_external=external.get(sid))
  with c:
   c.execute('insert or ignore into assets values(?,?,?,?,?,?)',(r['sha256'],r['path'],r['bytes'],r['format'],route)) if False else c.execute('insert or ignore into assets values(?,?,?,?,?)',(r['sha256'],r['path'],r['bytes'],r['format'],route))
   c.execute('insert or ignore into refs values(?,?,?,?)',(sid,r['sha256'],partition,canonical(meta)))
   c.execute('insert or ignore into asset_quality values(?,?,?,?,?,?)',(r['sha256'],'source_'+r['format'] if r['source_tier']=='official' else 'internal_'+r['format'],'candidate_not_certified','raw_not_validated_facts',0,'incremental_final_contract'))
  if route not in ('bge_m3_new','internal_hold','existing_cour') or sid in completed:continue
  path=O/'documents'/(sid+'.jsonl.gz');rp=path.with_suffix('.receipt.json')
  if not rp.exists():pending.append(sid);continue
  receipt=json.loads(rp.read_text('utf-8'));assert prep.sha(path)==receipt['sha256'];assert receipt['contract_id']==prep.CONTRACT_ID
  counts=collections.Counter()
  with c,gzip.open(path,'rt',encoding='utf-8') as f:
   for ln in f:
    obj=json.loads(ln);rec=obj['record'];chunks,corrected=fix_table_boundaries(obj,tk,m.serialize_table)
    # Repeated chunks inside the extraction record are redundant; original stage remains immutable.
    rec=dict(rec)
    if 'review' in rec:rec['review']={k:v for k,v in rec['review'].items() if k not in ('chunks','raw_segments')}
    encoded=canonical(rec);ref=h(encoded);record_no=rec['record_number'];loc=rec['locator'];kind=rec['kind']
    c.execute('insert into records values(?,?,?,?,?,?)',(ref,sid,record_no,encoded,str(path.relative_to(O)),receipt['sha256']))
    proof=dict(record_ref=ref,upstream_record_ref=obj['record_ref'],quality=obj['quality'],source_url=r['url'],title=r['title'],source_sha256=r['sha256'],document_year_candidates=r.get('years_title',[]),year_scope='document_not_amount',stage_documentaire=r.get('stage'),amount_dimensions='consult_raw_headers_no_automatic_assignment',physical_page=rec.get('page'),printed_page_label=rec.get('page_label'),sheet=rec.get('sheet'),row_start=rec.get('row_start'),allow_automatic_numeric_fact=False)
    c.execute('insert into evidence values(?,?,?,?,?,?,?)',(ref,r['sha256'],record_no,loc,kind,None,canonical(proof)))
    for tr in corrected:c.execute('insert into boundary_corrections values(?,?,?)',(ref,tr,'Word-boundary resegmentation of this table only; source characters unchanged'))
    if kind=='page':
     assert rec['page']==counts['pages']+1
     review=rec.get('review',{});issues=rec.get('issues',[])
     c.execute('insert into page_reviews values(?,?,?,?,?,?,?)',(r['sha256'],rec['page'],ref,rec['method'],canonical(issues),len(review.get('tables',[])),int(bool(issues) or bool(review.get('review_required')) or rec['method'].startswith('ocr'))))
     counts['pages']+=1
    for no,ch in enumerate(chunks):
     assert ch['quality']['allow_automatic_numeric_fact'] is False and 0<ch['tokens']<=800
     ident=h(partition+'\n'+ch['text']);bodysha=h(ch.get('body',ch['text']));occ=h(ref+'\n'+str(no)+'\n'+ident)
     c.execute('insert or ignore into passages values(?,?,?,?,?,?)',(ident,partition,bodysha,ch['text'],ch['tokens'],route))
     c.execute('insert into occurrences values(?,?,?,?,?,?)',(occ,ident,r['sha256'],ch['locator'],rec.get('section') or rec.get('sheet'),ch.get('kind',kind)))
     ch=dict(ch,record_ref=ref,upstream_record_ref=ch.get('record_ref'));c.execute('insert into occurrence_proof values(?,?,?,?)',(occ,ref,canonical(ch),canonical(ch['quality'])))
     counts['chunks']+=1
    counts['records']+=1
   assert counts['records']==receipt['records']
   c.execute('insert into completed_documents values(?,?)',(sid,canonical(receipt|dict(export_counts=dict(counts),route=route))))
  print(json.dumps(dict(exported=sid,route=route,**counts)),flush=True)
 if pending:
  save(O/'export_status.json',dict(state='waiting_for_staged_documents',pending=pending));c.close();return
 out=O/'gpu_input';out.mkdir(exist_ok=True)
 counts={}
 for partition,name in [('public','public.bge-m3.jsonl'),('internal','internal.held.jsonl')]:
  path=out/name;part=path.with_suffix('.partial');n=t=0
  with part.open('w',encoding='utf-8',newline='\n') as f:
   for ident,text,tokens in c.execute('select id,text,tokens from passages where partition=? order by id',(partition,)):
    f.write(canonical(dict(id=ident,text=text,tokens=tokens))+'\n');n+=1;t+=tokens
  os.replace(part,path);counts[partition]=dict(count=n,tokens=t,bytes=path.stat().st_size,sha256=prep.sha(path),input=str(path.relative_to(O)))
 c.execute('insert or replace into metadata values(?,?)',('state','exported_pending_independent_validation'));c.commit()
 assert c.execute('pragma integrity_check').fetchone()[0]=='ok';assert c.execute('pragma foreign_key_check').fetchone() is None
 doccounts=dict(c.execute('select partition,count(*) from refs group by partition'))
 corrections=c.execute('select count(*) from boundary_corrections').fetchone()[0]
 c.close()
 save(O/'export_status.json',dict(state='exported_pending_independent_validation',partitions=counts,documents=doccounts,table_boundary_corrections=corrections,preparation_identity=identity,base_reencoded=0,gpu_launched=False))
 print(canonical(dict(export_complete=True,partitions=counts,documents=doccounts,table_boundary_corrections=corrections)),flush=True)

if __name__=='__main__':export()
