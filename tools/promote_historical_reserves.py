import json,re,sqlite3,pathlib,hashlib,collections
root=pathlib.Path('.')
scan=json.loads((root/'reports/historique-2017-2022/reserves-scan-candidates.json').read_text(encoding='utf-8'))
db=sqlite3.connect('reports/mpr-closure-20260920/runtime/derived/budget.sqlite')
sources={}
for sid,data in db.execute('select id,data from sources'):
 try:
  z=json.loads(data); sources[z.get('sha256')]=(sid,z)
 except Exception: pass
maps={}
for y,p,mi,ml,pl in db.execute("select year,program,mission,mission_label,program_label from facts where year between 2017 and 2022 and budget='BG' group by 1,2,3,4,5"):
 maps[(y,str(p))]=(mi,ml,pl)
num=re.compile(r'[+-]?\d{1,3}(?:[ .]\d{3})*(?:,\d+)?|[+-]?0')
def val(s):
 s=s.replace('\u00a0',' ').replace(' ','').replace('.','').replace(',','.')
 try:return int(round(float(s)*100))
 except Exception:return None
def line_values(s):
 vals=[val(x) for x in num.findall(s)]
 if len(vals)==4: vals=[None,vals[0],vals[1],None,vals[2],vals[3]]
 return vals if len(vals)==6 else None
records=[]; srcs={}; bad=collections.Counter()
for item in scan['items']:
 if item.get('status')!='candidate': continue
 y=item['year']; program=str(item.get('program') or '')
 if (y,program) not in maps: bad['mapping']+=1; continue
 got=sources.get(item.get('source'))
 if not got: bad['source']+=1; continue
 sid,source=got; lines={}
 for hit in item.get('hits',[]):
  for line in hit.get('lines',[]):
   low=line.lower()
   key='initial' if 'initiale' in low else 'surgels' if 'surgel' in low else 'degels' if 'gel' in low and 'initiale' not in low else 'remaining' if 'disponible' in low else None
   if key: lines[key]=line_values(line)
 if set(lines)!=set(('initial','surgels','degels','remaining')) or any(lines[k] is None for k in lines): bad['fields']+=1; continue
 mi,ml,pl=maps[(y,program)]
 for measure,offset in (('AE',0),('CP',3)):
  cells={}; ok=True
  for key,values in lines.items():
   t=values[offset+2]; d=t-(values[offset] or 0)-(values[offset+1] or 0); ok &= d==0
   cells[key]={'title2_cents':values[offset],'other_titles_cents':values[offset+1],'total_cents':t}
  for col in ('title2_cents','other_titles_cents','total_cents'):
   if all(cells[k][col] is not None for k in cells):
    d=cells['remaining'][col]-sum(cells[k][col] for k in ('initial','surgels','degels')); ok &= abs(d)<=100
  records.append({'year':y,'budget':'BG','mission':mi,'program':program,'program_label':pl,'measure':measure,'source':sid,'source_sha256':source.get('sha256'),'page':item['hits'][0]['page'],'cells':cells,'note':'Tableau RAP historique au niveau du programme ; aucune ventilation par action deduite.','remaining_label':'Reserve disponible avant mise en place du schema de fin de gestion','context_pages':[item['hits'][0]['page']],'checks':[],'numeric_validation':'published_columns_and_balance_reconciled' if ok else 'published_with_balance_difference'})
 srcs[sid]={'id':sid,'sha256':source.get('sha256'),'title':source.get('title',''),'path':source.get('path'),'url':source.get('url')}
uniq={}
for row in records: uniq[(row['year'],row['mission'],row['program'],row['measure'])]=row
out={'updated_at':'2026-09-21','coverage':'RAP historiques 2017-2022 : tables de reserves programmatiques extraites et controlees ; Budget general uniquement quand le programme est identifie sans ambiguite.','field_labels':['initial','surgels','degels','remaining'],'sources':list(srcs.values()),'records':list(uniq.values()),'checks':[],'notes':['Montants conserves selon les colonnes imprimees ; aucune ventilation par action.','Les tables sans total ou avec mise en page non reconnue restent candidates non promues.']}
p=root/'budget_service/data/reserves-historique-2017-2022.json';p.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print('records',len(out['records']),'sources',len(srcs),'skipped',dict(bad),'sha',hashlib.sha256(p.read_bytes()).hexdigest())
