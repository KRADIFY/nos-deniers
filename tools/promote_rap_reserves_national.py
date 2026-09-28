"""Promote unique, exactly balanced national RAP reserve tables."""
from __future__ import annotations
import hashlib,json,subprocess
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CAND=ROOT/'reports/reserves-national-20260920/candidates.json'
BASE=ROOT/'budget_service/data/reserves-ecologie.json'
SOURCES=ROOT/'reports/rap-actions-national-20260920/sources.json'
TARGET=ROOT/'budget_service/data/reserves-national.json'
RECEIPT=ROOT/'reports/reserves-national-20260920/promotion.json'

def dump(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
 cand=json.loads(CAND.read_text(encoding='utf-8'));base=json.loads(BASE.read_text(encoding='utf-8'))
 counts=Counter((t['year'],t['mission'],t['program']) for t in cand['tables'])
 unique={(r['year'],r['mission'],r['program'],r['measure']):r for r in cand['records']
         if counts[(r['year'],r['mission'],r['program'])]==1}
 existing={(r['year'],r['mission'],r['program'],r['measure']):r for r in base['records']}
 common=set(unique)&set(existing)
 assert len(common)==46
 assert all(unique[k]['cells']==existing[k]['cells'] for k in common)
 new=[unique[k] for k in sorted(set(unique)-set(existing))]
 assert len(new)==528
 source_ids={r['source'] for r in new}
 code=r"""import json,sqlite3
c=sqlite3.connect('file:/data/derived/budget.sqlite?mode=ro',uri=True)
print(json.dumps({x[0]:json.loads(x[1]) for x in c.execute('select id,data from sources')},ensure_ascii=False))"""
 catalogue=json.loads(subprocess.check_output(['docker','exec','lexmachine-budget-web-1','python','-c',code],text=True,encoding='utf-8'))
 sources=[dict(catalogue[s],id=s) for s in sorted(source_ids)]
 for source in sources:
  assert source['sha256'] in {r['source_sha256'] for r in new if r['source']==source['id']}
 checks=[check|{'year':r['year'],'mission':r['mission'],'program':r['program'],'source':r['source'],'page':r['page']}
         for r in new for check in r['checks']]
 registry=dict(updated_at='2026-09-20',
  coverage='264 programme-années nationales supplémentaires en 2023-2025, avec six colonnes publiées et solde arithmétique exact.',
  field_labels=base['field_labels'],sources=sources,records=new,checks=checks,
  notes=[
   "Tables RAP intégrées uniquement lorsque les six colonnes AE/CP, titre 2, autres titres et total sont lisibles et que le solde publié se réconcilie exactement.",
   "Les tables déjà présentes pour la mission Écologie sont conservées dans leur registre relu ; aucun doublon n'est ajouté.",
   "La réserve est publiée au niveau du programme. Aucune ventilation par action, sous-action ou MaPrimeRénov' n'est estimée.",
   "Les pages en double, les colonnes ambiguës et les écarts arithmétiques restent exclus et signalés comme indisponibles."
  ])
 dump(TARGET,registry)
 receipt=dict(programme_years=len(new)//2,records=len(new),sources=len(sources),checks=len(checks),
              manual_records_reproduced=len(common),duplicate_programme_years=sum(n>1 for n in counts.values()),
              sha256=hashlib.sha256(TARGET.read_bytes()).hexdigest())
 dump(RECEIPT,receipt);print(json.dumps(receipt,ensure_ascii=False))
if __name__=='__main__':main()
