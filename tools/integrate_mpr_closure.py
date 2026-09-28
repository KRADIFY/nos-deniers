"""Reviewed MPR additions. No canonical budget fact or vector index is changed."""
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports/mpr-closure-20260920'
REGISTRY = ROOT / 'budget_service/data/maprimerenov.json'


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def main():
    before = OUT / 'before/maprimerenov.json'
    if not before.exists():
        before.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REGISTRY, before)
    original = json.loads(before.read_text(encoding='utf-8'))
    r = json.loads(REGISTRY.read_text(encoding='utf-8'))
    # Each addition was read on the physical PDF page, including AE/CP headings.
    additions = [
        (2020, 'PLF', 390, 390, '46eea38db98f94b6af13', 27),
        (2021, 'PLF', 740, 740, '9f56a4e8a7062f15663e', 367),
        (2022, 'PLF', 1700, 1390, 'adaf79e019ba52fac704', 379),
        (2023, 'PLF', 2450, 2300, '7ca128d2349a72abdec6', 374),
        (2024, 'PLF', 2697, 2065, 'ad1d42da63958bf4a275', 400),
        (2021, 'LFI', 740, 740, '2f15709320cdd6cb8d0a', 54),
        (2022, 'LFI', 1700, 1390, 'a954f39135465e66a745', 42),
        (2023, 'LFI', 2450, 2300, '8a04f40171b880b41ba2', 39),
        (2022, 'OUVERT', None, 1419, 'a954f39135465e66a745', 42),
    ]
    pap = {year: (sid, page) for year, stage, _, _, sid, page in additions if stage == 'PLF'}
    new = []
    for year, stage, ae, cp, sid, page in additions:
        for measure, amount in [('AE', ae), ('CP', cp)]:
            if amount is None:
                continue
            row = dict(year=year, stage=stage, measure=measure, budget='BG', mission='TA',
                       mission_label='Écologie, développement et mobilité durables',
                       program='174', program_label='Énergie, climat et après-mines',
                       action='02', action_label='Accompagnement transition énergétique',
                       subaction='', subaction_label='', category='', title='',
                       cents=amount*100000000, source=sid, page=page, line=page,
                       field=f'Part MaPrimeRénov’ du P174 · {stage} {year} · {measure}',
                       published_value=str(amount), published_unit='M€', precision='1 M€',
                       approximate=1, basis='Part explicitement identifiée dans le P174, sans extrapolation aux P135 et P362.')
            if year == 2020:
                row.update(published_value='390000000', published_unit='€', precision='1 €', approximate=0,
                           references=[dict(source=sid, page=26)])
            elif stage != 'PLF':
                row['references'] = [dict(source=pap[year][0], page=pap[year][1])]
            if stage == 'LFI' and year == 2023:
                row['basis'] += ' Note 29 : réserve de précaution de 5 % incluse dans la LFI.'
            key = lambda x: tuple(x[k] for k in ('year','stage','measure','mission','program','action'))
            existing = [x for x in r['facts'] if key(x) == key(row)]
            if existing:
                assert existing == [row], 'Ne pas écraser une observation préexistante différente'
            else:
                r['facts'].append(row)
            coverage = dict(year=year, stage=stage, measure=measure, paths=['TA/174/02'], basis=row['basis'])
            if coverage not in r['coverage']:
                r['coverage'].append(coverage)
            new.append(row)
    source_files = []
    for sid, name, years in [
        ('2f15709320cdd6cb8d0a', 'neb2021-ecologie.pdf', ['2021']),
        ('a954f39135465e66a745', 'neb2022-ecologie.pdf', ['2022']),
        ('8a04f40171b880b41ba2', 'neb2023-ecologie.pdf', ['2023']),
        ('270aaa96aa51346f908e', 'neb2025-cohesion.pdf', ['2025','2026']),
    ]:
        d = json.loads((OUT/'local-pages'/f'{sid}.json').read_text(encoding='utf-8'))['document']
        content = Path(d['physical_path']).read_bytes()
        assert content.startswith(b'%PDF-') and hashlib.sha256(content).hexdigest() == d['source_sha256']
        target = ROOT/'reports/dossiers/maprimerenov/sources'/name
        if target.exists():
            assert target.read_bytes() == content
        else:
            target.write_bytes(content)
        s = dict(id=sid, title=d['title'], dataset_title='Dossier MaPrimeRénov’ · documents de contrôle du périmètre',
                 path='topics/maprimerenov/'+name, format='pdf', years_title=years, url=d['url'],
                 sha256=d['source_sha256'], bytes=len(content), pages=d['pages_total'],
                 checked_at='2026-09-20', imported=True, license='Publication officielle de la Cour des comptes')
        if not any(x['id'] == sid for x in r['sources']):
            r['sources'].append(s)
        source_files.append(s)
    notes = {
        2020: 'P174 action 02 : PLF et LFI 390 M€ AE/CP ; consommé 575 M€ AE et 455 M€ CP. Le PAP distingue aussi 60 M€ du P135 pour d’autres aides à la rénovation ; le total national MaPrimeRénov’ reste à délimiter.',
        2021: 'Consommé disponible dans le périmètre publié. P174 action 02 : PLF et LFI 740 M€ AE/CP. Les dotations du P362 doivent être ventilées pour compléter ces deux étapes au niveau national.',
        2022: 'Consommé disponible dans le périmètre publié. P174 action 02 : PLF et LFI 1 700 M€ AE / 1 390 M€ CP ; ouverts 1 419 M€ CP. Ces compléments ne couvrent pas la totalité des autres programmes.',
        2023: 'Consommé disponible dans le périmètre publié, élargi au P135. P174 action 02 : PLF et LFI 2 450 M€ AE / 2 300 M€ CP, réserve initiale incluse. Le total national proposé et voté reste à ventiler.',
        2024: 'LFI, ouverts et consommé disponibles dans le périmètre publié. PLF P174 action 02 : 2 697 M€ AE / 2 065 M€ CP. La subvention du P135 couvre un ensemble d’aides : PLF national MaPrimeRénov’ non établi.',
        2025: 'PLF CP : 1 378 M€ dans le périmètre de la prime de transition énergétique du jaune 2025. LFI : une brique de 779,9 M€ CP est identifiée, mais l’autre part de financement Anah n’est pas ventilée. Cette brique ne remplace pas le total national.',
        2026: 'P135 : brique MaPrimeRénov’ identifiée de 604,6 M€ CP en LFI ; complément Anah non ventilé. Le jaune présente une estimation des aides à la rénovation, pas un total certifié du dispositif. Exécution annuelle non achevée au 20 septembre 2026.',
    }
    for t in r['timeline']:
        if t['year'] in notes:
            t['note'] = notes[t['year']]
            for row in new:
                if row['year'] != t['year']:
                    continue
                if row['stage'] not in t['stages']:
                    t['stages'].append(row['stage'])
                ref = dict(source=row['source'], page=row['page'])
                if ref not in t['references']:
                    t['references'].append(ref)
            if t['year'] in (2025, 2026):
                ref = dict(source='270aaa96aa51346f908e', page=55)
                if ref not in t['references']:
                    t['references'].append(ref)
    r['updated_at'] = '2026-09-20'
    r['limitations'][2] = ('Restent à isoler : total national complet de 2020, étapes nationales encore absentes de 2021–2024, LFI/ouverts/consommé complets 2025 et montants complets 2026. Les parts connues et les enveloppes mixtes figurent dans les justificatifs. Les gels et mouvements des programmes ne sont pas automatiquement ceux du dispositif ; aucun gel n’est déduit du non-consommé.')
    r['limitations'][4] = ('Le rattachement à l’action 02 du P174 est documenté pour les PLF 2020–2024, les LFI 2020–2023, les ouverts CP 2022 et les consommés 2020, 2023 et 2024. Il ne permet pas d’estimer les autres ventilations, notamment les réserves.')
    r['availability_note'] = ('Disponible dans le périmètre publié : consommé 2021–2024 ; LFI et ouverts 2024 ; PLF CP 2025. '
        'Compléments limités au P174 : PLF 2020–2024, LFI 2020–2023 et ouverts CP 2022. '
        'Cliquez sur un montant ou une case indisponible pour vérifier sa portée, les sources et les démarches possibles.')
    assert all(row in r['facts'] for row in original['facts']), 'Les observations antérieures doivent être conservées à l’identique'
    dump(REGISTRY, r)
    dump(OUT/'integration.json', dict(date='2026-09-20', original_facts=len(original['facts']),
         added_facts=len(new), final_facts=len(r['facts']), preserved_original_facts=True,
         canonical_sql_unchanged=True, vector_index_unchanged=True, additions=new, sources=source_files))
    print(f"{len(new)} observations intégrées ; {len(original['facts'])} observations antérieures préservées ; {len(source_files)} PDF vérifiés.")


if __name__ == '__main__':
    main()
