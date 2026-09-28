"""One-time, guarded refinement of four already documented MPR observations."""
import copy
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'budget_service/data/maprimerenov.json'
BEFORE = '2e42f3ef9281afd62f62b333853ac3951442d238e8d606c4cb3d7808f5b49ec3'


def main():
    raw = TARGET.read_bytes()
    if hashlib.sha256(raw).hexdigest() != BEFORE:
        raise SystemExit('Le registre a changé ou ce complément a déjà été appliqué.')
    data = json.loads(raw)
    report = ROOT / 'reports/mpr-precision-20260910'
    report.mkdir(exist_ok=True)
    (report / 'maprimerenov-before.json').write_bytes(raw)
    references = json.loads((ROOT / 'reports/actions-p174-20260910/reference.json').read_text(encoding='utf-8'))
    checks = []
    for year, source, page in [(2023, 'c793d7737895c135ad70', 439), (2024, '113330a8d3bb90c96604', 446)]:
        text = (ROOT / f'reports/reserves-et-consignes-20260909/rap-ecologie-{year}.txt').read_text(encoding='utf-8').split('\f')[page - 1]
        match = re.search(r'Prime transition énergétique \(MaPrimeRénov[’\']\) \(([\d ]+) € en AE et ([\d ]+) € en CP\)', text)
        assert match, (year, page)
        (report / f'rap-{year}-page-{page}.txt').write_text(text, encoding='utf-8')
        for measure, amount in zip(('AE', 'CP'), match.groups()):
            euros = int(amount.replace(' ', ''))
            row = next(r for r in data['facts'] if (r['year'], r['stage'], r['measure'], r['program']) == (year, 'EXEC', measure, '174'))
            old = copy.deepcopy(row)
            assert abs(euros * 100 - old['cents']) <= 5000000  # half of the former 0.1 M€ unit
            data.setdefault('observation_history', []).append(dict(observation=old, replaced_at='2026-09-10',
                reason='Montant du dispositif publié à l’euro dans le RAP du même exercice, compatible avec l’arrondi antérieur.',
                replacement_source=source, replacement_page=page))
            row.update(cents=euros * 100, source=source, line=page, page=page,
                       field=f'Prime transition énergétique (MaPrimeRénov’) · consommé {year} · {measure} · rubrique de l’action 02',
                       published_value=str(euros), published_unit='€', precision='1 € (RAP)', approximate=1,
                       basis='Crédits de l’État consacrés à MaPrimeRénov’ dans le P174 ; montants versés aux bénéficiaires par l’Anah non additionnés.',
                       previous_source=old['source'], previous_page=old['page'])
            checks.append(dict(year=year,measure=measure,old_cents=old['cents'],new_cents=row['cents'],source=source,page=page))
        ref=dict(source=source,page=page,label=f'RAP Écologie {year} · montant propre à MaPrimeRénov’',url=references['sources'][source]['url'])
        data['references'].append(ref)
        timeline=next(r for r in data['timeline'] if r['year']==year)
        timeline['references'].append(dict(source=source,page=page))
        if year==2023:
            timeline['note'] += ' Le consommé P174 est précisé à l’euro par le RAP ; les autres programmes conservent leur précision publiée.'
        else:
            timeline['note'] = 'Voté, crédits ouverts nets et consommé identifiés. Consommé P174 publié à l’euro dans le RAP ; autres consommés à 0,1 M€ ; LFI et ouverts au M€.'
    data['updated_at']='2026-09-10'
    data['limitations'][-1]='La précision varie selon les sources : euro pour le consommé P174 2023–2024, 0,1 M€ ou M€ pour les autres observations. Aucun pourcentage arbitraire du programme, de l’action ou du budget de l’Anah n’est utilisé.'
    TARGET.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (report / 'reconciliation.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
    print('4 observations précisées ; 4 anciennes observations conservées dans l’historique ; 28 autres observations inchangées.')


if __name__=='__main__':
    main()
