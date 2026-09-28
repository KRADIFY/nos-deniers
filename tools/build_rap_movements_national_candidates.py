"""Extract and reconcile national RAP credit-movement tables without mutating facts."""
from __future__ import annotations
import argparse,hashlib,json,re,subprocess,sys,unicodedata
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import fitz
from rap_program_context import programme_context

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from budget_service.reconciliation import assess_difference, difference_note, capped_rounding_bound
REPORT=ROOT/'reports/rap-movements-national-20260920'
SOURCES=ROOT/'reports/rap-actions-national-20260920/sources.json'
TEXT=ROOT/'reports/rap-actions-national-20260920/text'
CAPTIONS={
 "DECRETS D'ANNULATION DE FDC OU DE ADP":('ANNULATION_FDC_ADP','FDC'),
 'ARRETES DE REPORT DE CREDITS':('REPORT_GENERAL','REPORT_ENTRANT'),
 'LOIS DE FINANCES RECTIFICATIVE':('LOI_FINANCES','LEGIS'),
 'LOIS DE FINANCES DE FIN DE GESTION':('LOI_FINANCES','LEGIS'),
 'ARRETES DE RATTACHEMENT DE ADP':('RATTACHEMENT_ADP','FDC'),
 'ARRETES DE RATTACHEMENT DE FDC':('RATTACHEMENT_FDC','FDC'),
 'ARRETES DE REPORT DE FDC':('REPORT_FDC','REPORT_ENTRANT'),
 "ARRETES DE REPORT D'AENE":('REPORT_AENE','REPORT_ENTRANT'),
 'ARRETES DE REPORT GENERAL HORS FDC HORS AENE':('REPORT_GENERAL','REPORT_ENTRANT'),
 'DECRETS DE TRANSFERT':('TRANSFERT','REGLEMENT'),
 "DECRETS D'ANNULATION":('ANNULATION','LEGIS'),
 'DECRETS DE VIREMENT':('VIREMENT','REGLEMENT'),
 'LOIS DE FINANCES RECTIFICATIVES':('LOI_FINANCES','LEGIS'),
 'LOI DE FINANCES DE FIN DE GESTION':('LOI_FINANCES','LEGIS'),
 'ARRETES DE REPARTITION POUR MESURES GENERALES':('REPARTITION','REGLEMENT'),
 'DECRETS DE DEPENSES ACCIDENTELLES':('DEPENSES_ACCIDENTELLES','REGLEMENT'),
 'TOTAL DES OUVERTURES ET ANNULATIONS (Y.C. FDC ET ADP)':('TOTAL',None),
}
COLUMNS=[dict(direction=d,sign=s,measure=m,title=t) for d,s in [('opening',1),('cancellation',-1)]
         for m in ('AE','CP') for t in ('2','HT2')]

def dump(path,value):
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def norm(text):
 return ' '.join(unicodedata.normalize('NFKD',text).encode('ascii','ignore').decode().upper().split())

def digest(path):
 with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def canonical():
 code=r"""import json,sqlite3
c=sqlite3.connect('file:/data/derived/budget.sqlite?mode=ro',uri=True);c.row_factory=sqlite3.Row
q="select * from facts where budget='BG' and year between 2023 and 2025 and action='' and subaction='' and stage in ('LFI','OUVERT','FDC','REPORT_ENTRANT','REGLEMENT','LEGIS') order by year,mission,program,measure,stage,title"
print(json.dumps([dict(x) for x in c.execute(q)],ensure_ascii=False))"""
 out=subprocess.check_output(['docker','exec','lexmachine-budget-web-1','python','-c',code],text=True,encoding='utf-8')
 return json.loads(out)

def lines_of(page):
 return sorted([dict(text=''.join(s['text'] for s in line['spans']).strip(),
                          bbox=[round(float(n),3) for n in line['bbox']])
                for block in page.get_text('dict')['blocks'] for line in block.get('lines',[])],
               key=lambda x:(round(x['bbox'][1],1),x['bbox'][0]))

def midpoint(line):return (line['bbox'][0]+line['bbox'][2])/2

def cells_at(lines,label,headers):
 values=[dict(column,amount_cents=None,raw_text=None) for column in COLUMNS]
 for line in lines:
  if abs(line['bbox'][1]-label['bbox'][1])>1.0 or line['bbox'][0]<=label['bbox'][2]:continue
  raw=line['text'].strip()
  if not raw:continue
  if not re.fullmatch(r'[+-]?\d[\d\s]*(?:,\d{1,2})?',raw):continue
  index=min(range(8),key=lambda i:abs(midpoint(headers[i])-midpoint(line)))
  if abs(midpoint(headers[index])-midpoint(line))>=30 or values[index]['amount_cents'] is not None:
   raise ValueError(('ambiguous_numeric_cell',raw,line['bbox']))
  amount=Decimal(re.sub(r'\s+','',raw).replace(',','.'))*100
  if amount!=amount.to_integral_value():raise ValueError(('fractional_cent',raw))
  values[index].update(amount_cents=abs(int(amount)),raw_text=raw,bbox=line.get('physical_bbox',line['bbox']))
 return values

def parse_date(raw):
 if re.fullmatch(r'\d{2}/\d{4}',raw):
  return datetime.strptime(raw,'%m/%Y').strftime('%Y-%m'),'month','month'
 if re.fullmatch(r'\d{2}/\d{2}/\d{4}',raw):
  return datetime.strptime(raw,'%d/%m/%Y').date().isoformat(),'day','signature'
 raise ValueError(('unexpected_date',raw))

def programmes(text):
 return {n:r['program'] for n,r in programme_context(text).items()}

def extract_page(page,year,mission,program,number,source,sha):
 lines=lines_of(page)
 for line in lines:
  line['physical_page']=number;line['physical_bbox']=list(line['bbox'])
 # Narrative subheadings also repeat these captions. Only table headings have
 # opening/cancellation headers directly beneath them.
 captions=[x for x in lines if norm(x['text']) in CAPTIONS and
           any(norm(h['text'])=='OUVERTURES' and 0<h['bbox'][1]-x['bbox'][1]<65 for h in lines)]
 if not captions:return [],[]
 rows=[];totals=[]
 for index,caption in enumerate(captions):
  end_y=captions[index+1]['bbox'][1] if index+1<len(captions) else page.rect.height
  area=[x for x in lines if caption['bbox'][1]<x['bbox'][1]<end_y]
  # A recap table may start at the bottom of a page and finish on the next.
  # Only consume the continuation before the next table caption.
  total_labels=lambda ls:[x for x in ls if norm(x['text']) in ('TOTAL','TOTAL GENERAL')]
  if not total_labels(area) and index==len(captions)-1 and number<len(page.parent):
   following=lines_of(page.parent[number]);offset=float(page.rect.height)
   next_caption=next((x['bbox'][1] for x in following if norm(x['text']) in CAPTIONS),float('inf'))
   for line in following:
    if line['bbox'][1]>=next_caption:break
    line=dict(line,physical_page=number+1,physical_bbox=list(line['bbox']))
    line['bbox']=[line['bbox'][0],line['bbox'][1]+offset,line['bbox'][2],line['bbox'][3]+offset]
    area.append(line)
  by_page={}
  for physical_page in {x['physical_page'] for x in area}:
   hh=[x for x in area if x['physical_page']==physical_page and x['text'] in ('Titre 2','Autres titres')]
   if hh:
    first_y=min(x['bbox'][1] for x in hh)
    by_page[physical_page]=sorted([x for x in hh if abs(x['bbox'][1]-first_y)<2],key=lambda x:x['bbox'][0])
  headers=by_page.get(number,[])
  if any(len(hh)!=8 for hh in by_page.values()):raise ValueError(('continuation_headers',number))
  if len(headers)!=8 or [x['text'] for x in headers]!=['Titre 2','Autres titres']*4:
   raise ValueError(('headers',caption['text'],len(headers)))
  kind,stage=CAPTIONS[norm(caption['text'])]
  table_id=f'rap-{year}-{mission.lower()}-{program}-p{number}-{kind.lower()}-{index}'
  labels=total_labels(area)
  if not labels:raise ValueError(('total_label',table_id,0))
  total_label=labels[0]
  area=[x for x in area if x['bbox'][1]<=total_label['bbox'][1]+1]
  date_lines=[x for x in area if re.fullmatch(r'\d{2}/(?:\d{2}/)?\d{4}',x['text'])]
  if kind!='TOTAL' and not date_lines:raise ValueError(('no_dates',table_id))
  table_rows=[]
  for seq,line in enumerate(date_lines):
   date,precision,date_kind=parse_date(line['text']);cells=cells_at(area,line,by_page[line['physical_page']])
   row=dict(row_id=f'{table_id}-{date}-{seq}',table_id=table_id,year=year,budget='BG',mission=mission,
            program=program,page=line['physical_page'],source=source,sha256=sha,kind=kind,reconciles_stage=stage,
            date=date,date_precision=precision,date_kind=date_kind,table_title=caption['text'],
            source_date=line['text'],cells=cells,bbox=[line['physical_bbox'][0],line['physical_bbox'][1],550.0,line['physical_bbox'][3]],
            published_precision="Montants publies a l'euro dans le RAP.")
   rows.append(row);table_rows.append(row)
  total_cells=cells_at(area,total_label,by_page[total_label['physical_page']]);table_checks=[]
  if table_rows:
   for i,cell in enumerate(total_cells):
    amounts=[r['cells'][i]['amount_cents'] for r in table_rows if r['cells'][i]['amount_cents'] is not None]
    expected=sum(amounts) if amounts else None
    delta=(cell['amount_cents'] or 0)-(expected or 0)
    bound=capped_rounding_bound(len(amounts),0) if amounts else 0
    if abs(delta)>bound:raise ValueError(('table_total',table_id,i,expected,cell['amount_cents']))
    table_checks.append(dict(column=i,difference_cents=delta,rounding_bound_cents=bound,
                             status='exact' if delta==0 else 'published_rounding_difference'))
  totals.append(dict(table_id=table_id,year=year,budget='BG',mission=mission,program=program,page=total_label['physical_page'],
                     source=source,sha256=sha,kind=kind,table_title=caption['text'],cells=total_cells,
                     headers=[dict(column,printed_label=h['text'],bbox=h['physical_bbox']) for column,h in zip(COLUMNS,by_page[total_label['physical_page']])],
                     is_grand_total=kind=='TOTAL',checked_against_dated_rows=bool(table_rows),checks=table_checks))
 return rows,totals

def main():
 global REPORT
 ap=argparse.ArgumentParser();ap.add_argument('--sources',type=Path,default=SOURCES)
 ap.add_argument('--output',type=Path,default=REPORT);args=ap.parse_args();REPORT=args.output
 source_rows=json.loads(args.sources.read_text(encoding='utf-8'));parents=canonical()
 parent_groups=defaultdict(list)
 for row in parents:parent_groups[(row['year'],row['mission'],row['program'],row['measure'],row['stage'])].append(row)
 candidates=[];gaps=[];stats=defaultdict(int)
 for source in source_rows:
  year=source['year'];mission=source['mission'];path=Path(source['path'])
  if digest(path)!=source['sha256']:
   gaps.append(dict(year=year,mission=mission,reason='physical_sha256_mismatch'));continue
  text=Path(source.get('text_path',TEXT/(source['sha256']+'.txt'))).read_text(encoding='utf-8')
  page_program=programmes(text);wanted=[]
  for number,page_text in enumerate(text.split('\f'),1):
   labels={norm(line) for line in page_text.splitlines()}
   if labels.intersection(CAPTIONS):
    wanted.append((number,page_program[number]))
  per_program=defaultdict(lambda:{'evidence':[],'totals':[],'failures':[]})
  with fitz.open(path) as doc:
   for number,program in wanted:
    if not program:
     gaps.append(dict(year=year,mission=mission,page=number,reason='program_context_missing'));continue
    try:
     rows,totals=extract_page(doc[number-1],year,mission,program,number,source['source'],source['sha256'])
     per_program[program]['evidence']+=rows;per_program[program]['totals']+=totals
    except Exception as exc:
     per_program[program]['failures'].append(dict(page=number,detail=repr(exc)))
  for program,data in sorted(per_program.items()):
   key=dict(year=year,mission=mission,program=program)
   if data['failures']:
    gaps.append(dict(**key,reason='page_decode_failed',failures=data['failures']));continue
   grands=[t for t in data['totals'] if t['is_grand_total']]
   if len(grands)!=1:
    gaps.append(dict(**key,reason='grand_total_missing_or_duplicate',count=len(grands)));continue
   grand=grands[0];valid=True;differences=[];grand_checks=[]
   for i,column in enumerate(COLUMNS):
    amounts=[r['cells'][i]['amount_cents'] for r in data['evidence'] if r['cells'][i]['amount_cents'] is not None]
    expected=sum(amounts) if amounts else None
    delta=(grand['cells'][i]['amount_cents'] or 0)-(expected or 0)
    bound=capped_rounding_bound(len(amounts),0) if amounts else 0
    grand_checks.append(dict(column=i,difference_cents=delta,rounding_bound_cents=bound,
      status='exact' if delta==0 else 'published_rounding_difference'))
    if abs(delta)>bound:
     valid=False;differences.append(dict(column=column,items=expected,grand=grand['cells'][i]['amount_cents']))
   items=[]
   for row in data['evidence']:
    for cell in row['cells']:
     if cell['amount_cents'] is None:continue
     items.append(dict(id=row['row_id']+'/'+cell['measure']+'/'+cell['title']+'/'+cell['direction'],
      row_id=row['row_id'],year=year,budget='BG',mission=mission,program=program,title=cell['title'],
      measure=cell['measure'],kind=row['kind'],date=row['date'],date_precision=row['date_precision'],
      date_kind=row['date_kind'],sign=cell['sign'],amount_cents=cell['amount_cents'],source=source['source'],
      sha256=source['sha256'],page=row['page'],field=f"{row['table_title']} · {row['source_date']} · {cell['direction']} · {cell['measure']} · {cell['title']}",
      reconciles_stage=row['reconciles_stage'],linked_act_id=None))
   reconciliations=[]
   for measure in ('AE','CP'):
    lfi=parent_groups.get((year,mission,program,measure,'LFI'),[])
    opened=parent_groups.get((year,mission,program,measure,'OUVERT'),[])
    if not lfi or not opened:
     valid=False;differences.append(dict(measure=measure,reason='canonical_lfi_or_opened_missing'))
     continue
    movement=sum(x['sign']*x['amount_cents'] for x in items if x['measure']==measure)
    delta=sum(x['cents'] for x in lfi)+movement-sum(x['cents'] for x in opened)
    printed=[c for c in grand['cells'] if c['measure']==measure and c['amount_cents'] is not None]
    printed_net=sum(c['sign']*c['amount_cents'] for c in printed)
    printed_delta=sum(x['cents'] for x in lfi)+printed_net-sum(x['cents'] for x in opened)
    bound=50*len([x for x in items if x['measure']==measure])
    printed_bound=50*len(printed)
    reference=sum(x['cents'] for x in opened)
    check=assess_difference(reference+delta,reference,len([x for x in items if x['measure']==measure]))
    printed_check=assess_difference(reference+printed_delta,reference,len(printed))
    acceptable=check['accepted'] and printed_check['accepted']
    reconciliations.append(dict(year=year,measure=measure,stage='OUVERT',status=check['status'],
     source=source['source'],sha256=source['sha256'],lfi_cents=sum(x['cents'] for x in lfi),
     reported_net_cents=movement,lfi_plus_reported_cents=sum(x['cents'] for x in lfi)+movement,
     canonical_cents=sum(x['cents'] for x in opened),difference_cents=delta,
     rounding_bound_cents=check['rounding_bound_cents'],materiality_bound_cents=check['materiality_bound_cents'],
     printed_net_cents=printed_net,printed_difference_cents=printed_delta,printed_check=printed_check,
     printed_rounding_bound_cents=printed_check['rounding_bound_cents'],
     note=difference_note(check)+" Montants datés contrôlés aussi contre le total imprimé du RAP."))
    if not acceptable:valid=False;differences.append(dict(measure=measure,reason='lfi_plus_movements_differs_from_opened',difference_cents=delta,printed_difference_cents=printed_delta))
   if not valid:
    gaps.append(dict(**key,reason='reconciliation_failed',differences=differences,
                     evidence_rows=len(data['evidence']),items=len(items)));continue
   refs=[dict(id=source['source'],sha256=source['sha256'],year=year,
              pages=sorted({x['page'] for x in data['evidence']}|{x['page'] for x in data['totals']}))]
   candidates.append(dict(scope=dict(years=[year],budget='BG',mission=mission,program=program,titles=['2','HT2']),
    sources=refs,items=items,evidence_rows=data['evidence'],table_totals=data['totals'],
    reconciliations=reconciliations,grand_total_checks=grand_checks))
   stats['items']+=len(items);stats['evidence_rows']+=len(data['evidence']);stats['tables']+=len(data['totals'])
 dump(REPORT/'candidates.json',{'registries':candidates});dump(REPORT/'gaps.json',gaps)
 summary=dict(sources=len(source_rows),registries=len(candidates),gaps=len(gaps),**stats)
 dump(REPORT/'candidate-summary.json',summary);print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':main()
