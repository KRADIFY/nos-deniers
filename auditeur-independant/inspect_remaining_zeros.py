import csv,json,collections
from pathlib import Path
from zeros import Reader
from oracle import Reference
r=Reference(Path('references/20260924-final'));reader=Reader('references/physical-sources')
seen=set()
for f in r.rows:
 if f['cents']!=0:continue
 s=r.sources[f['source']]
 if 'AEPLF' in f['field'] or 'CPPLF' in f['field']:
  if s['id'] not in seen:
   d=reader.source(s);print(s['title'], f['field'], d['sheets'][d['default']][0]);seen.add(s['id'])
print('document sources',collections.Counter(r.sources[f['source']]['format'] for f in r.rows if f['cents']==0 and r.sources[f['source']]['format'] not in ('csv','xls')))
