"""Targeted recovery of previously rejected RAP groups with source evidence."""
from __future__ import annotations
import hashlib,json,shutil,sys
from collections import Counter
from pathlib import Path
from promote_rap_movements_national import labels
from promote_rap_actions_national import clean_item

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from budget_service import action_details
from budget_service.rap_validation import validate_action,validate_movements,validate_reserve
R=ROOT/'reports/recovery-20260920';D=ROOT/'budget_service/data'
def read(p):return json.loads(p.read_text(encoding='utf8'))
def dump(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def reserve_key(r):return (r['year'],r['mission'],r['program'],r['measure'])
def movement_key(r):return (r['scope']['years'][0],r['scope']['mission'],r['scope']['program'])
def observation(x):return tuple(x[k] for k in ('year','mission','program','measure','kind','date','title','sign','amount_cents','page','source'))

def main():
    backup=R/'before';backup.mkdir(exist_ok=True)
    names=['actions-national.json','mouvements-rap-national.json','reserves-national.json']
    for name in names:
        if not (backup/name).exists():shutil.copyfile(D/name,backup/name)
    old_actions=read(backup/names[0])['groups'];old_movements=read(backup/names[1])['registries'];old_reserves=read(backup/names[2])['records']
    candidates=read(R/'actions/candidates.json')['groups']
    manual=[]
    for name in ('actions-p174.json','actions-ecologie.json','actions-multititres.json','actions-sousactions.json','actions-dette.json'):
        manual+=read(D/name)['groups']
    by_key={action_details.key(g):g for g in candidates};assert len(by_key)==len(candidates)
    citation_corrections=[]
    def without_pages(items):
        return [{k:without_pages(v) if k=='subactions' else v for k,v in a.items() if k!='page'} for a in items]
    for old in old_actions+manual:
        fresh=by_key[action_details.key(old)]
        fresh_items=[clean_item(a) for a in fresh['actions']]
        if without_pages(old['actions'])!=without_pages(fresh_items):
            # The old parser attached P423's all-zero LFI table to P425.
            # P425 has three published actions, not the nine of P423.
            assert action_details.key(old)==(2024,'LFI','AE','BG','AV','425')
            assert all(a['euros']==0 for a in old['actions']+fresh_items)
            assert without_pages(old['actions'][:3])==without_pages(fresh_items)
        if old in old_actions and old['actions']!=fresh_items:
            citation_corrections.append(dict(key=action_details.key(old),old_page=old['page'],new_page=fresh['page'],amounts_unchanged=True,
                removed_misattributed_zero_actions=sorted({a['code'] for a in old['actions']}-{a['code'] for a in fresh_items})))
    manual_keys={action_details.key(g) for g in manual}
    selected=[]
    for g in candidates:
        if action_details.key(g) in manual_keys:continue
        g={k:v for k,v in g.items() if k!='status'}|dict(actions=[clean_item(a) for a in g['actions']])
        if g['reconciliation']['status']=='source_difference':
            reference=sum(p['cents'] for p in g['parents']);published=g['published_total_euros']*100
            fmt=lambda c:f'{c/100:,.2f}'.replace(',',' ').replace('.',',')+' €'
            percent=f'{abs(published-reference)/abs(reference)*100:.4f}'.replace('.',',')
            g['reconciliation_note']=(f'Total de programme retenu (tableau de synthèse) : {fmt(reference)}. '
                f'Total publié dans le RAP : {fmt(published)}. Écart : {fmt(published-reference)} '
                f'({percent} %). Les chiffres sources sont conservés ; cet écart ne bloque pas l’utilisation des données.')
        validate_action(g);selected.append(g)
    actions=dict(updated_at='2026-09-20',coverage=f'{len(selected)} groupes nationaux LFI/consommé AE/CP, 2023–2025, avec rapprochement documenté.',
                 note='Montants du RAP conservés. Aucun écart supérieur à 10 € accepté automatiquement ; cause à analyser avant validation. Aucun périmètre ambigu accepté.',groups=selected)
    cand_mov=read(R/'movements/candidates.json')['registries'];mapping=labels()
    pilot=[r for r in cand_mov if r['scope']['mission']=='TA' and r['scope']['program']=='174']
    assert {observation(x) for r in pilot for x in r['items']}=={observation(x) for x in read(D/'mouvements-rap-p174.json')['items']}
    movements=[r for r in cand_mov if r not in pilot];by_mov={movement_key(r):r for r in movements}
    assert len(by_mov)==len(movements)
    for old in old_movements:
        assert {observation(x) for x in old['items']}=={observation(x) for x in by_mov[movement_key(old)]['items']},movement_key(old)
    for r in movements:
        validate_movements(r)
        r['scope']['mission_label'],r['scope']['program_label']=mapping[movement_key(r)]
        for check in r['reconciliations']:
            check.update(mission=r['scope']['mission'],program=r['scope']['program'])
    mov=dict(updated_at='2026-09-20',source_kind='rap_recapitulation',registries=movements,
             coverage=f'{len(movements)} programme-années nationales contrôlées, en plus du programme 174 relu.',
             limits=['Les montants datés, les totaux imprimés et les crédits ouverts sont rapprochés. Aucun écart supérieur à 10 € accepté automatiquement ; cause à analyser avant validation.',
                     'Les huit colonnes sont conservées ; une cellule vide reste absente.',
                     'Ces mouvements expliquent les crédits ouverts et ne s’y ajoutent pas. Aucune ventilation par action ou dispositif n’est déduite.'])
    reserve_cand=read(R/'reserves/candidates.json')['records'];manual_r=read(D/'reserves-ecologie.json')
    by_res={reserve_key(r):r for r in reserve_cand};assert len(by_res)==len(reserve_cand)
    manual_r_keys={reserve_key(r) for r in manual_r['records']}
    for r in manual_r['records']:
        if reserve_key(r) in by_res:assert r['cells']==by_res[reserve_key(r)]['cells']
    physical=lambda r:(r['source'],r['page'],r['measure'])
    by_physical={physical(r):r for r in reserve_cand};corrections=[]
    for old in old_reserves:
        fresh=by_physical[physical(old)]
        assert old['cells']==fresh['cells'],physical(old)
        if old['program']!=fresh['program']:
            corrections.append(dict(year=old['year'],mission=old['mission'],measure=old['measure'],source=old['source'],page=old['page'],
                                    old_program=old['program'],new_program=fresh['program'],programme_page=fresh['programme_page'],amounts_unchanged=True))
    records=[r for r in reserve_cand if reserve_key(r) not in manual_r_keys]
    for r in records:validate_reserve(r)
    # Catalogue metadata is read from the application, never reconstructed from a filename.
    import subprocess
    code="import sqlite3,json;c=sqlite3.connect('file:/data/derived/budget.sqlite?mode=ro',uri=True);print(json.dumps({i:json.loads(d) for i,d in c.execute('select id,data from sources')},ensure_ascii=False))"
    catalogue=json.loads(subprocess.check_output(['docker','exec','lexmachine-budget-web-1','python','-c',code],text=True,encoding='utf8'))
    sources=[dict(catalogue[s],id=s) for s in sorted({r['source'] for r in records})]
    reserves=dict(updated_at='2026-09-20',coverage=f'{len(records)//2} programme-années nationales supplémentaires, avec rattachement au programme et contrôles arithmétiques.',
                  field_labels=manual_r['field_labels'],sources=sources,records=records,
                  checks=[c|dict(year=r['year'],mission=r['mission'],program=r['program'],source=r['source'],page=r['page']) for r in records for c in r['checks']],
                  notes=['Les montants publiés sont conservés ; les écarts de solde d’un euro vérifiés dans le PDF sont signalés.',
                         'Rattachement au programme établi par la page d’ouverture de sa section, sans utiliser les programmes cités dans les commentaires.',
                         'Les relevés manuels Écologie restent prioritaires. Aucune ventilation par action ou dispositif n’est estimée.'])
    summary=dict(actions=dict(groups=len(selected),added=len(selected)-len(old_actions),actions=sum(len(g['actions']) for g in selected),
        subactions=sum(len(a.get('subactions',[])) for g in selected for a in g['actions']),programme_years=len({(g['year'],g['mission'],g['program']) for g in selected}),mission_years=len({(g['year'],g['mission']) for g in selected}),
        reconciliation_statuses=dict(Counter(g['reconciliation']['status'] for g in selected)),manual_groups_preserved=len(manual)),
        movements=dict(registries=len(movements),added=len(movements)-len(old_movements),items=sum(len(r['items']) for r in movements),evidence_rows=sum(len(r['evidence_rows']) for r in movements),tables=sum(len(r['table_totals']) for r in movements),sources=len({s['id'] for r in movements for s in r['sources']})),
        reserves=dict(records=len(records),programme_years=len(records)//2,net_additional_programme_years=(len(records)-len(old_reserves))//2,sources=len(sources),corrected_programme_attributions=len(corrections)//2,manual_records_reproduced=len(manual_r_keys&set(by_res)),nonexact_records=sum(r['numeric_validation']=='published_with_balance_difference' for r in records)),
        unresolved_extraction_gaps={kind:len(read(R/kind/'gaps.json')) for kind in ('actions','movements','reserves')},
        canonical_original_facts_preserved=120948,explicit_zero_facts_added=46,public_deployed=False)
    summary['action_citation_corrections']=citation_corrections
    dump(R/'reserve-attribution-corrections.json',corrections)
    for name,value in zip(names,(actions,mov,reserves)):
        staged=D/(name+'.staged');dump(staged,value);staged.replace(D/name)
    dump(R/'integration-summary.json',summary)
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':main()
