"""Incremental Nos Deniers preparation under the final source/table evidence contract.
Uses the original extractor, positioned text reader and table reconstruction modules.
Never opens active numerical or vector stores for writing and never starts RunPod.
"""
from pathlib import Path
import sys,json,hashlib,gzip,sqlite3,collections,re,io,csv,zipfile,os,time,datetime,argparse
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
BUNDLE=ROOT/'consolidation-vectorisation-20260924'
OUT=BUNDLE/'preparation-conforme'
OLD=Path(r'C:\Users\Jean-Christophe\Documents\ChatGPT\Mises à jour auto\nos_deniers_preparation_20260909')
sys.path.insert(0,str(OLD));sys.path.insert(0,str(OLD/'_deps'));sys.path.insert(0,str(ROOT/'tools'))
import extractors
from tokenizers import Tokenizer
from prepare_vectorisation_tables import page_payload,raw_chunks
from vectorisation_table_text import serialize_table
CFG=json.loads((OLD/'config.json').read_text('utf-8'))
SOURCES=json.loads((BUNDLE/'_controle/sources.json').read_text('utf-8'))

def dump(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),default=str)
def hashtext(s):return hashlib.sha256(s.encode()).hexdigest()
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);t=p.with_name(p.name+'.partial');t.write_text(dump(v)+'\n','utf-8');os.replace(t,p)
def config():
 assert sha(CFG['tokenizer'])==CFG['tokenizer_sha256']
 tk=Tokenizer.from_file(CFG['tokenizer']);tk.no_truncation();tk.no_padding();return tk

def natural_chunks(tk,context,blocks):
 """Whole blocks first; split oversized blocks at spaces, preserving exact characters."""
 context=context.strip()
 while len(tk.encode(context+'\n\n').ids)>100:
  if ' ' not in context:raise ValueError('Context has an oversized unsplittable word')
  context=context.rsplit(' ',1)[0]
 prefix=context+'\n\n';pending=[];result=[]
 def text(items):return prefix+'\n\n'.join(x['text'] for x in items)
 def fits(items):return len(tk.encode(text(items)).ids)<=800
 def flush():
  if not pending:return
  t=text(pending);result.append(dict(text=t,body='\n\n'.join(x['text'] for x in pending),tokens=len(tk.encode(t).ids),segments=[dict(x) for x in pending]));pending.clear()
 for bi,body in enumerate(blocks):
  if not body:continue
  whole=dict(block=bi,char_start=0,char_end=len(body),text=body)
  if fits(pending+[whole]):pending.append(whole);continue
  flush()
  if fits([whole]):pending.append(whole);continue
  start=0
  while start<len(body):
   low,high,end=start+1,len(body),None
   while low<=high:
    trial=(low+high)//2;item=dict(whole,char_start=start,char_end=trial,text=body[start:trial])
    if fits([item]):end=trial;low=trial+1
    else:high=trial-1
   if end is None:raise ValueError('A character exceeds the token budget')
   if end<len(body):
    spaces=list(re.finditer(r'\s+',body[start:end]))
    if not spaces:raise ValueError('An indivisible word exceeds the token budget; no truncation allowed')
    end=start+spaces[-1].end()
   pending.append(dict(whole,char_start=start,char_end=end,text=body[start:end]));flush();start=end
 flush()
 recovered=['' for x in blocks]
 for ch in result:
  assert 0<ch['tokens']<=800
  for s in ch['segments']:
   assert len(recovered[s['block']])==s['char_start'];recovered[s['block']]+=s['text']
 assert recovered==blocks,'Source character omitted or duplicated'
 return result

def quality(r,kind):
 return dict(source_kind=('internal_workbook' if r['source_tier']=='working' else 'internal_context' if r['source_tier']=='internal' else 'source_'+r['format']),table_layout=('candidate_not_certified' if 'table' in kind else 'positioned_source' if r['format']=='pdf' else 'original_structure_retained'),numeric_status='raw_not_validated_facts',allow_automatic_numeric_fact=False,source_tier=r['source_tier'],header_status='source_candidates_not_certified')

def context(r,section=''):
 return ('Nos Deniers. '+('Source officielle' if r['source_tier']=='official' else 'Référence interne non officielle')+'. Années documentaires : '+', '.join(map(str,r.get('years_title',[])))+'. Étape documentaire : '+r.get('stage','non établie')+'. '+section)

def doc_records(p):
 W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
 with zipfile.ZipFile(p) as z:root=ET.fromstring(z.read('word/document.xml'))
 body=root.find(W+'body');para=table=0
 for child in body:
  if child.tag==W+'p':
   para+=1;txt=''.join(x.text or '' for x in child.iter(W+'t'))
   if txt:yield dict(kind='text',locator=f'paragraph:{para}',text=txt,paragraph_number_kind='document_xml_order')
  elif child.tag==W+'tbl':
   table+=1;rows=[];spans=[]
   for i,tr in enumerate(child.findall(W+'tr'),1):
    row=[]
    for j,tc in enumerate(tr.findall(W+'tc'),1):
     row.append('\n'.join(''.join(x.text or '' for x in p0.iter(W+'t')) for p0 in tc.findall(W+'p')))
     pr=tc.find(W+'tcPr');spans.append(dict(row=i,column=j,xml=ET.tostring(pr,encoding='unicode') if pr is not None else ''))
    rows.append(row)
   yield dict(kind='table',locator=f'table:{table}',rows=rows,spans=spans,column_alignment='ooxml_grid_retained')

def tab_text(record,headers):
 lines=[]
 for rowno,row in enumerate(record['rows'],record.get('row_start',1)):
  vals=[]
  for col,val in enumerate(row,1):
   state='[ABSENT NULL]' if val is None else '[VIDE chaîne vide]' if val=='' else dump(val) if isinstance(val,(dict,list)) else str(val)
   label=str(headers[col-1]) if col<=len(headers) else ''
   vals.append(f'Colonne {col}'+(f' [en-tête candidat {label}]' if label else '')+' : '+state)
  lines.append(f'Ligne {rowno}. '+' | '.join(vals))
 return lines

def records_for(r):
 p=BUNDLE/r['path'];fmt=r['format']
 if fmt=='html':yield from extractors.html_records(p)
 elif fmt=='xls':yield from extractors.xls_records(p)
 elif fmt=='xlsx':yield from extractors.xlsx_records(p)
 elif fmt in ('doc','docx'):
  yield from doc_records(BUNDLE/'05_extractions/documents-convertis'/(r['id']+'.docx') if fmt=='doc' else p)
 elif fmt=='csv':
  raw=sqlite3.connect((BUNDLE/'05_extractions/tableaux.sqlite').as_uri()+'?mode=ro',uri=True)
  headers,enc,sep=raw.execute('select headers_json,encoding,delimiter from csv_headers where source_id=?',(r['id'],)).fetchone();headers=json.loads(headers)
  yield dict(kind='structure',locator='csv:headers',headers=headers,encoding=enc,delimiter=sep)
  for row,fields in raw.execute('select row,fields_json from csv_rows where source_id=? order by row',(r['id'],)):
   yield dict(kind='table',locator=f'csv:row:{row}',rows=[json.loads(fields)],row_start=row,header={'names':headers},header_status='literal_csv_column_names',encoding=enc,delimiter=sep)
  raw.close()
 else:raise ValueError(fmt)

def stage_document(r):
 import fitz
 tk=config();sid=r['id'];out=OUT/'documents'/(sid+'.jsonl.gz');receipt=out.with_suffix('.receipt.json')
 if receipt.exists():
  old=json.loads(receipt.read_text('utf-8'))
  assert old['contract_id']==CONTRACT_ID and old['sha256']==sha(out),'A staged file changed'
  return old
 assert sha(BUNDLE/r['path'])==r['sha256'];out.parent.mkdir(parents=True,exist_ok=True)
 temp=out.with_name(out.name+'.partial');counts=collections.Counter();heads={};started=time.time()
 def write(stream,rec,chunks):
  no=counts['records']+1;loc=rec.get('locator') or f'paragraph:{no}'
  rec=dict(rec,locator=loc,record_number=no,source_sha256=r['sha256'],source_id=sid)
  q=quality(r,rec['kind']);ref=hashtext(r['sha256']+'\n'+loc+'\n'+dump(rec))
  for n,c in enumerate(chunks,1):
   c['locator']=c.get('locator') or loc+f'/part:{n}'
   c['quality']=q|c.get('quality',{})
   assert c['quality']['allow_automatic_numeric_fact'] is False
   c['record_ref']=ref;assert c['tokens']==len(tk.encode(c['text']).ids)<=800
  stream.write(dump(dict(record_ref=ref,record=rec,chunks=chunks,quality=q))+'\n')
  counts['records']+=1;counts['chunks']+=len(chunks);counts['tokens']+=sum(c['tokens'] for c in chunks)
  if counts['records']%250==0:
   save(OUT/'progress.json',dict(source=sid,format=r['format'],**counts,elapsed=round(time.time()-started,1),gpu_launched=False))
 with gzip.open(temp,'wt',encoding='utf-8',compresslevel=3) as f:
  if r['format']=='pdf':
   doc=fitz.open(BUNDLE/r['path'])
   try:
    for rec in extractors.pdf_records(BUNDLE/r['path'],CFG):
     counts['pages']+=1
     payload=page_payload(rec,doc[rec['page']-1],r['sha256'],tk,context(r))
     if payload['review_required']:
      chunks=payload['chunks'];rec=dict(rec,review=payload,locator=f'page:{rec["page"]}')
      counts['table_review_pages']+=1;counts['tables']+=len(payload['tables'])
     else:
      chunks=raw_chunks(rec,r['sha256'],tk);rec=dict(rec,locator=f'page:{rec["page"]}')
     # Retain both all positioned source text and any reconstructed table; never inside_table filtering.
     counts['ocr_pages']+=rec['method'].startswith('ocr')
     if rec.get('issues'):counts['pages_with_alerts']+=1
     for c in chunks:
      c['page']=rec['page'];c['page_label']=rec.get('page_label');c['paragraph_number_kind']='extractor_block_order_not_official_number'
      c.setdefault('quality',quality(r,c.get('kind','page_source_text')))
     write(f,rec,chunks)
   finally:doc.close()
  else:
   for no,rec in enumerate(records_for(r),1):
    kind=rec['kind'];section=rec.get('section') or rec.get('sheet') or ''
    if kind=='structure':write(f,rec,[]);continue
    if kind=='table':
     sheet=rec.get('sheet','');candidates=heads.setdefault(sheet,[]) if r['format'] in ('xls','xlsx') else []
     if len(candidates)<5:candidates.extend(rec['rows'][:5-len(candidates)])
     names=rec.get('header',{}).get('names') or []
     if not names and candidates:
      names=[' / '.join(str(row[c]) for row in candidates if c<len(row) and row[c] is not None)[:120] for c in range(max(map(len,candidates)))]
     rec=dict(rec,header_candidates=names,header_assignment='candidate_not_certified',null_is_not_zero=True)
     chunks=natural_chunks(tk,context(r,section),tab_text(rec,names));counts['table_rows']+=len(rec['rows'])
    else:chunks=natural_chunks(tk,context(r,section),[rec['text']])
    write(f,rec,chunks)
 os.replace(temp,out)
 result=dict(source_id=sid,source_sha256=r['sha256'],sha256=sha(out),contract_id=CONTRACT_ID,path=str(out),**counts,elapsed_seconds=round(time.time()-started,2))
 save(receipt,result);print(dump(result),flush=True);return result

CODEFILES=[Path(__file__),OLD/'extractors.py',OLD/'common.py',ROOT/'tools/prepare_vectorisation_tables.py',ROOT/'tools/vectorisation_table_geometry.py',ROOT/'tools/vectorisation_table_text.py']
CONTRACT_ID=hashtext(dump({str(p):sha(p) for p in CODEFILES})+CFG['tokenizer_sha256'])

def run_stage():
 OUT.mkdir(exist_ok=True);sources=[r for r in SOURCES if r['action']=='index' or r['action']=='context_only']
 save(OUT/'preparation_contract.json',dict(contract_id=CONTRACT_ID,reference_generation='F:/LexMachine/NosDeniers/generation_tables_20260911',code={str(p):sha(p) for p in CODEFILES},model=CFG['model'],revision=CFG['model_revision'],tokenizer_sha256=CFG['tokenizer_sha256'],max_tokens=800,artificial_overlap=0,word_boundary_required=True,truncation=False,internal_export='held_separately',automatic_numeric_fact=False,sources=len(sources),gpu_launched=False))
 receipts=[]
 for r in sources:
  print('START',r['id'],r['title'],flush=True);receipts.append(stage_document(r))
  save(OUT/'status.json',dict(phase='staging',done=len(receipts),expected=len(sources),records=sum(x['records'] for x in receipts),passages=sum(x['chunks'] for x in receipts),gpu_launched=False))
 save(OUT/'receipts.json',receipts);save(OUT/'status.json',dict(phase='staged',complete=True,documents=len(receipts),records=sum(x['records'] for x in receipts),passages=sum(x['chunks'] for x in receipts),gpu_launched=False))

if __name__=='__main__':
 sys.stdout.reconfigure(encoding='utf-8');run_stage()
