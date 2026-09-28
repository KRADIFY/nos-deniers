import sys,json,sqlite3
from pathlib import Path
import fitz
sys.path.insert(0,'tools')
from build_rap_movements_national_candidates import lines_of,norm
items=json.load(open('reports/historique-2017-2022/mouvements-scan-candidates.json',encoding='utf8'))['items']
for y in range(2017,2023):
 x=next(x for x in items if x['year']==y)
 with fitz.open(x['path']) as d:
  hit=False
  for pi,page in enumerate(d):
   if 'TOTAL DES OUVERTURES ET ANNULATIONS' in norm(page.get_text()):
    print('SAMPLE',y,x['program'],pi+1,x['path'])
    for z in lines_of(page):print(z)
    hit=True;break
  if not hit: print('NO',y,x['program'])
