"""Integrate the independently reviewed 2020–2022 funding evidence once."""
from pathlib import Path
import copy, hashlib, json, shutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'reports/audit-final-20260920'
REG = ROOT/'budget_service/data/maprimerenov.json'

def main():
    original = REG.read_bytes()
    backup = OUT/'before/maprimerenov.json'
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists(): backup.write_bytes(original)
    r = json.loads(original)
    marker = 'an-funding-review-20260921'
    if r.get('last_funding_review') == marker:
        print('Already integrated'); return
    old_facts = copy.deepcopy(r['facts'])
    def source(name, title, years):
        p = OUT/'sources'/(name+'.pdf')
        d = json.loads((OUT/'sources'/(name+'.json')).read_text(encoding='utf8'))
        sha = hashlib.sha256(p.read_bytes()).hexdigest()
        sid = sha[:20]
        s = dict(id=sid, title=title, dataset_title='Dossier MaPrimeRénov’ · crédits de l’État',
                 path='topics/maprimerenov/'+p.name, format='pdf', years_title=list(map(str,years)),
                 url=d.get('url') or d['source']['url'], sha256=sha, bytes=p.stat().st_size,
                 pages=d['pages'], checked_at='2026-09-21', imported=True,
                 license='Publication officielle de l’État français')
        assert not any(x['id']==sid for x in r['sources'])
        r['sources'].append(s)
        shutil.copyfile(p, ROOT/'reports/dossiers/maprimerenov/sources'/p.name)
        return sid
    an = source('an-plf2022-plan-relance', 'Assemblée nationale — PLF 2022, Plan de relance, tableau MaPrimeRénov’', [2020,2021,2022])
    an21 = source('an-plf2021-energie', 'Assemblée nationale — PLF 2021, Énergie, financement MaPrimeRénov’', [2020,2021])
    pap21 = source('pap2021-plan-relance', 'PAP 2021 — Plan de relance, financement des logements privés', [2021])
    def add(year, stage, measure, path, millions, sid, page, basis, action=''):
        mission, program = path.split('/')
        carrier = next(c for c in r['carriers'] if c['path']==path)
        row = dict(year=year, stage=stage, measure=measure, budget='BG', mission=mission,
                   mission_label=carrier['mission_label'], program=program, program_label=carrier['label'],
                   action=action, action_label={'02':'Accompagnement de la transition énergétique','01':'Rénovation énergétique'}.get(action,''),
                   subaction='', subaction_label='', category='', title='', cents=round(millions*100000000),
                   source=sid, page=page, line='MaPrimeRénov’ · '+path, field=stage+' '+measure,
                   published_value=str(millions), published_unit='M€', precision='M€' if millions==int(millions) else '0,1 M€',
                   approximate=millions!=0, basis=basis)
        assert not any((f['year'],f['stage'],f['measure'],f['mission'],f['program']) == (year,stage,measure,mission,program) for f in r['facts'])
        r['facts'].append(row)
        return row
    def cover(year, stage, measure, paths, basis):
        item = next((x for x in r['coverage'] if (x['year'],x['stage'],x['measure'])==(year,stage,measure)),None)
        if item is None:
            item=dict(year=year,stage=stage,measure=measure,paths=[]);r['coverage'].append(item)
        item['paths']=sorted(set(item['paths'])|set(paths));item['basis']=basis
    def evidence(year,path,stages,explanation,refs):
        r['perimeter_evidence'].append(dict(kind='outside_scope',year=year,path=path,stages=stages,
            measures=['AE','CP'],label=f'{year} · financement et périmètre documentés',explanation=explanation,
            references=[dict(source=s,page=p) for s,p in refs],is_published_zero=False))
    # The 85 M€ from P135 finance P174. They are not a second expenditure.
    for measure in ('AE','CP'):
        add(2020,'OUVERT',measure,'TA/174',575,an,31,
            '390 M€ initiaux + 100 M€ LFR + 85 M€ transférés du P135 : 575 M€ sur le programme destinataire. Le transfert n’est pas ajouté une seconde fois.', '02')
        cover(2020,'OUVERT',measure,['TA/174/02'],'AN PLF 2022 pp.31–32 : financement de la prime 2020, au programme destinataire.')
    evidence(2020,'PR/362',['PLF','LFI','OUVERT','EXEC'],
        'Le Plan de relance porte MaPrimeRénov’ à partir de 2021. Le tableau rétrospectif publie zéro sur le P362 en 2020 ; aucun financement supplémentaire n’est ajouté.',[(an,31),(an,32)])
    evidence(2020,'VA/135',['PLF','LFI','OUVERT','EXEC'],
        'Périmètre de la prime 2020, distinct d’Habiter Mieux : 390 M€ initiaux au P174. En gestion, les 85 M€ venus du P135 sont transférés au P174 et compris dans les 575 M€ disponibles. Ils ne constituent pas une seconde dépense à additionner. Les autres aides Anah ne sont pas assimilées à la prime.',
        [(an,31),(an,32),('46eea38db98f94b6af13',27),('df8d92ccd79f7b889547',415)])
    published_scope='Périmètre publié de MaPrimeRénov’ dans le Plan de relance : copropriétés, accompagnements connexes et communication inclus selon le PAP ; pas une mesure de la seule prime par geste.'
    for measure,amount in [('AE',2000),('CP',915)]:
        add(2021,'PLF',measure,'PR/362',amount,pap21,30,published_scope,'01')
        add(2021,'LFI',measure,'PR/362',amount,an,32,published_scope)
        add(2021,'LFI',measure,'VA/135',0,an,32,'Zéro explicitement imprimé dans la colonne LFI 2021 du tableau récapitulatif.')
        for stage in ('PLF','LFI'):
            cover(2021,stage,measure,['TA/174','PR/362']+(['VA/135'] if stage=='LFI' else []),published_scope)
    evidence(2021,'VA/135',['PLF'],
        'Le financement proposé pour MaPrimeRénov’ est identifié au P174 et complété au P362. Les autres interventions de l’Anah ne sont pas ajoutées à cette enveloppe publiée.',[(an21,33),(an21,52),(pap21,30)])
    for measure,amount in [('AE',0),('CP',565.5)]:
        add(2022,'PLF',measure,'PR/362',amount,an,32,'Montant de la colonne PLF 2022 ; distinct du collectif 2021 et des futurs reports.')
        add(2022,'PLF',measure,'VA/135',0,an,32,'Zéro explicitement imprimé dans la colonne PLF 2022.')
        cover(2022,'PLF',measure,['TA/174','PR/362','VA/135'],'Tableau AN PLF 2022 p.32 ; chaque colonne budgétaire reste séparée.')
    assert r['facts'][:len(old_facts)] == old_facts
    r['updated_at']='2026-09-21';r['last_funding_review']=marker
    r['availability_note']='Disponible dans le périmètre publié : PLF/LFI/ouverts/consommé 2020 ; PLF/LFI/consommé 2021 ; PLF/consommé 2022 ; consommé 2023 ; LFI/ouverts/consommé 2024 ; PLF CP 2025. Les autres étapes comportent des parts documentées. Cliquez sur chaque montant ou case indisponible pour vérifier sa définition et ses sources.'
    r['limitations'][2]='Restent à isoler : ouverts nationaux 2021, LFI/ouverts nationaux 2022–2023, PLF national 2024, LFI/ouverts/consommé complets 2025 et montants complets 2026. Les parts connues et enveloppes mixtes figurent dans les justificatifs. Les gels et mouvements des programmes ne sont pas ceux du dispositif ; aucun gel n’est déduit du non-consommé.'
    r['limitations'].append('2020 : les 85 M€ transférés du P135 sont comptés une seule fois au P174. En 2021, le périmètre publié du Plan de relance comprend des aides connexes et la communication : les comparaisons historiques ne sont pas à périmètre constant.')
    notes={2020:'Prime 2020 au programme destinataire P174 : PLF/LFI 390 M€ AE/CP ; ouverts 575 M€ AE/CP ; consommé 575 M€ AE et 455 M€ CP. Les 85 M€ transférés depuis le P135 sont déjà compris, sans double compte.',
           2021:'PLF et LFI : 2 740 M€ AE, 1 655 M€ CP, dont P174 740 M€ et P362 2 000 M€ AE / 915 M€ CP. Le périmètre de relance comprend des aides connexes. Consommé disponible ; ouverts annuels complets non établis.',
           2022:'PLF : 1 700 M€ AE et 1 955,5 M€ CP. Consommé disponible. LFI et ouverts : part P174 identifiée ; les autres parts demandent un rapprochement de périmètre. La colonne PLF n’est pas recopiée dans la LFI.'}
    for t in r['timeline']:
        if t['year'] in notes:
            t['note']=notes[t['year']]
            if t['year']==2020 and 'OUVERT' not in t['stages']:t['stages'].append('OUVERT')
            t['references'] += [dict(source=an,page=31),dict(source=an,page=32)]
    REG.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    receipt=dict(before_facts=len(old_facts),after_facts=len(r['facts']),old_facts_preserved=True,
                 sources_added=[an,an21,pap21],new_facts=r['facts'][len(old_facts):],review=marker)
    (OUT/'mpr-historical-integration.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8')
    print({k:v for k,v in receipt.items() if k!='new_facts'})

if __name__=='__main__':main()
