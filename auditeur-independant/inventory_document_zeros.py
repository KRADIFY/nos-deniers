import sqlite3,json,collections
from pathlib import Path
db=sqlite3.connect('references/20260924-final/budget.sqlite');db.row_factory=sqlite3.Row
sources={r['id']:json.loads(r['data']) for r in db.execute('select * from sources')}
groups=collections.defaultdict(list)
for r in db.execute('select * from facts where cents=0'):
 if sources[r['source']]['format'] not in ('csv','xls'):groups[r['source']].append(dict(r))
items=[]
for sid,rows in groups.items():
 s=sources[sid];print('\nSOURCE',sid,s['format'],s['title'],'COUNT',len(rows),'PATH',s['path'])
 print('FIELDS',collections.Counter(r['field'] for r in rows))
 print('CELLS',[(r['year'],r['program'],r['measure'],r['stage'],r['title'],r['line']) for r in rows])
 items.append(dict(source=s,rows=rows))
Path('resultats/document-zero-inputs.json').write_text(json.dumps(items,ensure_ascii=False,indent=2),'utf-8')
print('TOTAL',sum(len(x['rows']) for x in items),'DOCUMENTS',len(items))
