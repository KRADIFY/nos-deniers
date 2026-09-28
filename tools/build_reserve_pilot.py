"""Publish the first checked reserve series from already-collected RAPs.

The scope is deliberately P174 only. Other candidate tables need their own
programme/perimeter checks. No annual budget facts or vectorization files change.
"""
from pathlib import Path
import hashlib,json,re,urllib.request

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/reserves-et-consignes-20260909'
inventory=json.loads((OUT/'rap-reserves-pages.json').read_text(encoding='utf-8'))
catalogue=json.load(urllib.request.urlopen('http://127.0.0.1:8552/api/documents?format=pdf'))['items']
page_numbers={2017:393,2018:385,2019:417,2020:407,2021:414,2022:440,2023:431,2024:437,2025:413}
labels={
 'initial':'Mise en réserve initiale',
 'surgels':'Surgels',
 'degels':'Dégels',
 'cancellations':'Annulations / réserve en cours de gestion',
 'remaining':'Réserve disponible avant mise en place',
}
records=[];sources=[];checks=[]
for year,page in page_numbers.items():
 doc=next(x for x in inventory if x['year']==year)
 assert hashlib.sha256(Path(doc['path']).read_bytes()).hexdigest()==doc['sha256']
 source=next(x for x in catalogue if x.get('sha256')==doc['sha256'])
 sources.append(source)
 text=(OUT/f'rap-ecologie-{year}.txt').read_text(encoding='utf-8').split('\f')[page-1]
 extracted={};raw_lines={}
 for line in text.splitlines():
  for key,label in labels.items():
   if not line.strip().startswith(label):continue
   fields=re.split(r'\s{2,}',line.strip())
   assert fields[0].startswith(label),(year,fields)
   numbers=fields[1:]
   assert all(re.fullmatch(r'[+-]?\d{1,3}(?: \d{3})*',x) for x in numbers),(year,numbers)
   values=[int(x.replace(' ',''))*100 for x in numbers]
   if year in (2017,2018):
    assert len(values)==4
    values=[None,*values[:2],None,*values[2:]]
   assert len(values)==6,(year,values)
   assert key not in extracted
   extracted[key]=values;raw_lines[key]=line
 assert set(extracted)==set(labels) if year in (2017,2018,2022) else set(extracted)==set(labels)-{'cancellations'}
 for measure,offset in [('AE',0),('CP',3)]:
  cells={key:{'title2_cents':vals[offset],'other_titles_cents':vals[offset+1],'total_cents':vals[offset+2]} for key,vals in extracted.items()}
  for key,cell in cells.items():
   # Empty T2 is preserved. Equality of the printed HT2 and total is checked,
   # without making an observation of zero for the unprinted T2 cell.
   assert cell['total_cents']==sum(x for x in [cell['title2_cents'],cell['other_titles_cents']] if x is not None)
   checks.append(dict(year=year,measure=measure,field=key,check='printed_columns_reconcile',passed=True))
  assert cells['remaining']['total_cents']==sum(v['total_cents'] for k,v in cells.items() if k!='remaining')
  checks.append(dict(year=year,measure=measure,check='sum_of_published_reserve_rows',passed=True))
  records.append(dict(year=year,budget='BG',mission='TA',program='174',program_label='Énergie, climat et après-mines',measure=measure,source=source['id'],page=page,
   source_sha256=source['sha256'],cells=cells,raw_lines=raw_lines,
   remaining_label='Réserve disponible avant mise en place du schéma de fin de gestion',
   numeric_validation='published_columns_and_balance_reconciled',
   note=('Le texte suivant le tableau décrit un dégel de fin d’exercice. Les zéros du tableau ne prouvent donc pas l’absence de dégel sur toute l’année.' if year==2018 else 'Les lignes décrivent le tableau publié dans ce RAP ; le solde ne constitue pas un stock au 31 décembre.')
  ))
assert len(records)==18 and len(sources)==9
data=dict(updated_at='2026-09-09',coverage='Première série intégrée : programme 174 de la mission Écologie, de 2017 à 2025. Les autres programmes et la part MaPrimeRénov’ restent à extraire. Aucun total de mission n’est calculé.',
 field_labels=labels,sources=sources,records=records,checks=checks,
 notes=['Un dégel peut précéder une annulation : il ne correspond pas nécessairement à des crédits rendus disponibles pour dépenser.',
 'Le solde est celui du tableau avant le schéma de fin de gestion, pas un stock certifié au 31 décembre.',
 'Une ligne d’annulation absente du tableau reste non renseignée, jamais assimilée à zéro.',
 'Les tableaux ne constituent pas une chronologie exhaustive des actes de gestion. Les paragraphes de justification doivent être rapprochés séparément.',
 'Ces réserves ne sont ajoutées ni aux crédits ouverts, ni aux annulations du registre juridique, ni au consommé.'])
data['version']=hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
dest=ROOT/'budget_service/data/reserves-p174.json'
dest.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'reserves-p174-controle.json').write_text(json.dumps(dict(records=len(records),checks=len(checks),version=data['version'],sources=len(sources),pages=page_numbers),ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(records=len(records),checks=len(checks),sources=len(sources),version=data['version'])))
