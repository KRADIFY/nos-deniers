"""Integrate the visually reviewed Ecology reserve tables, preserving the pilot."""
from pathlib import Path
from copy import deepcopy
import hashlib,json,zipfile
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/reserves-ecologie-2023-2025'
notes={
 '2023-p205':'Le texte décrit une levée intégrale en fin de gestion, malgré le zéro de la ligne Dégels du tableau.',
 '2023-p113':'Le texte décrit une levée de réserve en fin d’année ; le zéro de la ligne Dégels ne couvre donc pas toute l’année.',
 '2023-p159':'Le tableau affiche zéro dégel ; le texte décrit plusieurs dégels en fin de gestion. Ne pas les additionner au tableau ni déduire un stock annuel.',
 '2023-p181':'Le texte décrit des annulations puis la remise à disposition du solde en fin de gestion. Le tableau précède ces opérations.',
 '2023-p217':'Écart dans la source : le solde publié dépasse de 1 € la somme des lignes, en AE comme en CP. Montants publiés conservés. Le texte décrit ensuite un dégel partiel et des annulations en fin de gestion.',
 '2024-p203':'Le dégel de 341,1 M€ décrit dans le texte précède l’annulation de février 2024 ; il ne constitue pas une remise à disposition pour dépenser.',
 '2024-p205':'Le texte distingue le dégel préalable à l’annulation de février et la levée de réserve de fin de gestion, partiellement annulée.',
 '2024-p113':'La page suivante décrit les mouvements de l’année et les annulations de fin de gestion ; ne pas assimiler le solde du tableau au 31 décembre.',
 '2024-p159':'Le tableau publie un solde de 1 123 243 €, confirmé par la somme des lignes. Un paragraphe écrit 1 123 596 € avant de citer un dégel de 1 123 243 € : divergence conservée et signalée.',
 '2024-p181':'Le commentaire, poursuivi page 351, décrit le traitement de la réserve en fin de gestion ; le solde du tableau précède ces opérations.',
 '2024-p217':'Le texte décrit les dégels suivis d’annulation en février, puis un dégel partiel et des annulations en fin de gestion.',
 '2025-p203':'Le texte décrit un surgel ensuite dégelé avant annulation ; les dégels ne mesurent pas les seuls crédits rendus disponibles pour dépenser.',
 '2025-p205':'Le texte décrit un dégel avant annulation puis une levée en fin de gestion. Les montants AE/CP du tableau sont conservés séparément ; le montant final annoncé AE=CP dans le texte ne se rapproche pas des deux colonnes.',
 '2025-p113':'Le texte décrit un surgel en décembre et une annulation en fin de gestion. Le tableau ne permet pas de reconstituer seul une chronologie complète.',
 '2025-p159':'Le dégel de la réserve initiale précède son annulation d’avril ; le surgel restant est présenté séparément.',
 '2025-p181':'Le texte décrit un dégel puis une annulation de la réserve initiale, un surgel et des annulations en fin de gestion.',
 '2025-p217':'Le texte distingue le titre 2 des autres titres et décrit des dégels suivis d’annulation. Le solde ne mesure pas des crédits dépensables.',
 '2025-p235':'Le texte distingue la réserve de personnel et les autres titres annulés en avril. Le tableau ne constitue pas un historique des actes.',
}

def main():
 tables=json.loads((OUT/'candidate-tables.json').read_text(encoding='utf-8'))
 old=json.loads((ROOT/'budget_service/data/reserves-p174.json').read_text(encoding='utf-8'))
 assert len(tables)==28
 assert all((OUT/t['image']).exists() for t in tables)
 assert [(t['key'],c['measure'],c['field'],c['difference_cents']) for t in tables for c in t['checks'] if not c['passed']]==[
  ('2023-p217','AE','other_titles_cents',100),('2023-p217','AE','total_cents',100),('2023-p217','CP','other_titles_cents',100),('2023-p217','CP','total_cents',100)]
 review=dict(reviewed_tables=[t['key'] for t in tables],column_layout='AE: T2, HT2, total; CP: T2, HT2, total',source_values_preserved=True,notes=notes)
 (OUT/'reviewed-tables.json').write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf-8')
 backup=OUT/'before-extension.zip'
 if not backup.exists():
  with zipfile.ZipFile(backup,'w',zipfile.ZIP_DEFLATED) as z:
   for name in ['budget_service/reserves.py','budget_service/data/reserves-p174.json','public/explorer.html','public/assets/explorer.js','public/assets/explorer.css','tests/test_reserves.py','tests/reserves-ui.cjs']:
    z.write(ROOT/name,name)
 result=deepcopy(old)
 for table in tables:
  for row in table['records']:
   if row['program']=='174':
    pilot=next(r for r in old['records'] if (r['year'],r['measure'])==(row['year'],row['measure']))
    assert all(pilot[k]==row[k] for k in ['cells','page','source','source_sha256','raw_lines'])
    continue
   row=deepcopy(row)
   row['remaining_label']='Réserve disponible avant mise en place du schéma de fin de gestion'
   row['note']=notes.get(table['key'],'Les montants sont ceux du tableau publié ; le solde ne constitue pas un stock certifié au 31 décembre.')
   row['context_pages']=[row['page'],row['page']+1] if table['key'] in ('2024-p113','2024-p181') else [row['page']]
   row['checks']=[c for c in table['checks'] if c['measure']==row['measure']]
   row['numeric_validation']='published_with_balance_difference' if any(not c['passed'] for c in row['checks']) else 'published_columns_and_balance_reconciled'
   result['records'].append(row)
  result['checks'].extend(dict(year=table['year'],program=table['program'],**c) for c in table['checks'])
 result['records'].sort(key=lambda r:(r['year'],int(r['program']),r['measure']))
 coverage=json.loads((OUT/'coverage.json').read_text(encoding='utf-8'))
 missing=[]
 for c in coverage:
  for program in c['without_table']:
   p=next(p for p in c['programmes'] if p['program']==program)
   source=next(t['source'] for t in tables if t['year']==c['year'])
   for measure in ('AE','CP'):
    missing.append(dict(year=c['year'],budget='BG',mission='TA',program=program,program_label=p['program_label'],measure=measure,page=p['programme_page'],source=source['id'],source_sha256=source['sha256'],cells={},note='Aucun tableau de réserve trouvé dans la section de ce programme. Aucune valeur n’est déduite de cette absence.',remaining_label='Réserve disponible avant mise en place du schéma de fin de gestion',table_unavailable=True,numeric_validation='table_unavailable'))
 result['missing_tables']=missing
 result['coverage']='Réserves Écologie : 9 programmes en 2023 et 2024, 10 en 2025. De 2017 à 2022 : programme 174 uniquement. Aucun total de mission n’est calculé ; la part MaPrimeRénov’ n’est pas isolée.'
 result['coverage_by_year']=[dict(year=c['year'],integrated_programmes=sorted({t['program'] for t in tables if t['year']==c['year']}),programmes_without_table=c['without_table']) for c in coverage]
 result['notes'].append('Programme 217 en 2023 : écart de 1 € sur le solde publié en AE et en CP. Programme 159 en 2024 : divergence entre le solde du tableau et un paragraphe explicatif. Aucune correction des montants sources.')
 result.pop('version',None)
 result['version']=hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
 assert len(result['records'])==68 and len(missing)==2
 assert len({(r['year'],r['program'],r['measure']) for r in result['records']})==68
 (ROOT/'budget_service/data/reserves-ecologie.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 (OUT/'integration.json').write_text(json.dumps(dict(records=68,added_records=50,missing_table_rows=2,reviewed_tables=28,checks=392,arithmetic_discrepancies=4,version=result['version'],pilot_unchanged=True),ensure_ascii=False,indent=2),encoding='utf-8')
 print('50 observations added; 18 pilot observations unchanged; 28 tables checked visually; no SQL or vector corpus changes.')
if __name__=='__main__':main()