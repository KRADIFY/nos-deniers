"""Build reviewed RAP action totals across canonical personnel/other titles.

This offline builder reads the original facts, preserves every parent row, and
selects one published Total per action. It never sums titles plus that Total.
"""
import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'reports/actions-multititres-20260910'
TARGET = ROOT / 'budget_service/data/actions-multititres.json'
SOURCE = {2023: 'c793d7737895c135ad70', 2024: '113330a8d3bb90c96604', 2025: '06557292eccf98885e32'}
PAGES = {'181': {2023: 339, 2024: 339, 2025: 325},
         '217': {2023: 518, 2024: 530, 2025: 508}, '235': {2025: 607}}
LABELS = {
    '181': {
        '01': 'Prévention des risques technologiques et des pollutions',
        '09': 'Contrôle de la sûreté nucléaire et de la radioprotection',
        '10': 'Prévention des risques naturels et hydrauliques',
        '11': "Gestion de l'après-mine et travaux de mise en sécurité, indemnisations et expropriations sur les sites",
        '12': "Agence de l'environnement et de la maîtrise de l'énergie (ADEME)",
        '13': "Institut national de l'environnement industriel et des risques (INERIS)",
        '14': 'Fonds de prévention des risques naturels majeurs',
        '15': 'Retrait Gonflement des Argiles',
    },
    '217': {
        '07': 'Pilotage, support, audit et évaluations',
        '08': 'Personnels œuvrant pour les politiques de transport',
        '09': 'Personnels oeuvrant pour les politiques du programme "Sécurité et éducation routières"',
        '11': 'Personnels oeuvrant pour les politiques du programme "Affaires maritimes"',
        '13': "Personnels œuvrant pour la politique de l'eau et de la biodiversité",
        '15': "Personnels œuvrant pour les politiques du programme Urbanisme, territoires et aménagement de l'habitat",
        '16': 'Personnels œuvrant pour la politique de la prévention des risques',
        '18': "Personnels relevant de programmes d'autres ministères",
        '22': 'Personnels transférés aux collectivités territoriales',
        '23': "Personnels œuvrant pour les politiques de l'énergie et du climat",
        '25': 'Commission nationale du débat public',
        '26': 'Autorité de contrôle des nuisances aéroportuaires (ACNUSA)',
        '27': "Commission de régulation de l'énergie (CRE)",
        '28': 'Personnels œuvrant dans le domaine de la stratégie et de la connaissance des politiques de transition écologique',
    },
    '235': {
        '01': 'Personnels œuvrant pour la politique en matière de sûreté nucléaire et radio-protection',
        '02': 'Sûreté nucléaire et radio-protection',
    },
}
POPPLER = Path('C:/Users/Jean-Christophe/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin')


def numbers(line):
    return [int(s.replace(' ', '')) for s in re.split(r'\s{2,}', line.strip())
            if re.fullmatch(r'-?\d[\d ]*', s)]


def read_parents():
    query = """import json,sqlite3
c=sqlite3.connect('file:/data/derived/budget.sqlite?mode=ro',uri=True)
c.row_factory=sqlite3.Row
rows=c.execute("select * from facts where budget='BG' and mission='TA' and program in ('181','217','235') and year between 2023 and 2025 and stage in ('LFI','EXEC') order by program,year,measure,stage,title").fetchall()
print(json.dumps([dict(r) for r in rows],ensure_ascii=False))
"""
    output = subprocess.check_output(['docker', 'exec', 'lexmachine-budget-web-1', 'python', '-c', query],
                                     text=True, encoding='utf-8')
    rows = json.loads(output)
    assert len(rows) == 52, ('Unexpected canonical row count', len(rows))
    assert not any(r['program'] == '235' and r['year'] != 2025 for r in rows)
    return rows


def measure_lines(pages, first, year, measure):
    heading = rf'^{year} / ' + ('AUTORISATIONS D.ENGAGEMENT' if measure == 'AE' else 'CR[ÉE]DITS DE PAIEMENT') + r'\s*$'
    selected = []
    started = False
    for page in range(first, min(first + 3, len(pages) + 1)):
        for line in pages[page - 1].splitlines():
            if not started:
                if re.match(heading, line.strip()):
                    started = True
                continue
            if re.match(r'^\d{4} / (?:AUTORISATIONS|CR[ÉE]DITS|PR[ÉE]SENTATION)', line.strip()):
                raise AssertionError(('Missing consumption total before another table', year, measure, page))
            selected.append((page, line))
            if line.strip().startswith('Total des ' + measure) and 'consomm' in line:
                return selected
    raise AssertionError(('Incomplete table', year, measure, first))


def printed_label(lines, index):
    """Read wrapped labels without treating the numeric second row as a label."""
    chunks = []
    for offset, (_, line) in enumerate(lines[index:]):
        if not line.strip() or (offset and re.match(r'^\s*(?:\d{2} – |Total des )', line)):
            break
        first = re.split(r'\s{2,}', line.strip())[0]
        if offset == 0:
            first = re.sub(r'^\d{2} – ', '', first)
        if not re.fullmatch(r'-?\d[\d ]*', first):
            chunks.append(first)
    return ' '.join(chunks).replace('radio- protection', 'radio-protection')


def expected_codes(program, year):
    codes = list(LABELS[program])
    if program == '181':
        codes.remove('09' if year == 2025 else '15')
    return codes


def extract_actions(lines, program, year, measure):
    lfi, executed = [], []
    for index, (page, line) in enumerate(lines):
        match = re.match(r'^\s*(\d{2}) – ', line)
        if not match:
            continue
        code = match[1]
        assert code in LABELS[program], (program, year, measure, code)
        label = printed_label(lines, index)
        assert label == LABELS[program][code], ('Label changed', program, year, code, label)
        actual_page, actual_line = lines[index + 1]
        forecast, actual = numbers(line), numbers(actual_line)
        assert len(forecast) >= 2 and len(actual) >= 1, (program, year, measure, code)
        lfi.append(dict(code=code, label=label, euros=forecast[-2], page=page))
        executed.append(dict(code=code, label=label, euros=actual[-1], page=actual_page))
    assert [a['code'] for a in lfi] == expected_codes(program, year), (program, year, measure)
    return lfi, executed


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    REPORT.mkdir(parents=True, exist_ok=True)
    parents = read_parents()
    refs = json.loads((ROOT / 'reports/actions-p174-20260910/reference.json').read_text(encoding='utf-8'))['sources']
    inventory = json.loads((ROOT / 'reports/reserves-et-consignes-20260909/rap-reserves-pages.json').read_text(encoding='utf-8'))
    groups, gaps, rendered = [], [], []
    for program, years in PAGES.items():
        for year, first in years.items():
            pdf = Path(next(d['path'] for d in inventory if d['year'] == year))
            sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
            assert sha == refs[SOURCE[year]]['sha256'], ('Source PDF changed', year)
            pages = (ROOT / f'reports/reserves-et-consignes-20260909/rap-ecologie-{year}.txt').read_text(encoding='utf-8').split('\f')
            used_pages = set()
            for measure in ('AE', 'CP'):
                lines = measure_lines(pages, first, year, measure)
                used_pages.update(page for page, _ in lines)
                lfi, executed = extract_actions(lines, program, year, measure)
                for stage, actions in [('LFI', lfi), ('EXEC', executed)]:
                    found = [r for r in parents if (r['program'], r['year'], r['measure'], r['stage']) == (program, year, measure, stage)]
                    expected_titles = ['HT2'] if program == '181' and year == 2025 else ['2', 'HT2']
                    assert sorted(r['title'] for r in found) == expected_titles, ('Unexpected titles', program, year, measure, stage)
                    assert all(not r['action'] and not r['subaction'] for r in found)
                    matching_totals = [(page, line) for page, line in lines if line.strip().startswith('Total des ' + measure)
                                       and ('en LFI' in line if stage == 'LFI' else 'consomm' in line)]
                    assert len(matching_totals) == 1
                    total_page, total_line = matching_totals[0]
                    totals = numbers(total_line)
                    published = totals[-2] if stage == 'LFI' else totals[-1]
                    canonical = sum(r['cents'] for r in found)
                    delta = sum(a['euros'] * 100 for a in actions) - canonical
                    total_delta = published * 100 - canonical
                    group = dict(year=year, stage=stage, measure=measure, budget='BG', mission='TA', program=program,
                                 source=SOURCE[year], sha256=sha, page=actions[0]['page'], total_page=total_page,
                                 parents=found, published_total_euros=published, action_sum_minus_parent_cents=delta,
                                 published_total_minus_parent_cents=total_delta, actions=actions)
                    if abs(delta) > min(1000, len(actions) * 50 if stage == 'EXEC' else 0) or abs(total_delta) > (50 if stage == 'EXEC' else 0):
                        gaps.append(dict(group, status='excluded', reason_code='rap_canonical_total_mismatch',
                                         reason='Écart entre les totaux RAP et les parents canoniques supérieur à la précision admise ; groupe exclu du registre.'))
                    else:
                        groups.append(group)
            for page in sorted(used_pages):
                (REPORT / f'rap-{year}-p{page}.txt').write_text(pages[page - 1], encoding='utf-8')
                image = REPORT / f'rap-{year}-p{page}.png'
                subprocess.run([str(POPPLER / 'pdftoppm.exe'), '-f', str(page), '-singlefile', '-r', '125', '-png', str(pdf), str(image.with_suffix(''))],
                               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                rendered.append(dict(year=year, program=program, page=page, path=str(image), sha256=hashlib.sha256(image.read_bytes()).hexdigest()))
    assert len(groups) + len(gaps) == 28
    write_json(REPORT / 'parents.json', parents)
    write_json(REPORT / 'gaps.json', gaps)
    write_json(REPORT / 'rendered-pages.json', rendered)
    write_json(REPORT / 'reconciliation.json', [{k: g[k] for k in ('year', 'program', 'measure', 'stage', 'page', 'total_page',
               'published_total_euros', 'action_sum_minus_parent_cents', 'published_total_minus_parent_cents')} for g in groups])
    write_json(TARGET, dict(updated_at='2026-09-10',
               coverage='P181 et P217 : LFI/consommé, AE/CP, 2023–2025 ; P235 : 2025 seulement. Totaux par action tous titres, sans sous-action.',
               note='Les parents T2 et HT2 sont conservés séparément. Chaque action utilise une seule fois le Total publié dans le RAP, hors FdC/AdP prévus pour la LFI.',
               groups=groups))
    print(json.dumps(dict(groups=len(groups), observations=sum(len(g['actions']) for g in groups), excluded_groups=len(gaps),
                          parents=len(parents), rendered_pages=len(rendered), sha256=hashlib.sha256(TARGET.read_bytes()).hexdigest()), ensure_ascii=False))


if __name__ == '__main__':
    main()
