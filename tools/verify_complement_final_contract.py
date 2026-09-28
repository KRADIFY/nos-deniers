"""Independent read-back of the incremental input and its retained evidence."""
from pathlib import Path
import sys,json,sqlite3,collections,hashlib,re,datetime,importlib.util
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import prepare_complement_final_contract as prep
from export_complement_final_contract import boundary_errors
O=prep.OUT;B=prep.BUNDLE

def j(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def ro(p):return sqlite3.connect(Path(p).resolve().as_uri()+'?mode=ro',uri=True)
def lex(s):return collections.Counter(re.findall(r'\w+',str(s).casefold()))
def rendered(v):return '' if v is None or v=='' else v if isinstance(v,str) else j(v)

def verify():
 status=json.loads((O/'export_status.json').read_text('utf-8'));assert status['state']=='exported_pending_independent_validation'
 tk=prep.config();stats=collections.Counter();checks=[];c=ro(O/'catalogue.sqlite');raw=ro(B/'05_extractions/tableaux.sqlite')
 assert c.execute('pragma integrity_check').fetchone()[0]=='ok' and c.execute('pragma foreign_key_check').fetchone() is None
 assert c.execute('select count(*) from completed_documents').fetchone()[0]==53
 expected_sources={r['id']:r for r in prep.SOURCES}
 for source in prep.SOURCES:
  assert prep.sha(B/source['path'])==source['sha256'];stats['source_hashes']+=1
 for row in json.loads((B/'_controle/indexes-avant.json').read_text('utf-8')):
  assert prep.sha(Path(row['path'])/'manifest.json')==row['manifest_sha256'];stats['unchanged_active_index_manifests']+=1
 # Word-safe splitting includes accents, whitespace, signs and decimal separators.
 phrase='Crédits de l’État : −1 227 063 244,70 € ; MaPrimeRénov’, jeunesse.\n'
 for text in [phrase,phrase*200,'Première ligne\n\nDeuxième ligne : 0 € ; donnée manquante ≠ zéro.']:
  chunks=prep.natural_chunks(tk,'Contexte de contrôle',[text]);assert ''.join(s['text'] for ch in chunks for s in ch['segments'])==text;assert not boundary_errors(chunks)
 spec=importlib.util.spec_from_file_location('safe',O/'code/vectorisation_table_text_word_safe.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 t=m.serialize_table({'rows':[[phrase*100,None,'']], 'header':{'names':['Texte','Absent','Vide']}},{'source_sha256':'a'*64,'page':1,'table_id':'selfcheck'},tk)
 assert not boundary_errors(t['chunks']);checks.append('synthetic_unicode_money_null_and_word_boundary_cases')
 # Reconstruct every retained source field from the exact indexed fragments.
 for ref,sid,encoded in c.execute('select id,source_id,record_json from records order by source_id,record_no'):
  rec=json.loads(encoded);assert hashlib.sha256(encoded.encode()).hexdigest()==ref
  chunks=[json.loads(v[0]) for v in c.execute('select chunk_json from occurrence_proof where evidence_id=? order by rowid',(ref,))]
  assert not boundary_errors(chunks),(sid,rec['locator'],'word boundary')
  groups=collections.defaultdict(list)
  for ch in chunks:
   assert ch['record_ref']==ref and ch['quality']['allow_automatic_numeric_fact'] is False
   for s in ch.get('segments',[]):groups[(ch.get('table_ref',''),s.get('field_ref',s.get('block')))].append(s)
  source=expected_sources[sid]
  if rec['kind']=='page':
   expected=[str(v.get('text','')) for v in rec.get('blocks',[])]
   source_words=rec.get('words',[]);needed=sum((lex(w[4]) for w in source_words),collections.Counter());have=sum((lex(x) for x in expected),collections.Counter())
   if needed-have:expected.append(' '.join(str(w[4]) for w in source_words))
   stats['pdf_pages']+=1;stats['positioned_words']+=len(source_words)
   tables={t['table_ref']:t for t in rec.get('review',{}).get('tables',[])};stats['table_candidates']+=len(tables)
   assert rec['page']>0 and rec.get('page_count')>=rec['page'] and 'method' in rec
  elif rec['kind']=='table':
   expected=prep.tab_text(rec,rec['header_candidates']);tables={}
   if source['format']=='csv':
    original=raw.execute('select fields_json from csv_rows where source_id=? and row=?',(sid,rec['row_start'])).fetchone();assert original and rec['rows']==[json.loads(original[0])];stats['csv_rows_checked']+=1
   if source['format'] in ('xlsx','xls'):
    for rownum,values in enumerate(rec['rows'],rec.get('row_start',1)):
     for col,val in enumerate(values,1):
      saved=raw.execute('select value_json from cells where source_id=? and sheet=? and row=? and col=?',(sid,rec['sheet'],rownum,col)).fetchone()
      if saved:
       before=json.loads(saved[0])
       comparable=val
       if isinstance(val,dict) and val.get('type')=='date':comparable=val['value'].replace('T',' ')
       assert comparable==before or (val in ('',None) and before in ('',None)),(sid,rec['sheet'],rownum,col,val,before)
       stats['spreadsheet_cells_checked']+=1
  elif rec['kind']=='text':expected=[rec['text']];tables={}
  else:expected=[];tables={}
  recovered={};field_seen=collections.defaultdict(set)
  for (table_ref,field),segments in groups.items():
   body='';end=0
   for s in segments:
    assert s['char_start']==end and s['char_end']-s['char_start']==len(s['text']),(sid,rec['locator'],field,'gap/overlap')
    body+=s['text'];end=s['char_end']
   if not table_ref:assert body==expected[field],(sid,rec['locator'],field,'block mismatch');recovered[field]=body
   else:
    rt=tables[table_ref];s=segments[0];table=rt['table'];field_seen[table_ref].add(field)
    if s['kind']=='context':value=j({s['context_key']:rt['context'][s['context_key']]})
    elif s['kind']=='header_candidate':value=rendered((table.get('header') or {})['names'][s['candidate_index']-1])
    else:
     row=table['rows'][s['row']-table.get('row_start',1)];value=rendered(row[s['column']-1] if len(row)>=s['column'] else None)
    assert body==value,(sid,rec['locator'],field,'table mismatch');stats['table_fields_checked']+=1
  assert set(recovered)=={i for i,x in enumerate(expected) if x},(sid,rec['locator'],'missing raw block')
  for table_ref,rt in tables.items():
   table=rt['table'];width=rt['column_count'];n=len(rt['context'])+len((table.get('header') or {}).get('names',[]))+len(table['rows'])*width
   assert len(field_seen[table_ref])==n,(sid,rec['locator'],'missing table field')
  stats['records_checked']+=1
  if stats['records_checked']%10000==0:print(j(dict(phase='evidence',**stats)),flush=True)
 # Every numerical source cell represented in staged sheets is present, including zero.
 assert stats['csv_rows_checked']==104300
 assert c.execute('select count(*) from passages p where not exists(select 1 from occurrences o where o.passage_id=p.id)').fetchone()[0]==0
 assert c.execute('select count(*) from occurrences o where not exists(select 1 from occurrence_proof q where q.occurrence_id=o.id)').fetchone()[0]==0
 for partition,desc in status['partitions'].items():
  f=O/desc['input'];assert prep.sha(f)==desc['sha256'] and f.stat().st_size==desc['bytes'];n=t=0
  with f.open(encoding='utf-8') as stream:
   rows=c.execute('select id,text,tokens from passages where partition=? order by id',(partition,))
   for ln in stream:
    rec=json.loads(ln);expected=next(rows,None);assert expected and (rec['id'],rec['text'],rec['tokens'])==expected
    actual=len(tk.encode(rec['text']).ids);assert 0<actual==rec['tokens']<=800;n+=1;t+=actual;stats['max_tokens']=max(stats['max_tokens'],actual)
   assert next(rows,None) is None
  assert n==desc['count'] and t==desc['tokens'];stats[partition+'_passages']=n;stats[partition+'_tokens']=t
  print(j(dict(partition=partition,checked=n,tokens=t)),flush=True)
 assert c.execute("select count(*) from refs where partition='public' and json_extract(metadata_json,'$.source_tier')!='official'").fetchone()[0]==0
 snap=json.loads((O/'structured/manifest.json').read_text('utf-8'))
 for r in snap['files']:assert prep.sha(O/'structured'/r['path'])==r['sha256']
 assert snap['facts']==122970
 reviews=dict(c.execute('select method,count(*) from page_reviews group by method'))
 report=dict(state='passed',at=datetime.datetime.now().astimezone().isoformat(),checks=checks,counts=dict(stats),pdf_methods=reviews,independent_readback=True,quality_flags_are_not_numeric_certification=True,catalogue_sha256=prep.sha(O/'catalogue.sqlite'),input_sha256=status['partitions']['public']['sha256'],source_base_input_sha256='5089bcdcd395be8c371f4ed99961b46251120a744d61a7349b3b27b8687ce442',gpu_launched=False,active_site_modified=False)
 c.close();raw.close();prep.save(O/'VERIFICATION.json',report);print(j(report),flush=True)
if __name__=='__main__':verify()
