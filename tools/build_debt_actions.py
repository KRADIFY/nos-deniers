"""Build only the four reviewed P355 action observations in Ecology for 2023.

Read the original PDF and a read-only canonical SQLite snapshot. P355 belongs
to mission EB after 2023; those years are outside this reviewed registration.
"""
import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'reports/actions-dette-20260910'
TARGET = ROOT / 'budget_service/data/actions-dette.json'
DEFAULT_DATABASE = ROOT / 'deploy/update-20260910-fdc2023/staging/budget.sqlite'
POPPLER = Path('C:/Users/Jean-Christophe/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin')
SOURCE = 'c793d7737895c135ad70'
SOURCE_SHA = 'cd259bd6ab925e434f1848db6267770b84b715bd78ce2ba1c71d3d41c4e12116'
LABEL = "Charge de la dette de SNCF Réseau reprise par l'État"
EXPECTED = {'LFI': 900000000, 'EXEC': 905411106}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def numbers(line):
    return [int(s.replace(' ', '')) for s in re.split(r'\s{2,}', line.strip())
            if re.fullmatch(r'-?\d[\d ]*', s)]


def read_page(pdf, page):
    extractor = POPPLER / 'pdftotext.exe'
    if not extractor.is_file():
        located = shutil.which('pdftotext')
        assert located, 'An existing pdftotext executable is required'
        extractor = Path(located)
    return subprocess.check_output([str(extractor), '-f', str(page), '-l', str(page),
                                    '-layout', '-enc', 'UTF-8', str(pdf), '-'],
                                   text=True, encoding='utf-8')


def measure_lines(text, measure):
    heading = r'^2023 / ' + ('AUTORISATIONS D.ENGAGEMENT' if measure == 'AE' else 'CR[ÉE]DITS DE PAIEMENT') + r'\s*$'
    started = False
    lines = []
    for line in text.splitlines():
        if not started:
            started = bool(re.match(heading, line.strip()))
            continue
        assert not re.match(r'^\d{4} / ', line.strip()), 'Another table reached before the consumption total'
        lines.append(line)
        if line.strip().startswith('Total des ' + measure) and 'consomm' in line:
            return lines
    raise AssertionError('Missing 2023 ' + measure + ' table on physical page 577')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=DEFAULT_DATABASE,
                        help='Existing canonical SQLite snapshot; opened read-only.')
    args = parser.parse_args()
    database = args.database.resolve(strict=True)
    database_sha = digest(database)
    inventory = json.loads((ROOT / 'reports/reserves-et-consignes-20260909/rap-reserves-pages.json').read_text(encoding='utf-8'))
    reference = next(row for row in inventory if row['year'] == 2023)
    pdf = Path(reference['path']).resolve(strict=True)
    assert reference['sha256'] == SOURCE_SHA and digest(pdf) == SOURCE_SHA, 'Reviewed original RAP changed'
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        parents = [dict(row) for row in db.execute(
            "SELECT * FROM facts WHERE year=2023 AND budget='BG' AND mission='TA' "
            "AND program='355' AND stage IN ('LFI','EXEC') ORDER BY measure,stage")]
        assert len(parents) == 4, 'Exactly four canonical programme parents expected'
        published_source = json.loads(db.execute('SELECT data FROM sources WHERE id=?', (SOURCE,)).fetchone()[0])
        assert published_source['sha256'] == SOURCE_SHA, 'Canonical catalogue identifies a different PDF'
        later_missions = [dict(row) for row in db.execute(
            "SELECT DISTINCT year,mission,mission_label FROM facts WHERE program='355' AND year>=2024 ORDER BY year,mission")]
    assert all(row['title'] == 'HT2' and not row['action'] and not row['subaction'] for row in parents)
    assert {(row['measure'], row['stage']) for row in parents} == {(m, s) for m in ('AE', 'CP') for s in EXPECTED}
    assert all(row['mission'] == 'EB' for row in later_missions), 'Unexpected annual reattachment to review separately'

    pages = {page: read_page(pdf, page) for page in (577, 580)}
    confirmation_lines = pages[580].splitlines()
    positions = [i for i, line in enumerate(confirmation_lines) if re.match(r'^\s*01 – Charge de la dette de SNCF Réseau', line)]
    assert len(positions) == 1, 'Single confirming action on page 580'
    # Page 580 independently displays HT2 and Total, first AE and then CP.
    for stage, offset in [('LFI', 0), ('EXEC', 1)]:
        assert numbers(confirmation_lines[positions[0] + offset]) == [EXPECTED[stage]] * 4, ('Page 580 confirmation changed', stage)

    groups = []
    for measure in ('AE', 'CP'):
        lines = measure_lines(pages[577], measure)
        positions = [i for i, line in enumerate(lines) if re.match(r'^\s*\d{2} – ', line)]
        assert len(positions) == 1, 'Only action 01 is published in the reviewed programme'
        index = positions[0]
        printed_label = re.split(r'\s{2,}', lines[index].strip())[0]
        assert printed_label == '01 – ' + LABEL, ('Action code or label changed', printed_label)
        assert numbers(lines[index]) == [EXPECTED['LFI']] * 3
        assert numbers(lines[index + 1]) == [EXPECTED['EXEC']] * 2
        for stage, offset in [('LFI', 0), ('EXEC', 1)]:
            amounts = numbers(lines[index + offset])
            # LFI final column contains expected FdC/AdP; take the preceding Total.
            amount = amounts[-2] if stage == 'LFI' else amounts[-1]
            totals = [line for line in lines if line.strip().startswith('Total des ' + measure)
                      and ('en LFI' in line if stage == 'LFI' else 'consomm' in line)]
            assert len(totals) == 1
            printed = numbers(totals[0])[-2 if stage == 'LFI' else -1]
            found = [row for row in parents if (row['measure'], row['stage']) == (measure, stage)]
            assert len(found) == 1 and found[0]['cents'] == amount * 100 == printed * 100
            groups.append(dict(year=2023, stage=stage, measure=measure, budget='BG', mission='TA', program='355',
                               source=SOURCE, sha256=SOURCE_SHA, page=577, total_page=577, parents=found,
                               published_total_euros=printed, action_sum_minus_parent_cents=0,
                               published_total_minus_parent_cents=0,
                               actions=[dict(code='01', label=LABEL, euros=amount, page=577)]))

    assert len(groups) == 4 and digest(database) == database_sha, 'Canonical snapshot must remain unchanged'
    REPORT.mkdir(parents=True, exist_ok=True)
    rendered = []
    for page, text in pages.items():
        (REPORT / f'rap-2023-p{page}.txt').write_text(text, encoding='utf-8')
        image = REPORT / f'rap-2023-p{page}.png'
        subprocess.run([str(POPPLER / 'pdftoppm.exe'), '-f', str(page), '-singlefile', '-r', '125', '-png',
                        str(pdf), str(image.with_suffix(''))], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        rendered.append(dict(page=page, path=str(image), sha256=digest(image)))
    dump(REPORT / 'parents.json', parents)
    dump(REPORT / 'rendered-pages.json', rendered)
    dump(REPORT / 'reconciliation.json', dict(passed=True, database=str(database), database_sha256=database_sha,
         source=SOURCE, pdf=str(pdf), sha256=SOURCE_SHA, verified_pages=[577, 580], groups=4, observations=4,
         all_four_parent_totals_match_exactly=True, later_missions_not_imported=later_missions,
         visual_review='Rendered for inspection; the builder does not itself certify visual review.',
         checks=[{k: group[k] for k in ('year', 'stage', 'measure', 'published_total_euros', 'action_sum_minus_parent_cents')}
                 for group in groups]))
    dump(TARGET, dict(updated_at='2026-09-10',
         coverage='P355, mission Écologie en 2023 seulement : LFI/consommé, AE/CP, action 01. Années ultérieures en mission EB non revues ici.',
         note='Une action publiée et un parent HT2 unique par groupe ; aucun transfert de montant entre missions ou exercices.',
         groups=groups))
    print(json.dumps(dict(groups=4, observations=4, pages=[577, 580], source=SOURCE,
                          registry=str(TARGET), sha256=digest(TARGET)), ensure_ascii=False))


if __name__ == '__main__':
    main()
