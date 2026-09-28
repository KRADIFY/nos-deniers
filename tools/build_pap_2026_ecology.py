"""Checked PAP 2026 Ecology programme amounts, excluding expected FdC/AdP."""
import hashlib,json,sqlite3,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/'reports/finalisation-20260919/evidence'
# Programme, physical page, PLF AE, PLF CP, expected FdC/AdP AE and CP.
VALUES=[
 ('203',17,5930000000,4635813380,3464200000,3512572500),
 ('205',17,290283839,289702930,15250000,15250000),
 ('113',17,378752482,395097182,2918400,2918400),
 ('159',18,670754833,670754833,30000,30000),
 ('181',18,2646231496,1484891584,4320000,4650000),
 ('174',18,1244724835,1232145522,None,None),
 ('345',18,8929936908,8443236908,None,None),
 ('217',19,3151330132,3226661304,16500000,16500000),
 ('380',20,650000000,1085834766,None,None),
 ('235',20,345607012,350307013,21881560,21881560),
]
TOTALS={'PLF':{'AE':24237621537,'CP':21814445422},'FDC_PREVU':{'AE':3525099960,'CP':3573802460}}

def build():
 source=json.loads((EVIDENCE/'pap-ecologie-2026.json').read_text(encoding='utf8'))
 pdf=EVIDENCE/'pap-ecologie-2026.pdf'
 assert hashlib.sha256(pdf.read_bytes()).hexdigest()==source['sha256']
 pages=(EVIDENCE/'pap-ecologie-2026.txt').read_text(encoding='utf8').split('\f')
 db=sqlite3.connect(ROOT/'reports/finalisation-20260919/budget-reference.sqlite')
 labels=dict(db.execute("SELECT program,program_label FROM facts WHERE year=2026 AND mission='TA'"));db.close()
 rows=[];checks=[]
 for program,page,ae,cp,fdcae,fdccp in VALUES:
  lines=pages[page-1].splitlines();line=next(i for i,l in enumerate(lines) if re.match(program+r'\s+[–-]',l.strip()))
  printed=lines[line+1]
  fields=re.split(r'\s{2,}',printed.strip())
  integers=[int(f.replace(' ','')) for f in fields if re.fullmatch(r'\d{1,3}(?: \d{3})*',f)]
  expected=[v for v in (ae,fdcae,cp,fdccp) if v is not None]
  assert integers==expected,(program,integers,expected)
  checks.append({'program':program,'page':page,'printed_values':integers,'passed':True})
  for stage,measure,amount in [('PLF','AE',ae),('PLF','CP',cp),('FDC_PREVU','AE',fdcae),('FDC_PREVU','CP',fdccp)]:
   if amount is None:continue
   field=f'{stage} {measure} 2026 · PAP p. {page} · '+('ouvertures proposées hors FdC/AdP' if stage=='PLF' else 'FdC/AdP attendus, prévision distincte')
   rows.append(dict(year=2026,stage=stage,measure=measure,budget='BG',mission='TA',mission_label='Écologie, développement et mobilité durables',program=program,program_label=labels[program],action='',action_label='',subaction='',subaction_label='',category='',title='',cents=amount*100,source=source['id'],line=page,field=field,approximate=0,page=page))
 for stage,measures in TOTALS.items():
  for measure,total in measures.items():
   assert sum(r['cents'] for r in rows if r['stage']==stage and r['measure']==measure)==total*100
   assert f'{total:,}'.replace(',',' ') in pages[19]
 plan=dict(version='pap-ecologie-2026-1',source=source,rows=rows,totals=TOTALS,checks=checks,
  limits=['Crédits proposés du PAP 2026 ; ce ne sont pas les crédits votés en LFI.',
  'P362 : cases vides préservées ; aucun montant nul créé.',
  'Ventilation par action et sous-action non intégrée dans ce lot.',
  'Les FdC/AdP attendus restent distincts des crédits proposés et des recettes réellement rattachées.'],reviewed_pages=[17,18,19,20])
 out=ROOT/'budget_service/data/pap-ecologie-2026.json';out.write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps({'facts':len(rows),'programmes':len(VALUES),'totals':TOTALS},ensure_ascii=False))
if __name__=='__main__':build()