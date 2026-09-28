"""Extract exactly balanced national RAP reserve tables from cached physical-PDF text."""
from __future__ import annotations
import argparse,hashlib,json,re,unicodedata
from pathlib import Path
from rap_program_context import programme_context

ROOT=Path(__file__).resolve().parents[1]
SOURCES=ROOT/'reports/rap-actions-national-20260920/sources.json'
TEXT=ROOT/'reports/rap-actions-national-20260920/text'
OUT=ROOT/'reports/reserves-national-20260920'
LABELS={'initial':'Mise en réserve initiale','surgels':'Surgels','degels':'Dégels',
 'cancellations':'Annulations / réserve en cours de gestion','remaining':'Réserve disponible avant mise en place'}
# Reviewed against the printed six-column tables; retain the published euros
# and expose the one-euro discrepancy, never silently repair it.
REVIEWED_BALANCE_DIFFERENCES={(2023,'DA','178',134),(2023,'DA','212',259),
 (2023,'RA','191',538),(2023,'TA','217',531),(2025,'SF','350',143)}

def dump(name,value):
 OUT.mkdir(parents=True,exist_ok=True);(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def programmes(text):
 return {n:(r['program'],r['label']) for n,r in programme_context(text).items()}

def main():
 global OUT, SOURCES
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=OUT)
 ap.add_argument('--sources',type=Path,default=SOURCES)
 args=ap.parse_args();OUT=args.output;SOURCES=args.sources
 sources=json.loads(SOURCES.read_text(encoding='utf-8'));records=[];gaps=[];tables=[]
 for source in sources:
  text=Path(source.get('text_path',TEXT/(source['sha256']+'.txt'))).read_text(encoding='utf-8');contexts=programmes(text)
  pages=text.split('\f')
  for page_no,page in enumerate(pages,1):
   if not re.search(r'^Mise en réserve initiale\s{2,}[+-]?\d',page,re.M):continue
   program,program_label=contexts[page_no]
   key=dict(year=source['year'],mission=source['mission'],program=program,page=page_no,source=source['source'])
   if not program:
    gaps.append(dict(**key,reason='program_context_missing'));continue
   extracted={};raw={};field_pages={}
   start=next(i for i,line in enumerate(page.splitlines()) if re.match(r'^Mise en réserve initiale\s{2,}[+-]?\d',line))
   table_lines=[(page_no,line) for line in page.splitlines()[start:]]
   if page_no<len(pages) and contexts[page_no+1][0]==program:
    table_lines += [(page_no+1,line) for line in pages[page_no].splitlines()]
   for physical_page,line in table_lines:
    for name,label in LABELS.items():
     if not line.startswith(label):continue
     fields=re.split(r'\s{2,}',line.strip())
     if len(fields)!=7 or not all(re.fullmatch(r'[+-]?\d{1,3}(?: \d{3})*',v) for v in fields[1:]):
      gaps.append(dict(**key,reason='six_columns_not_unambiguous',field=name,raw=line));extracted={};break
     extracted[name]=[int(v.replace(' ',''))*100 for v in fields[1:]];raw[name]=line;field_pages[name]=physical_page
    if 'remaining' in extracted:break
    if not extracted and gaps and gaps[-1].get('page')==page_no and gaps[-1].get('source')==source['source']:break
   if not extracted:continue
   required={'initial','surgels','degels','remaining'}
   if not required<=set(extracted):
    gaps.append(dict(**key,reason='required_rows_missing',rows=sorted(extracted)));continue
   rows=[];checks=[];valid=True
   for measure,offset in [('AE',0),('CP',3)]:
    cells={name:dict(title2_cents=values[offset],other_titles_cents=values[offset+1],total_cents=values[offset+2])
           for name,values in extracted.items()}
    for field,cell in cells.items():
     delta=cell['total_cents']-cell['title2_cents']-cell['other_titles_cents']
     checks.append(dict(measure=measure,field=field,check='printed_columns',difference_cents=delta,passed=delta==0))
     valid &= delta==0
    for column in ('title2_cents','other_titles_cents','total_cents'):
     delta=cells['remaining'][column]-sum(cell[column] for name,cell in cells.items() if name!='remaining')
     checks.append(dict(measure=measure,field=column,check='printed_balance',difference_cents=delta,passed=delta==0))
     valid &= delta==0
    rows.append(dict(year=source['year'],budget='BG',mission=source['mission'],program=program,
     program_label=program_label,measure=measure,source=source['source'],source_sha256=source['sha256'],
     page=page_no,cells=cells,raw_lines=raw,remaining_label='Réserve disponible avant mise en place du schéma de fin de gestion',
     note="Tableau RAP publié au niveau du programme ; aucune ventilation par action ou dispositif n'est déduite.",
     context_pages=sorted(set(field_pages.values())),field_pages=field_pages,
     programme_page=programme_context(text)[page_no]['opening_page'],
     checks=[c for c in checks if c['measure']==measure],
     numeric_validation='published_columns_and_balance_reconciled'))
   if not valid:
    failures=[c for c in checks if not c['passed']]
    reviewed=(source['year'],source['mission'],program,page_no) in REVIEWED_BALANCE_DIFFERENCES
    if not reviewed or any(c['check']!='printed_balance' or abs(c['difference_cents'])!=100 for c in failures):
     gaps.append(dict(**key,reason='printed_arithmetic_mismatch',checks=failures));continue
    for row in rows:
     if any(not c['passed'] for c in row['checks']):
      row['numeric_validation']='published_with_balance_difference'
      row['note']='Écart de 1 € dans le solde du tableau source, vérifié dans le PDF. Montants publiés conservés sans correction ; aucune ventilation par action ou dispositif déduite.'
   records+=rows;tables.append(dict(**key,program_label=program_label,checks=checks))
 dump('candidates.json',{'records':records,'tables':tables})
 dump('gaps.json',gaps)
 summary=dict(sources=len(sources),tables=len(tables),records=len(records),gaps=len(gaps),
              mission_years=len({(t['year'],t['mission']) for t in tables}),
              programme_years=len({(t['year'],t['mission'],t['program']) for t in tables}))
 dump('summary.json',summary);print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':main()
