src=open('tools/extract_historical_detail.py',encoding='utf8').read(); exec(src[:src.index('stats=collections.Counter()')],globals())
import fitz,json,re
x=json.load(open('reports/historique-2017-2022/mouvements-scan-candidates.json',encoding='utf8'))['items'][0]
with fitz.open(x['path']) as d:
 lines=get_lines(d[23]);
 for l in lines:
  if 150<l['bbox'][1]<220: print(repr(l['text']),re.fullmatch(r'\d{2}/(?:\d{2}/)?\d{4}',l['text'].replace(chr(160),' ')))
