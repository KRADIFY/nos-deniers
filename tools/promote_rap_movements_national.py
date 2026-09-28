"""Promote only exactly reconciled national RAP movement candidates."""
from __future__ import annotations
import hashlib,json,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'reports/rap-movements-national-20260920/candidates.json'
TARGET=ROOT/'budget_service/data/mouvements-rap-national.json'
OLD=ROOT/'budget_service/data/mouvements-rap-p174.json'
REPORT=ROOT/'reports/rap-movements-national-20260920/promotion.json'

def dump(path,value):
 path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def key(item):
 return (item['year'],item['measure'],item['kind'],item['date'],item['title'],item['sign'],item['amount_cents'])

def labels():
 code=r"""import json,sqlite3
c=sqlite3.connect('file:/data/derived/budget.sqlite?mode=ro',uri=True)
rows=c.execute("select distinct year,mission,mission_label,program,program_label from facts where budget='BG' and year between 2023 and 2025 and action='' and subaction=''").fetchall()
print(json.dumps(rows,ensure_ascii=False))"""
 out=subprocess.check_output(['docker','exec','lexmachine-budget-web-1','python','-c',code],text=True,encoding='utf-8')
 return {(y,m,p):(ml,pl) for y,m,ml,p,pl in json.loads(out)}

def main():
 candidates=json.loads(SOURCE.read_text(encoding='utf-8'))['registries']
 old=json.loads(OLD.read_text(encoding='utf-8'))
 pilot=[r for r in candidates if r['scope']['mission']=='TA' and r['scope']['program']=='174']
 assert len(pilot)==3
 assert {key(x) for x in old['items']}=={key(x) for r in pilot for x in r['items']}
 promoted=[r for r in candidates if not (r['scope']['mission']=='TA' and r['scope']['program']=='174')]
 mapping=labels()
 for registry in promoted:
  scope=registry['scope'];year=scope['years'][0]
  scope['mission_label'],scope['program_label']=mapping[(year,scope['mission'],scope['program'])]
  assert all(x['year']==year and x['mission']==scope['mission'] and x['program']==scope['program'] for x in registry['items'])
  assert len({x['id'] for x in registry['items']})==len(registry['items'])
 registry=dict(updated_at='2026-09-20',source_kind='rap_recapitulation',
  coverage=f"{len(promoted)} programme-annees nationales 2023-2025 rapprochees exactement des credits LFI et ouverts, en plus du programme 174 deja relu.",
  limits=[
   "Récapitulations des RAP 2023-2025 intégrées uniquement lorsque la somme LFI et des mouvements publiés reproduit exactement les crédits ouverts du programme en AE et en CP.",
   "Les huit colonnes titre 2/autres titres, ouvertures/annulations et AE/CP sont conservées ; une cellule vide reste absente et ne devient pas zéro.",
   "Ces lignes expliquent les crédits ouverts et ne s'y ajoutent pas. Elles ne constituent pas une chronologie exhaustive des actes juridiques.",
   "Aucune ventilation par action, sous-action ou dispositif transversal n'est déduite des tableaux au niveau du programme.",
   "Les programmes dont la mise en page ou le rapprochement n'est pas exact restent indisponibles."
  ],registries=promoted)
 dump(TARGET,registry)
 raw=TARGET.read_bytes()
 receipt=dict(registries=len(promoted),items=sum(len(r['items']) for r in promoted),
  evidence_rows=sum(len(r['evidence_rows']) for r in promoted),
  table_totals=sum(len(r['table_totals']) for r in promoted),
  sources=len({s['id'] for r in promoted for s in r['sources']}),
  mission_years=len({(r['scope']['years'][0],r['scope']['mission']) for r in promoted}),
  programmes=len({(r['scope']['mission'],r['scope']['program']) for r in promoted}),
  pilot_items_reproduced=len(old['items']),sha256=hashlib.sha256(raw).hexdigest())
 dump(REPORT,receipt);print(json.dumps(receipt,ensure_ascii=False))

if __name__=='__main__':main()
