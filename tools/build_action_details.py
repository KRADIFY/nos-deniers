"""Reproduce the 72 reviewed P174 action observations from the local RAP pages."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'reports/actions-p174-20260910'
SOURCES = {2023: ('c793d7737895c135ad70', 421), 2024: ('113330a8d3bb90c96604', 426), 2025: ('06557292eccf98885e32', 401)}
LABELS = ["Politique de l'énergie", 'Accompagnement transition énergétique',
          "Aides à l'acquisition de véhicules propres", "Gestion économique et sociale de l'après-mines",
          "Lutte contre le changement climatique et pour la qualité de l'air", 'Soutien']


def numbers(line):
    return [int(s.replace(' ', '')) for s in re.split(r'\s{2,}', line.strip()) if re.fullmatch(r'\d[\d ]*', s)]


def main():
    reference = json.loads((REPORT / 'reference.json').read_text(encoding='utf-8'))
    inventory = json.loads((ROOT / 'reports/reserves-et-consignes-20260909/rap-reserves-pages.json').read_text(encoding='utf-8'))
    groups = []
    for year, (source, page) in SOURCES.items():
        entry = reference['sources'][source]
        pdf = Path(next(d['path'] for d in inventory if d['year'] == year))
        assert hashlib.sha256(pdf.read_bytes()).hexdigest() == entry['sha256']
        text = (ROOT / f'reports/reserves-et-consignes-20260909/rap-ecologie-{year}.txt').read_text(encoding='utf-8').split('\f')[page - 1]
        parts = re.split(rf'(?m)^{year} / (?:AUTORISATIONS D.ENGAGEMENT|CR[ÉE]DITS DE PAIEMENT)\s*$', text)
        assert len(parts) == 3
        for measure, part in zip(('AE', 'CP'), parts[1:]):
            lines = part.splitlines()
            lfi, executed = [], []
            for i, line in enumerate(lines):
                match = re.match(r'^\s*(\d{2}) – ', line)
                if not match:
                    continue
                code = match[1]
                assert int(code) == len(lfi) + 1
                forecast, actual = numbers(line), numbers(lines[i + 1])
                assert len(forecast) >= 3 and len(actual) >= 2
                lfi.append(dict(code=code, label=LABELS[int(code) - 1], euros=forecast[-2]))
                executed.append(dict(code=code, label=LABELS[int(code) - 1], euros=actual[-1]))
            assert len(lfi) == len(executed) == 6
            for stage, actions in [('LFI', lfi), ('EXEC', executed)]:
                parent = next(r for r in reference['parents'] if r['year'] == year and r['measure'] == measure and r['stage'] == stage)
                total_line = next(line for line in lines if line.strip().startswith('Total des ' + measure) and
                                  ('en LFI' in line if stage == 'LFI' else 'consomm' in line))
                published_total = numbers(total_line)[-1]
                delta = sum(a['euros'] * 100 for a in actions) - parent['cents']
                # Six independently rounded amounts may differ by at most 3 euros.
                assert abs(delta) <= (300 if stage == 'EXEC' else 0)
                assert abs(published_total * 100 - parent['cents']) <= (50 if stage == 'EXEC' else 0)
                groups.append(dict(year=year, stage=stage, measure=measure, budget='BG', mission='TA', program='174',
                                   source=source, sha256=entry['sha256'], page=page, parent=parent,
                                   published_total_euros=published_total, action_sum_minus_parent_cents=delta, actions=actions))
    result = dict(updated_at='2026-09-10', method='Colonne Total, lignes Prévision LFI et Consommation du même exercice ; aucune ouverture ni FdC ajouté.',
                  coverage='Programme 174, LFI et consommé, AE et CP, 2023–2025 ; six actions, aucune sous-action.', groups=groups)
    out = ROOT / 'budget_service/data/actions-p174.json'
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (REPORT / 'reconciliation.json').write_text(json.dumps([{
        k: g[k] for k in ('year', 'stage', 'measure', 'page', 'source', 'published_total_euros', 'action_sum_minus_parent_cents')
    } for g in groups], ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{len(groups) * 6} observations, {len(groups)} rapprochements, SHA-256 {hashlib.sha256(out.read_bytes()).hexdigest()}')


if __name__ == '__main__':
    main()
