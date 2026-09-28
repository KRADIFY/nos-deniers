"""Merge visually reviewed historical reserve tables without replacing prior work."""
from pathlib import Path
from copy import deepcopy
import hashlib,json,zipfile
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/reserves-ecologie-2017-2022-20260910'
BASELINE='84d7de2eddaf44df84916d32b2554ef485609441323d5c39939cde7b3e5270ec'
NOTES={
'2017-p113':'Le commentaire distingue les annulations sur réserve des autres crédits annulés. Le total du décret ne se confond pas avec la ligne du tableau.',
'2017-p159':'Le texte cite aussi les annulations de novembre. Le tableau reste un arrêté avant le schéma de fin de gestion.',
'2017-p181':'Le texte décrit des surgels et annulations supplémentaires en fin de gestion, y compris sur le titre 2 ; ils ne sont pas ajoutés au tableau.',
'2017-p203':'Le dégel de mars et les surgels d’avril sont détaillés page suivante. Les montants des décrets portent sur un périmètre différent de la seule réserve.',
'2017-p205':'Le texte décrit un second surgel et une annulation en novembre, après lesquels la réserve est vide. Le solde du tableau précède ces opérations.',
'2017-p217':'Le titre 2 comprend la réserve du programme 337, transférée au programme 217. Le texte décrit aussi des dégels et annulations après le schéma de fin de gestion.',
'2017-p345':'Le tableau affiche zéro dégel ; le texte décrit un dégel à l’automne. Le solde du tableau ne représente pas la situation finale de l’année.',
'2018-p113':'Le texte décrit une annulation de la réserve par la LFR de décembre. Les zéros du tableau ne signifient pas absence de mouvement sur toute l’année.',
'2018-p159':'Le texte décrit une annulation intégrale en décembre. Le tableau précède cette opération.',
'2018-p181':'Le texte distingue l’annulation de la réserve hors titre 2 et un dégel de crédits de pensions. Ces opérations ne sont pas reportées dans les lignes de mouvements du tableau.',
'2018-p203':'Le texte, poursuivi page suivante, décrit un dégel avant annulation en totalité en fin de gestion. Le zéro de la ligne Dégels ne couvre pas toute l’année.',
'2018-p205':'Le texte décrit un dégel de 2 081 616 € et une annulation de 2 299 066 € en fin de gestion, malgré les zéros du tableau.',
'2018-p217':'Le tableau publie un dégel de 41 520 € ; le texte page suivante le libelle « 41 520 M€ ». Valeur du tableau conservée. Le commentaire décrit aussi des mouvements de personnel et des annulations de fin de gestion.',
'2018-p345':'Le texte décrit un dégel total en AE et partiel en CP à l’automne, malgré le zéro de la ligne Dégels du tableau.',
'2019-p113':'Le texte décrit l’annulation de la totalité de la réserve en décembre. La ligne Annulations, absente du tableau, reste non renseignée.',
'2019-p159':'Le commentaire décrit l’annulation intégrale en décembre. L’absence de ligne Annulations dans le tableau ne signifie pas zéro annulation.',
'2019-p181':'Le texte décrit des gels et annulations supplémentaires en fin de gestion, ainsi que des crédits gelés non annulés pour Le Signal. Le solde du tableau n’est pas le solde final.',
'2019-p203':'Le texte indique que la réserve a été annulée en totalité en décembre. Cette annulation n’est pas inscrite dans le tableau.',
'2019-p205':'Le texte décrit un dégel de 860 000 € en AE et l’annulation du reste en fin de gestion. Le zéro de la ligne Dégels ne couvre pas toute l’année.',
'2019-p217':'Le texte évoque une exonération de réserve gouvernementale, mais le tableau conserve une réserve de titre 2. En CP, les totaux de la réserve initiale et du solde sont inférieurs de 1 € à la colonne titre 2. Montants publiés conservés.',
'2019-p345':'Le texte décrit un dégel intégral en AE. Le zéro de la ligne Dégels du tableau ne couvre pas toute l’année.',
'2020-p113':'Le dégel de 7 M€ en CP de fin d’année est explicitement exclu du tableau par le RAP. Le texte décrit aussi les annulations du solde. Le zéro en CP ne signifie pas absence de dégel annuel.',
'2020-p159':'Le texte décrit une levée intégrale par la LFR de novembre, malgré le zéro de la ligne Dégels du tableau.',
'2020-p181':'Le commentaire décrit une annulation en fin de gestion et la remise à disposition du solde en CP. Le tableau précède ces opérations.',
'2020-p203':'Le texte décrit une réserve répartie entre plusieurs programmes et un compte spécial. Seule la part publiée dans le tableau du programme 203 est retenue ici.',
'2020-p205':'Le texte décrit un dégel supplémentaire de fin d’année pour les armateurs ferries. Il ne faut pas confondre ce mouvement avec les 4 M€ déjà inscrits au tableau.',
'2020-p217':'Le texte décrit une annulation partielle des crédits de titre 2 mis en réserve par la LFR de novembre. Cette opération ne figure pas dans les mouvements du tableau.',
'2020-p345':'Le commentaire décrit un dégel intégral en loi de finances rectificative, malgré le zéro de la ligne Dégels du tableau.',
'2021-p113':'Le texte décrit un surgel en novembre puis des annulations en décembre, absents du tableau. Les zéros de ses lignes ne couvrent pas tous les mouvements de l’année.',
'2021-p159':'Le commentaire décrit une annulation intégrale par les LFR de juillet et décembre. L’absence de ligne Annulations dans le tableau ne signifie pas zéro annulation.',
'2021-p181':'Le commentaire distingue l’annulation de la réserve et d’autres économies sur le bail de l’ASN, puis un gel complémentaire. Le tableau ne constitue pas un historique exhaustif.',
'2021-p203':'Le texte décrit des dégels, annulations et reports supplémentaires, notamment pour les trains d’équilibre du territoire. Le solde du tableau n’est pas un stock au 31 décembre.',
'2021-p205':'Le texte décrit deux opérations de dégel, dont une en fin d’année pour Brittany Ferries, malgré le zéro de la ligne Dégels du tableau.',
'2022-p113':'Le texte décrit un dégel intégral en fin d’exercice. Il n’est pas inscrit dans la ligne Dégels du tableau.',
'2022-p159':'Le commentaire décrit une levée intégrale pour compléter la subvention à Météo-France, malgré le zéro de la ligne Dégels du tableau.',
'2022-p181':'Le texte distingue l’annulation d’une partie de la réserve et un dégel de 12 M€ pour l’ADEME en fin de gestion. Ces opérations ne remplacent pas les lignes du tableau.',
'2022-p205':'Le texte décrit un dégel de 7,8 M€ et l’annulation du solde en fin de gestion. Le zéro de la ligne Dégels ne couvre pas toute l’année.',
'2022-p217':'La page suivante décrit l’annulation du solde en CP et le dégel du solde en AE en fin de gestion. Les montants du tableau précèdent ces opérations.',
}
NEXT_PAGE={'2017-p203','2017-p217','2018-p203','2018-p217','2021-p203','2022-p217'}

def main():
 path=ROOT/'budget_service/data/reserves-ecologie.json'
 old=json.loads(path.read_text(encoding='utf-8'))
 assert old['version']==BASELINE,'Unexpected registry version; review current work before merging.'
 tables=json.loads((OUT/'candidate-tables.json').read_text(encoding='utf-8'))
 coverage=json.loads((OUT/'coverage.json').read_text(encoding='utf-8'))
 assert len(tables)==48 and len(old['records'])==68
 assert all((OUT/t['image']).exists() for t in tables)
 anomalies=[(t['key'],c['measure'],c['field'],c['difference_cents']) for t in tables for c in t['checks'] if not c['passed']]
 assert anomalies==[('2019-p217','CP','initial',-100),('2019-p217','CP','remaining',-100)],anomalies
 # Keep an immutable, directly usable copy of every pre-existing observation.
 backup=OUT/'before-extension.zip'
 if not backup.exists():
  with zipfile.ZipFile(backup,'w',zipfile.ZIP_DEFLATED) as z:
   for name in ['budget_service/data/reserves-ecologie.json','budget_service/reserves.py','public/explorer.html','public/assets/explorer.js','public/assets/explorer.css']:
    z.write(ROOT/name,name)
 result=deepcopy(old);added=0
 for table in tables:
  for candidate in table['records']:
   existing=next((r for r in old['records'] if (r['year'],r['program'],r['measure'])==(candidate['year'],candidate['program'],candidate['measure'])),None)
   if existing:
    assert candidate['program']=='174'
    assert all(existing[k]==candidate[k] for k in ['cells','page','source','source_sha256','raw_lines'])
    continue
   row=deepcopy(candidate);row.pop('programme_page',None)
   row['remaining_label']='Réserve disponible avant mise en place du schéma de fin de gestion'
   row['note']=NOTES.get(table['key'],'Les montants sont ceux du tableau publié ; le solde ne constitue pas un stock certifié au 31 décembre.')
   if any(c['title2_cents'] is None for c in row['cells'].values()):
    row['note']+=' Les colonnes de titre 2 laissées vides dans le RAP restent non renseignées.'
   row['context_pages']=[row['page'],row['page']+1] if table['key'] in NEXT_PAGE else [row['page']]
   row['checks']=[c for c in table['checks'] if c['measure']==row['measure']]
   row['numeric_validation']='published_with_column_difference' if any(not c['passed'] for c in row['checks']) else 'published_columns_and_balance_reconciled'
   result['records'].append(row);added+=1
  if table['program']!='174':
   result['checks'].extend(dict(year=table['year'],program=table['program'],**c) for c in table['checks'])
 for entry in coverage:
  source=next(t['source'] for t in tables if t['year']==entry['year'])
  for code in entry['without_table']:
   assert code=='355'
   p=next(p for p in entry['programmes'] if p['program']==code)
   for measure in ('AE','CP'):
    result['missing_tables'].append(dict(year=entry['year'],budget='BG',mission='TA',program=code,program_label=p['program_label'],measure=measure,page=p['programme_page'],source=source['id'],source_sha256=source['sha256'],cells={},note='Aucun tableau de réserve trouvé dans la section de ce programme. Aucune valeur n’est déduite de cette absence.',remaining_label='Réserve disponible avant mise en place du schéma de fin de gestion',table_unavailable=True,numeric_validation='table_unavailable'))
  result['coverage_by_year'].append(dict(year=entry['year'],integrated_programmes=sorted({t['program'] for t in tables if t['year']==entry['year']}),programmes_without_table=entry['without_table']))
 result['records'].sort(key=lambda r:(r['year'],int(r['program']),r['measure']))
 result['missing_tables'].sort(key=lambda r:(r['year'],int(r['program']),r['measure']))
 result['coverage_by_year'].sort(key=lambda r:r['year'])
 result['coverage']='Réserves Écologie : 8 programmes par an de 2017 à 2022, 9 en 2023 et 2024, 10 en 2025. Aucun total de mission n’est calculé ; la part MaPrimeRénov’ n’est pas isolée.'
 result['notes'].extend(['En 2017–2018, certaines colonnes de titre 2 sont vides : elles restent non renseignées. Un zéro publié dans un tableau avant fin de gestion ne prouve pas l’absence de mouvement dans l’année.', 'Programme 217 en 2019 : écart de 1 € entre les colonnes de titre 2 et de total en CP, sur la réserve initiale et le solde. Programme 217 en 2018 : unité divergente dans le texte du dégel. Les montants des tableaux sont conservés.'])
 result['updated_at']='2026-09-10'
 result.pop('version',None)
 result['version']=hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
 assert added==84 and len(result['records'])==152 and len(result['missing_tables'])==8
 assert len({(r['year'],r['program'],r['measure']) for r in result['records']})==152
 assert all(r in result['records'] for r in old['records'])
 assert all(r in result['missing_tables'] for r in old['missing_tables'])
 assert result['sources']==old['sources'] and result['field_labels']==old['field_labels']
 review=dict(reviewed_tables=[t['key'] for t in tables],column_layout='AE: T2, HT2, total; CP: T2, HT2, total',source_values_preserved=True,notes=NOTES,context_next_page=sorted(NEXT_PAGE))
 (OUT/'reviewed-tables.json').write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf-8')
 path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 report=dict(records=152,added_records=84,missing_table_rows=8,reviewed_tables=48,prior_records_unchanged=68,arithmetic_discrepancies=anomalies,baseline_version=BASELINE,version=result['version'],sql_unchanged=True,vector_corpus_unchanged=True)
 (OUT/'integration.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()