from pathlib import Path
import json
import pdfplumber
from PIL import Image,ImageDraw,ImageFont
root=Path(__file__).resolve().parents[1]
out=root/'reports/reserves-ecologie-2023-2025'
tables=json.loads((out/'candidate-tables.json').read_text(encoding='utf-8'))
inv=json.loads((root/'reports/reserves-et-consignes-20260909/rap-reserves-pages.json').read_text(encoding='utf-8'))
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',24)
for year in (2023,2024,2025):
 doc=next(d for d in inv if d['year']==year)
 with pdfplumber.open(doc['path']) as pdf:
  panels=[]
  for t in [x for x in tables if x['year']==year]:
   page=pdf.pages[t['page']-1]
   start=page.search('Mise en réserve initiale')[0]
   end=page.search('Réserve disponible avant')[0]
   img=Image.open(out/t['image'])
   scale=img.height/page.height
   crop=img.crop((0,max(0,(start['top']-65)*scale),img.width,min(img.height,(end['bottom']+40)*scale)))
   panel=Image.new('RGB',(img.width,crop.height+40),'white')
   panel.paste(crop,(0,40));ImageDraw.Draw(panel).text((20,5),f"{year} - P{t['program']} - RAP page {t['page']}",font=font,fill='black')
   panels.append(panel)
  for batch in range(0,len(panels),3):
   group=panels[batch:batch+3];canvas=Image.new('RGB',(max(p.width for p in group),sum(p.height for p in group)),'#dddddd')
   top=0
   for p in group:canvas.paste(p,(0,top));top+=p.height
   canvas.save(out/'pages'/f'review-{year}-{batch//3+1}.png')
summary=[]
for t in tables:
 text=(out/t['context_file']).read_text(encoding='utf-8')
 tail=text[text.index('Réserve disponible avant mise en place'):]
 tail=tail[tail.find('\n',tail.find('\n')+1)+1:].strip()
 tail=tail.split('\f')[0].strip()
 summary.append(dict(key=t['key'],tail=tail))
(out/'contexts-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print('Review sheets and context summary prepared.')