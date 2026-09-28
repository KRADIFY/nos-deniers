src=open('tools/extract_historical_detail.py',encoding='utf8').read(); exec(src[:src.index('stats=collections.Counter()')],globals())
import fitz,json,re
x=json.load(open('reports/historique-2017-2022/mouvements-scan-candidates.json',encoding='utf8'))['items'][0]
with fitz.open(x['path']) as d:
 page=d[23]; lines=get_lines(page); caps=[l for l in lines if kind_of(l['text']) and any(norm(q['text'])=='OUVERTURES' and 0<q['bbox'][1]-l['bbox'][1]<65 for q in lines)]
 cap=caps[0]; next_y=caps[1]['bbox'][1]; area=[l for l in lines if cap['bbox'][1]<l['bbox'][1]<next_y]; oi=next(i for i,l in enumerate(area) if norm(l['text'])=='OUVERTURES'); print('cap',cap,'next',next_y,'oi',oi)
 hs=[]
 for l in area[oi+1:]:
  if norm(l['text']) in ('TITRE 2','AUTRES TITRES'):
   if not hs or abs(l['bbox'][1]-hs[0]['bbox'][1])<18:hs.append(l)
   if len(hs)==8:break
 print('hs',len(hs),hs);hy=max(x['bbox'][3] for x in hs); print('hy',hy)
 ds=[l for l in area if re.fullmatch(r'\d{2}/(?:\d{2}/)?\d{4}',l['text'].replace(chr(160),' ')) and l['bbox'][1]>hy]; print('dates',ds)
