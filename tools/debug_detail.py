import sys,fitz,json,pathlib
src=open('tools/extract_historical_detail.py',encoding='utf8').read(); exec(src[:src.index('stats=collections.Counter()')],globals())
x=json.load(open('reports/historique-2017-2022/mouvements-scan-candidates.json',encoding='utf8'))['items'][0]
print(x['year'],x['program'],x['path'])
with fitz.open(x['path']) as d:
 page=d[23]; lines=get_lines(page)
 for l in lines:
  k=kind_of(l['text'])
  if k: print('CAP',repr(l['text']),k)
 caps=[l for l in lines if kind_of(l['text']) and any(norm(q['text'])=='OUVERTURES' and 0<q['bbox'][1]-l['bbox'][1]<65 for q in lines)]
 print('caps',len(caps))
 for i,cap in enumerate(caps):
  t=table_from(page,cap,lines,caps[i+1]['bbox'][1] if i+1<len(caps) else page.rect.height,2018,'AA','105','sid','sha',i)
  print('table',t and t['kind'],len(t['rows']) if t else None)
