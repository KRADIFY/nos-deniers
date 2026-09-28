"""Prepare historical reserve tables from verified PDFs; no app data writes."""
from pathlib import Path
import json,re,hashlib,subprocess,shutil
import pdfplumber
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/reserves-ecologie-2017-2022-20260910'
OLD=ROOT/'reports/reserves-et-consignes-20260909'
BIN=Path('C:/Users/Jean-Christophe/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin')
LABELS={'initial':'Mise en réserve initiale','surgels':'Surgels','degels':'Dégels','cancellations':'Annulations / réserve en cours de gestion','remaining':'Réserve disponible avant mise en place'}

def main():
 OUT.mkdir(parents=True,exist_ok=True);(OUT/'pages').mkdir(exist_ok=True)
 inventory=json.loads((OLD/'rap-reserves-pages.json').read_text(encoding='utf-8'))
 current=json.loads((ROOT/'budget_service/data/reserves-ecologie.json').read_text(encoding='utf-8'))
 font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',24)
 tables=[];coverage=[]
 for year in range(2017,2023):
  doc=next(d for d in inventory if d['year']==year);path=Path(doc['path'])
  assert hashlib.sha256(path.read_bytes()).hexdigest()==doc['sha256']
  source=next(s for s in current['sources'] if s['sha256']==doc['sha256'])
  textfile=OUT/f'rap-ecologie-{year}.txt'
  subprocess.run([shutil.which('pdftotext'),'-layout','-enc','UTF-8',str(path),str(textfile)],check=True,capture_output=True)
  pages=textfile.read_text(encoding='utf-8').split('\f');programmes={};panels=[]
  with pdfplumber.open(path) as pdf:
   for index,text in enumerate(pages):
    match=re.search(r'Programme n.\s*(\d{3})',text[:600])
    if not match:continue
    code=match[1]
    if code not in programmes:
     header=[l.strip() for l in text[:match.start()].splitlines() if l.strip()]
     assert 'PLR' in header[0] and len(header)>1,(year,index,header)
     # Remove right-hand section headings; programme labels occupy previous lines.
     label=' '.join(header[1:]).split('JUSTIFICATION')[0].split('BILAN')[0].strip()
     programmes[code]=dict(program=code,program_label=label,programme_page=index+1)
    if not re.search(r'^Mise en réserve initiale\s{2,}[-0-9]',text,re.M):continue
    raw={};extracted={};counts=set()
    for line in text.splitlines():
     for key,label in LABELS.items():
      if not line.startswith(label):continue
      fields=re.split(r'\s{2,}',line.strip())[1:]
      assert len(fields) in (4,6),(year,index+1,key,fields)
      assert all(re.fullmatch(r'[+-]?\d{1,3}(?: \d{3})*',v) for v in fields),(year,index+1,fields)
      assert key not in raw
      values=[int(v.replace(' ',''))*100 for v in fields]
      counts.add(len(values))
      if len(values)==4:
       assert year<=2018 and code not in ('181','217'),(year,code,key)
       values=[None,*values[:2],None,*values[2:]]
      raw[key]=line;extracted[key]=values
    assert len(counts)==1,(year,code,counts)
    assert {'initial','surgels','degels','remaining'}<=set(extracted)
    rows=[];checks=[]
    for measure,offset in [('AE',0),('CP',3)]:
     cells={k:dict(title2_cents=v[offset],other_titles_cents=v[offset+1],total_cents=v[offset+2]) for k,v in extracted.items()}
     for field,c in cells.items():
      diff=c['total_cents']-sum(v for k,v in c.items() if k!='total_cents' and v is not None)
      checks.append(dict(measure=measure,field=field,check='printed_columns',difference_cents=diff,passed=diff==0,blank_title2_preserved=c['title2_cents'] is None))
     for column in ('title2_cents','other_titles_cents','total_cents'):
      if any(c[column] is None for c in cells.values()):continue
      diff=cells['remaining'][column]-sum(c[column] for k,c in cells.items() if k!='remaining')
      checks.append(dict(measure=measure,field=column,check='printed_balance',difference_cents=diff,passed=diff==0))
     rows.append(dict(year=year,budget='BG',mission='TA',**programmes[code],measure=measure,source=source['id'],source_sha256=source['sha256'],page=index+1,cells=cells,raw_lines=raw))
    key=f'{year}-p{code}';image=OUT/'pages'/key
    subprocess.run([str(BIN/'pdftoppm.exe'),'-f',str(index+1),'-l',str(index+1),'-scale-to','1600','-singlefile','-png',str(path),str(image)],check=True,capture_output=True)
    context=text+'\f'+pages[index+1]
    (OUT/f'{key}-context.txt').write_text(context,encoding='utf-8')
    p=pdf.pages[index];start=p.search('Mise en réserve initiale')[0];end=p.search('Réserve disponible avant')[0]
    im=Image.open(image.with_suffix('.png'));scale=im.height/p.height
    crop=im.crop((0,max(0,(start['top']-65)*scale),im.width,min(im.height,(end['bottom']+42)*scale)))
    panel=Image.new('RGB',(im.width,crop.height+42),'white');panel.paste(crop,(0,42));ImageDraw.Draw(panel).text((20,5),f'{year} - P{code} - RAP p. {index+1}',font=font,fill='black');panels.append(panel)
    tables.append(dict(key=key,year=year,**programmes[code],page=index+1,source=source,records=rows,checks=checks,context_file=f'{key}-context.txt',image=f'pages/{key}.png'))
   found={t['program'] for t in tables if t['year']==year}
   assert len(found)==8,(year,found)
   coverage.append(dict(year=year,programmes=list(programmes.values()),without_table=sorted(set(programmes)-found)))
   for n in range(0,len(panels),3):
    group=panels[n:n+3];canvas=Image.new('RGB',(max(p.width for p in group),sum(p.height for p in group)),'white');top=0
    for panel in group:canvas.paste(panel,(0,top));top+=panel.height
    canvas.save(OUT/'pages'/f'review-{year}-{n//3+1}.jpg',quality=80,optimize=True)
  print(json.dumps(dict(year=year,tables=len(found),without_table=coverage[-1]['without_table'],discrepancies=[dict(program=t['program'],**c) for t in tables if t['year']==year for c in t['checks'] if not c['passed']]),ensure_ascii=False),flush=True)
 assert len(tables)==48
 (OUT/'candidate-tables.json').write_text(json.dumps(tables,ensure_ascii=False,indent=2),encoding='utf-8')
 (OUT/'coverage.json').write_text(json.dumps(coverage,ensure_ascii=False,indent=2),encoding='utf-8')
 print('Prepared 48 historical tables and review images; application data unchanged.')
if __name__=='__main__':main()