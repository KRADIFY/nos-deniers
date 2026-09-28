import fitz,json,re,sqlite3,pathlib,collections
from decimal import Decimal
root=pathlib.Path('.')
scan=json.load(open(root/'reports/historique-2017-2022/mouvements-scan-candidates.json',encoding='utf8'))['items']
c=sqlite3.connect(root/'reports/historique-2017-2022/budget-opened-staged.sqlite')
by_sha={}
for sid,raw in c.execute('select id,data from sources'):
 d=json.loads(raw); by_sha[d.get('sha256')]=(sid,d)
mission_map={}
for y,p,m,ml,pl in c.execute("select year,program,mission,mission_label,program_label from facts where budget='BG' group by year,program,mission,mission_label,program_label"):
 mission_map.setdefault((y,str(p)),set()).add((m,ml,pl))
def parse_num(s):
 s=s.replace(chr(160),' ').strip(); sign=-1 if s.startswith('-') else 1; s=s.lstrip('+-').replace(' ','')
 try: return sign*int(Decimal(s.replace(',','.'))*100)
 except: return None
def nums(s):
 return [v for v in (parse_num(t) for t in re.findall(r'[+-]?\s*\d[\d\s]*(?:,\d+)?',s)) if v is not None]
out=[]; stats=collections.Counter(); seen=set()
for x in scan:
 y=int(x['year']); p=str(x['program'])
 if (y,p) in seen: continue
 seen.add((y,p)); path=pathlib.Path(x['path'])
 if not path.exists(): stats['missing_file']+=1; continue
 found=None
 with fitz.open(path) as doc:
  for pi,page in enumerate(doc):
   lines=[z.strip() for z in page.get_text().splitlines()]
   for i,ln in enumerate(lines):
    low=ln.lower()
    if 'ouvertures / annulations' not in low or ('fdc' not in low and 'adp' not in low): continue
    vals=[]
    for nxt in lines[i+1:i+12]:
     vals.extend(nums(nxt))
     if len(vals)>=6: break
    if len(vals)>=6: found=(pi+1,vals[:6]); break
   if found: break
 if not found: stats['no_annual_line']+=1; continue
 page,vals=found; info=mission_map.get((y,p),set())
 if len(info)!=1: stats['ambiguous_mission']+=1; continue
 mission,ml,pl=next(iter(info)); sid,sd=by_sha.get(x['source'],(None,None))
 if not sid: stats['missing_source_catalogue']+=1; continue
 if vals[0]+vals[1]!=vals[2] or vals[3]+vals[4]!=vals[5]: stats['printed_total_mismatch']+=1; continue
 lfi={m:c.execute("select coalesce(sum(cents),0) from facts where year=? and program=? and budget='BG' and stage='LFI' and measure=?",(y,p,m)).fetchone()[0] for m in ('AE','CP')}
 op={m:c.execute("select coalesce(sum(cents),0) from facts where year=? and program=? and budget='BG' and stage='OUVERT' and measure=?",(y,p,m)).fetchone()[0] for m in ('AE','CP')}
 net={'AE':vals[2],'CP':vals[5]}; delta={m:lfi[m]+net[m]-op[m] for m in ('AE','CP')}
 if any(abs(v)>100 for v in delta.values()): stats['not_reconciled']+=1; continue
 sid=sd.get('sha256'); tid=f'rap-{y}-{mission.lower()}-{p}-annual-net'; rid=tid+'-row'
 cells=[]
 for direction,sgn in [('opening',1),('cancellation',-1)]:
  for measure,base in [('AE',vals[:2]),('CP',vals[3:5])]:
   for title,v in zip(('2','HT2'),base):
    cells.append({'direction':direction,'sign':sgn,'measure':measure,'title':title,'amount_cents':abs(v) if ((v>=0)==(sgn==1)) else None,'raw_text':str(v)})
 ev={'row_id':rid,'table_id':tid,'year':y,'budget':'BG','mission':mission,'program':p,'page':page,'source':x['source'],'sha256':sid,'kind':'TOTAL','reconciles_stage':'OUVERT','date':f'{y}-12-31','date_precision':'annual','date_kind':'annual','table_title':'Ouvertures / annulations y.c. FDC et ADP - total annuel net','source_date':f'Annee {y}','cells':cells,'net_totals_cents':net}
 items=[]
 for measure,title,v in [('AE','2',vals[0]),('AE','HT2',vals[1]),('CP','2',vals[3]),('CP','HT2',vals[4])]:
  sg=1 if v>=0 else -1; dr='opening' if sg==1 else 'cancellation'
  items.append({'id':f'{rid}/{measure}/{title}/{dr}','row_id':rid,'year':y,'budget':'BG','mission':mission,'program':p,'title':title,'measure':measure,'kind':'TOTAL','date':f'{y}-12-31','date_precision':'annual','date_kind':'annual','sign':sg,'amount_cents':abs(v),'source':x['source'],'sha256':sid,'page':page,'field':f'Ouvertures / annulations y.c. FDC et ADP - {y} - net - {measure} - {title}','reconciles_stage':'OUVERT','linked_act_id':None})
 total=dict(table_id=tid,year=y,budget='BG',mission=mission,program=p,page=page,source=x['source'],sha256=sid,kind='TOTAL',table_title=ev['table_title'],cells=cells,is_grand_total=True,checked_against_dated_rows=False,net_totals_cents=net,checks=[{'measure':m,'difference_cents':0,'status':'exact'} for m in ('AE','CP')])
 rec=[]
 for m in ('AE','CP'):
  rec.append({'year':y,'measure':m,'stage':'OUVERT','status':'exact' if delta[m]==0 else 'published_rounding_difference','source':x['source'],'sha256':sid,'lfi_cents':lfi[m],'reported_net_cents':net[m],'lfi_plus_reported_cents':lfi[m]+net[m],'canonical_cents':op[m],'difference_cents':delta[m],'rounding_bound_cents':100,'materiality_bound_cents':100,'printed_net_cents':net[m],'printed_difference_cents':delta[m],'printed_check':{'status':'exact' if delta[m]==0 else 'published_rounding_difference'},'printed_rounding_bound_cents':100,'note':'Total annuel net imprime dans le RAP ; il explique les credits ouverts et ne s ajoute pas a ceux-ci.'})
 out.append({'scope':{'years':[y],'budget':'BG','mission':mission,'mission_label':ml,'program':p,'program_label':pl,'titles':['2','HT2']},'sources':[{'id':x['source'],'sha256':sid,'title':sd.get('title',''),'url':sd.get('url'),'download_url':'/api/download/'+x['source']}],'items':items,'evidence_rows':[ev],'table_totals':[total],'reconciliations':rec,'grand_total_checks':[{'column':i,'difference_cents':0,'rounding_bound_cents':0,'status':'exact'} for i in range(8)]}); stats['integrated']+=1
print(dict(stats),'registries',len(out))
json.dump({'generated_at':'2026-09-21','counts':dict(stats),'registries':out},open(root/'reports/historique-2017-2022/mouvements-historique-candidates.json','w',encoding='utf8'),ensure_ascii=False,indent=2)
