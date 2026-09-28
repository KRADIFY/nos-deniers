import sys,json,sqlite3,pathlib,collections,fitz
sys.path.insert(0,'tools')
from build_rap_movements_national_candidates import extract_page,norm,CAPTIONS
scan=json.load(open('reports/historique-2017-2022/mouvements-scan-candidates.json',encoding='utf8'))['items']
c=sqlite3.connect('reports/historique-2017-2022/budget-opened-staged.sqlite')
mission_map={}
for y,p,m,ml,pl in c.execute("select year,program,mission,mission_label,program_label from facts where budget='BG' group by year,program,mission,mission_label,program_label"):
 mission_map.setdefault((y,str(p)),set()).add((m,ml,pl))
counts=collections.Counter();examples=[];ok=[]
seen=set()
for x in scan:
 y,p=int(x['year']),str(x['program'])
 if (y,p) in seen: continue
 seen.add((y,p)); info=mission_map.get((y,p),set())
 if len(info)!=1: counts['ambiguous_mission']+=1; continue
 mission=next(iter(info))[0]; path=pathlib.Path(x['path'])
 if not path.exists(): counts['missing_file']+=1; continue
 sha=x['source']
 with fitz.open(path) as doc:
  rows=[];totals=[];fails=[]
  for pi,page in enumerate(doc):
   text=norm(page.get_text())
   if not any(norm(k) in text for k in CAPTIONS): continue
   try:
    r,t=extract_page(page,y,mission,p,pi+1,'sid',sha)
    if r or t: rows+=r;totals+=t
   except Exception as e:
    fails.append((pi+1,repr(e)))
  if totals and any(t['is_grand_total'] for t in totals):
   counts['parsed_with_grand']+=1;ok.append((y,p,len(rows),len(totals),len(fails)))
  elif totals: counts['parsed_no_grand']+=1
  elif fails: counts['failed']+=1
  else: counts['no_table']+=1
  if fails and len(examples)<20:examples.append((y,p,fails[:3]))
print('counts',dict(counts),'ok',len(ok),'unique',len(seen));print('examples',examples)
print('ok sample',ok[:20])
