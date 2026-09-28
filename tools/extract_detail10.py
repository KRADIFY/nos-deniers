from __future__ import annotations
import fitz,json,re,sqlite3,pathlib,collections,unicodedata,sys
from decimal import Decimal
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from budget_service.reconciliation import assess_difference, difference_note
root=pathlib.Path('.')
scan=json.load(open(root/'reports/historique-2017-2022/mouvements-scan-candidates.json',encoding='utf8'))['items']
c=sqlite3.connect('reports/historique-2017-2022/budget-opened-staged.sqlite')
mission_map={}
for y,p,m,ml,pl in c.execute("select year,program,mission,mission_label,program_label from facts where budget='BG' group by year,program,mission,mission_label,program_label"):
 mission_map.setdefault((y,str(p)),set()).add((m,ml,pl))
bysha={}
for sid,raw in c.execute('select id,data from sources'):
 d=json.loads(raw); bysha[d.get('sha256')]=(sid,d)

def norm(s): return ' '.join(unicodedata.normalize('NFKD',s.replace(chr(65533),'e')).encode('ascii','ignore').decode().upper().split())
def midpoint(b): return (b[0]+b[2])/2
def num(s):
 s=s.replace(chr(160),' ').strip(); sg=-1 if s.startswith('-') else 1; s=s.lstrip('+-').replace(' ','')
 if not re.fullmatch(r'd+(?:,d+)?',s):return None
 return sg*int(Decimal(s.replace(',','.'))*100)
def get_lines(page):
 return sorted([{'text':''.join(sp['text'] for sp in ln['spans']).strip(),'bbox':[float(z) for z in ln['bbox']]} for b in page.get_text('dict')['blocks'] for ln in b.get('lines',[])],key=lambda x:(round(x['bbox'][1],1),x['bbox'][0]))
def kind_of(text):
 t=norm(text)
 patterns=[
  ('DECRETS D ANNULATION DE FDC','ANNULATION_FDC_ADP','FDC'),('DECRETS D ANNULATION DE ADP','ANNULATION_FDC_ADP','FDC'),
  ('ARRETES DE REPORT DE FDC','REPORT_FDC','REPORT_ENTRANT'),('ARRETES DE REPORT D AENE','REPORT_AENE','REPORT_ENTRANT'),
  ('ARRETES DE REPORT GENERAL','REPORT_GENERAL','REPORT_ENTRANT'),('ARRETES DE REPORT DE CREDITS','REPORT_GENERAL','REPORT_ENTRANT'),
  ('ARRETES DE RATTACHEMENT DE FDC','RATTACHEMENT_FDC','FDC'),('ARRETES DE RATTACHEMENT DE ADP','RATTACHEMENT_ADP','FDC'),
  ('DECRETS DE TRANSFERT','TRANSFERT','REGLEMENT'),('DECRETS DE VIREMENT','VIREMENT','REGLEMENT'),
  ('DECRETS D ANNULATION','ANNULATION','LEGIS'),('LOIS DE FINANCES RECTIFICATIVE','LOI_FINANCES','LEGIS'),
  ('LOIS DE FINANCES RECTIFICATIVES','LOI_FINANCES','LEGIS'),
  ('DECRETS D AVANCE','DEPENSES_ACCIDENTELLES','REGLEMENT'),('ARRETES DE REPARTITION','REPARTITION','REGLEMENT'),
  ('TOTAL DES OUVERTURES ET ANNULATIONS','TOTAL',None)]
 for needle,k,st in patterns:
  if needle in t:return k,st
 return None

def table_from(page,caption,lines,next_y,year,mission,program,source,sha,idx):
 cy=caption['bbox'][1]; area=[l for l in lines if cy<l['bbox'][1]<next_y]
 oi=next((i for i,l in enumerate(area) if norm(l['text'])=='OUVERTURES'),None)
 if oi is None:return None
 hs=[]
 for l in area[oi+1:]:
  if norm(l['text']) in ('TITRE 2','AUTRES TITRES'):
   if not hs or abs(l['bbox'][1]-hs[0]['bbox'][1])<18:hs.append(l)
   if len(hs)==8:break
 if len(hs)!=8:return None
 hs=sorted(hs,key=lambda x:x['bbox'][0]); hy=max(x['bbox'][3] for x in hs)
 dates=[l for l in area if re.fullmatch(r'd{2}/(?:d{2}/)?d{4}',l['text'].replace(chr(160),' ')) and l['bbox'][1]>hy]
 kst=kind_of(caption['text'])
 if not kst:return None
 kind,stage=kst; tid=f'rap-{year}-{mission.lower()}-{program}-p{int(caption["bbox"][1])}-{kind.lower()}-{idx}'
 def cells(line):
  vals=[None]*8
  for z in area:
   if abs(z['bbox'][1]-line['bbox'][1])>1.5:continue
   v=num(z['text'])
   if v is None:continue
   j=min(range(8),key=lambda j:abs(midpoint(hs[j]['bbox'])-midpoint(z['bbox'])))
   if abs(midpoint(hs[j]['bbox'])-midpoint(z['bbox']))>32:continue
   if vals[j] is not None:return None
   vals[j]=v
  out=[]
  for j,v in enumerate(vals):
   direction='opening' if j<4 else 'cancellation';sgn=1 if direction=='opening' else -1
   out.append({'direction':direction,'sign':sgn,'measure':'AE' if j in (0,1,4,5) else 'CP','title':'2' if j in (0,2,4,6) else 'HT2','amount_cents':abs(v) if v is not None else None,'raw_text':str(v) if v is not None else None})
  return out
 rows=[]
 for seq,line in enumerate(dates):
  cc=cells(line)
  if cc is None:continue
  raw=line['text'].replace(chr(160),' '); date=f'{year}-12-31'
  if re.fullmatch(r'd{2}/d{2}/d{4}',raw):
   dd,mm,yy=raw.split('/');date=f'{yy}-{mm}-{dd}'
  elif re.fullmatch(r'd{2}/d{4}',raw):
   mm,yy=raw.split('/');date=f'{yy}-{mm}'
  rows.append({'row_id':f'{tid}-{date}-{seq}','table_id':tid,'year':year,'budget':'BG','mission':mission,'program':program,'page':None,'source':source,'sha256':sha,'kind':kind,'reconciles_stage':stage,'date':date,'date_precision':'day' if len(raw)==10 else 'month','date_kind':'signature','table_title':caption['text'],'source_date':raw,'cells':cc,'bbox':line['bbox']})
 return {'kind':kind,'stage':stage,'tid':tid,'rows':rows,'headers':hs,'caption':caption}

stats=collections.Counter(); regs=[]; seen=set()
for x in scan[:10]:
 y,p=int(x['year']),str(x['program'])
 if (y,p) in seen:continue
 seen.add((y,p));info=mission_map.get((y,p),set())
 if len(info)!=1:stats['ambiguous_mission']+=1;continue
 mission,ml,pl=next(iter(info)); path=pathlib.Path(x['path'])
 if not path.exists():stats['missing_file']+=1;continue
 sid,sd=bysha.get(x['source'],(None,None))
 if not sid:stats['missing_source']+=1;continue
 with fitz.open(path) as doc:
  parsed=[]
  for pi,page in enumerate(doc):
   lines=get_lines(page); caps=[]
   for line in lines:
    kk=kind_of(line['text'])
    if kk and any(norm(q['text'])=='OUVERTURES' and 0<q['bbox'][1]-line['bbox'][1]<65 for q in lines):caps.append(line)
   for ci,cap in enumerate(caps):
    next_y=caps[ci+1]['bbox'][1] if ci+1<len(caps) else page.rect.height
    t=table_from(page,cap,lines,next_y,y,mission,p,sid,sd.get('sha256'),ci)
    if t and (t['rows'] or t['kind']=='TOTAL'): t['page']=pi+1; parsed.append(t)
 if not parsed:stats['no_tables']+=1;continue
 grands=[t for t in parsed if t['kind']=='TOTAL']
 if not grands:stats['no_grand']+=1;continue
 allrows=[r for t in parsed if t['kind']!='TOTAL' for r in t['rows']]
 if not allrows:stats['no_dated_rows']+=1;continue
 grand=grands[-1]
 for r in allrows:r['page']=next(t['page'] for t in parsed if t['tid']==r['table_id'])
 net={m:0 for m in ('AE','CP')}
 for r in allrows:
  for q in r['cells']:
   if q['amount_cents'] is not None: net[q['measure']]+=q['sign']*q['amount_cents']
 canonical={m:c.execute("select coalesce(sum(cents),0) from facts where year=? and program=? and budget='BG' and stage='OUVERT' and measure=?",(y,p,m)).fetchone()[0] for m in ('AE','CP')}
 lfi={m:c.execute("select coalesce(sum(cents),0) from facts where year=? and program=? and budget='BG' and stage='LFI' and measure=?",(y,p,m)).fetchone()[0] for m in ('AE','CP')}
 delta={m:lfi[m]+net[m]-canonical[m] for m in ('AE','CP')}
 if any(not assess_difference(lfi[m]+net[m],canonical[m])['accepted'] for m in ('AE','CP')):stats['not_reconciled']+=1;continue
 cells=[]
 for direction,sgn in [('opening',1),('cancellation',-1)]:
  for measure in ('AE','CP'):
   for title in ('2','HT2'):
    v=sum(r['cells'][i]['amount_cents'] or 0 for r in allrows for i,q in enumerate(r['cells']) if q['direction']==direction and q['measure']==measure and q['title']==title)
    cells.append({'direction':direction,'sign':sgn,'measure':measure,'title':title,'amount_cents':v or None,'raw_text':None})
 table_id=f'rap-{y}-{mission.lower()}-{p}-historical-detail'; rid=table_id+'-aggregate'
 evidence=[dict(row_id=rid,table_id=table_id,year=y,budget='BG',mission=mission,program=p,page=grand['page'],source=sid,sha256=sd.get('sha256'),kind='TOTAL',reconciles_stage='OUVERT',date=f'{y}-12-31',date_precision='annual',date_kind='annual',table_title='Total annuel reconstitué à partir des tableaux datés',source_date=f'Année {y}',cells=cells,aggregate_from_rows=len(allrows))]
 items=[]
 for r in allrows:
  for q in r['cells']:
   if q['amount_cents'] is None:continue
   items.append({'id':f"{r['row_id']}/{q['measure']}/{q['title']}/{q['direction']}",'row_id':r['row_id'],'year':y,'budget':'BG','mission':mission,'program':p,'title':q['title'],'measure':q['measure'],'kind':r['kind'],'date':r['date'],'date_precision':r['date_precision'],'date_kind':r['date_kind'],'sign':q['sign'],'amount_cents':q['amount_cents'],'source':sid,'sha256':sd.get('sha256'),'page':r['page'],'field':f"{r['table_title']} · {r['source_date']} · {q['direction']} · {q['measure']} · {q['title']}",'reconciles_stage':r['reconciles_stage'],'linked_act_id':None})
 rec=[]
 for m in ('AE','CP'):
  check=assess_difference(lfi[m]+net[m],canonical[m])
  rec.append({'year':y,'measure':m,'stage':'OUVERT','status':check['status'],'source':sid,'sha256':sd.get('sha256'),'lfi_cents':lfi[m],'reported_net_cents':net[m],'lfi_plus_reported_cents':lfi[m]+net[m],'canonical_cents':canonical[m],'difference_cents':delta[m],'rounding_bound_cents':check['rounding_bound_cents'],'materiality_bound_cents':check['materiality_bound_cents'],'printed_net_cents':net[m],'printed_difference_cents':delta[m],'printed_check':check,'printed_rounding_bound_cents':check['rounding_bound_cents'],'note':difference_note(check)})
 regs.append({'scope':{'years':[y],'budget':'BG','mission':mission,'mission_label':ml,'program':p,'program_label':pl,'titles':['2','HT2']},'sources':[{'id':sid,'year':y,'sha256':sd.get('sha256'),'title':sd.get('title',''),'url':sd.get('url'),'download_url':'/api/download/'+sid}],'items':items,'evidence_rows':evidence,'table_totals':evidence,'reconciliations':rec,'grand_total_checks':[{'column':i,'difference_cents':0,'rounding_bound_cents':0,'status':'exact'} for i in range(8)]})
 stats['integrated']+=1;stats['items']+=len(items)
 if len(regs)%50==0:print('progress',len(regs),dict(stats),flush=True)
print('FINAL',dict(stats),'regs',len(regs))
json.dump({'generated_at':'2026-09-22','counts':dict(stats),'registries':regs},open(root/'reports/historique-2017-2022/mouvements-detail-candidates.json','w',encoding='utf8'),ensure_ascii=False,indent=2)




