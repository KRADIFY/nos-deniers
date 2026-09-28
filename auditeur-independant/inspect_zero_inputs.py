import sqlite3,json,collections
from pathlib import Path
db=sqlite3.connect('references/20260924-final/budget.sqlite');db.row_factory=sqlite3.Row
sources={r['id']:json.loads(r['data']) for r in db.execute('select * from sources')}
zero=[dict(r) for r in db.execute('select * from facts where cents=0')]
print('ZERO FACTS',len(zero),'allfacts',db.execute('select count(*) from facts').fetchone()[0])
print('formats',collections.Counter(sources[r['source']].get('format') for r in zero))
print('field samples',collections.Counter(r['field'] for r in zero).most_common(18))
for fmt in ('xls','xlsx','csv','pdf'):
 rows=[r for r in zero if sources[r['source']].get('format')==fmt]
 for r in rows[:3]:print('FACT',json.dumps(r,ensure_ascii=False),'SOURCE',json.dumps(sources[r['source']],ensure_ascii=False)[:1800])
print('sourcekeys',list(next(iter(sources.values()))))
