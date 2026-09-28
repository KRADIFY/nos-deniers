"""Build reviewed P345 action/subaction trees without changing canonical facts."""
import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'reports/actions-sousactions-20260910'
TARGET = ROOT / 'budget_service/data/actions-sousactions.json'
DEFAULT_DATABASE = ROOT / 'deploy/update-20260910-fdc2023/staging/budget.sqlite'
POPPLER = Path('C:/Users/Jean-Christophe/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin')
PAGES = {2023: 480, 2024: 490, 2025: 465}
SOURCES = {2023: 'c793d7737895c135ad70', 2024: '113330a8d3bb90c96604', 2025: '06557292eccf98885e32'}
CHILDREN = {'09': ['01', '02', '03', '04', '05'], '10': ['01'],
            '11': ['01', '02'], '12': ['01'], '13': ['01'],
            '14': ['01', '02', '03'], '15': ['01', '02', '03'],
            '17': ['01', '02', '03'], '18': ['01']}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def numbers(line):
    return [int(s.replace(' ', '')) for s in re.split(r'\s{2,}', line.strip())
            if re.fullmatch(r'-?\d[\d ]*', s)]


def measure_lines(pages, first, year, measure):
    """Stop at the current exercise's consumption total, before its repeated N-1."""
    heading = rf'^{year} / ' + ('AUTORISATIONS D.ENGAGEMENT' if measure == 'AE' else 'CR[ÉE]DITS DE PAIEMENT') + r'\s*$'
    selected = []
    started = False
    for offset, text in enumerate(pages):
        number = first + offset
        for line in text.splitlines():
            if not started:
                if re.match(heading, line.strip()):
                    started = True
                continue
            if re.match(r'^\d{4} / (?:AUTORISATIONS|CR[ÉE]DITS|PR[ÉE]SENTATION)', line.strip()):
                raise AssertionError(('Another table before consumption total', year, measure, number))
            selected.append((number, line))
            if line.strip().startswith('Total des ' + measure) and 'consomm' in line:
                return selected
    raise AssertionError(('Incomplete table', year, measure))


def read_nodes(lines, year, measure):
    nodes = []
    for i, (page, line) in enumerate(lines):
        match = re.match(r'^\s*(\d{2}(?:\.\d{2})?) – ', line)
        if not match:
            continue
        code = match[1]
        actual_page, actual_line = lines[i + 1]
        forecast, actual = numbers(line), numbers(actual_line)
        assert len(forecast) >= 2 and actual, (year, measure, code, line, actual_line)
        label = re.sub(r'^\d{2}(?:\.\d{2})? – ', '', re.split(r'\s{2,}', line.strip())[0])
        continuation = re.split(r'\s{2,}', actual_line.strip())[0]
        if not re.fullmatch(r'-?\d[\d ]*', continuation):
            label += ' ' + continuation
        # Last LFI column also includes forecast FdC/AdP; select the preceding Total.
        nodes.append(dict(code=code, label=label, LFI=forecast[-2], EXEC=actual[-1],
                          LFI_page=page, EXEC_page=actual_page))
    expected = [code for action, children in CHILDREN.items()
                for code in [action] + [action + '.' + child for child in children]]
    assert [n['code'] for n in nodes] == expected, (year, measure, [n['code'] for n in nodes])
    return nodes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=DEFAULT_DATABASE,
                        help='Existing canonical SQLite file, opened strictly read-only.')
    args = parser.parse_args()
    database = args.database.resolve(strict=True)
    extractor = POPPLER / 'pdftotext.exe'
    if not extractor.is_file():
        located = shutil.which('pdftotext')
        assert located, 'pdftotext is required; no dependency is installed by this collector.'
        extractor = Path(located)
    inventory = json.loads((ROOT / 'reports/reserves-et-consignes-20260909/rap-reserves-pages.json').read_text(encoding='utf-8'))
    references = json.loads((ROOT / 'reports/actions-p174-20260910/reference.json').read_text(encoding='utf-8'))['sources']
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        parents = [dict(row) for row in db.execute("SELECT * FROM facts WHERE budget='BG' AND mission='TA' AND program='345' AND year BETWEEN 2023 AND 2025 AND stage IN ('LFI','EXEC') ORDER BY year,measure,stage")]
        assert len(parents) == 12
        assert all(not r['action'] and not r['subaction'] and r['title'] == 'HT2' for r in parents)
        source_metadata = {source: json.loads(db.execute('SELECT data FROM sources WHERE id=?', (source,)).fetchone()[0])
                           for source in SOURCES.values()}

    REPORT.mkdir(parents=True, exist_ok=True)
    groups, checks, rendered, source_checks = [], [], [], []
    for year, first in PAGES.items():
        source = SOURCES[year]
        pdf = Path(next(d['path'] for d in inventory if d['year'] == year))
        sha = digest(pdf)
        assert sha == references[source]['sha256'] == source_metadata[source]['sha256'], (year, 'PDF fingerprint')
        raw = subprocess.check_output([str(extractor), '-layout', '-f', str(first), '-l', str(first + 2), str(pdf), '-'])
        pages = raw.decode('utf-8').split('\f')
        assert len(pages) == 4 and not pages[-1].strip(), (year, len(pages))
        pages = pages[:-1]
        source_checks.append(dict(year=year, source=source, sha256=sha, pdf=str(pdf),
                                  text_origin='Fresh pdftotext -layout from the SHA-256 checked PDF'))
        for measure in ('AE', 'CP'):
            lines = measure_lines(pages, first, year, measure)
            nodes = read_nodes(lines, year, measure)
            for stage in ('LFI', 'EXEC'):
                matches = [r for r in parents if (r['year'], r['measure'], r['stage']) == (year, measure, stage)]
                assert len(matches) == 1, (year, measure, stage, len(matches))
                parent = matches[0]
                actions = []
                for action_code, children in CHILDREN.items():
                    row = next(n for n in nodes if n['code'] == action_code)
                    subs = [dict(code=code, label=n['label'], euros=n[stage], page=n[stage + '_page'])
                            for code in children
                            for n in nodes if n['code'] == action_code + '.' + code]
                    assert sum(s['euros'] for s in subs) == row[stage], (year, measure, stage, action_code)
                    actions.append(dict(code=action_code, label=row['label'], euros=row[stage],
                                        page=row[stage + '_page'], subactions=subs))
                total_matches = [(p, line) for p, line in lines
                                 if line.strip().startswith('Total des ' + measure)
                                 and ('en LFI' in line if stage == 'LFI' else 'consomm' in line)]
                assert len(total_matches) == 1
                total_page, total_line = total_matches[0]
                published = numbers(total_line)[-2 if stage == 'LFI' else -1]
                delta = sum(a['euros'] * 100 for a in actions) - parent['cents']
                published_delta = published * 100 - parent['cents']
                assert abs(published_delta) <= (50 if stage == 'EXEC' else 0), (year, measure, stage, published_delta)
                assert abs(delta) <= (50 * len(actions) if stage == 'EXEC' else 0), (year, measure, stage, delta)
                group = dict(year=year, stage=stage, measure=measure, budget='BG', mission='TA', program='345',
                             source=source, sha256=sha, page=first, total_page=total_page,
                             parents=[parent], published_total_euros=published,
                             action_sum_minus_parent_cents=delta, actions=actions)
                groups.append(group)
                checks.append(dict(year=year, stage=stage, measure=measure, total_page=total_page,
                                   parent_cents=parent['cents'], published_total_euros=published,
                                   published_total_minus_parent_cents=published_delta,
                                   action_sum_minus_parent_cents=delta,
                                   subaction_sum_minus_action_cents={a['code']: 0 for a in actions}))
        for offset, text in enumerate(pages):
            page = first + offset
            prefix = REPORT / f'rap-{year}-p{page}'
            prefix.with_suffix('.txt').write_text(text, encoding='utf-8')
            subprocess.run([str(POPPLER / 'pdftoppm.exe'), '-f', str(page), '-singlefile', '-r', '125',
                            '-png', str(pdf), str(prefix)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            rendered.append(dict(year=year, page=page, path=str(prefix.with_suffix('.png'))))

    assert len(groups) == 12
    assert sum(len(g['actions']) for g in groups) == 108
    assert sum(len(a['subactions']) for g in groups for a in g['actions']) == 240
    # These are genuine reversals and explicit zeros, never parser defaults.
    for measure in ('AE', 'CP'):
        group = next(g for g in groups if (g['year'], g['measure'], g['stage']) == (2023, measure, 'EXEC'))
        assert next(s for a in group['actions'] if a['code'] == '17' for s in a['subactions'] if s['code'] == '03')['euros'] == -102300000
    group = next(g for g in groups if (g['year'], g['measure'], g['stage']) == (2025, 'CP', 'EXEC'))
    assert next(a for a in group['actions'] if a['code'] == '17')['euros'] == -105687687
    assert next(a for a in group['actions'] if a['code'] == '18')['euros'] == 0
    data = dict(updated_at='2026-09-10',
                coverage='P345 : LFI/consommé AE/CP 2023–2025 ; 9 actions et 20 sous-actions par groupe.',
                method='Totaux de programme SQL préservés ; actions et sous-actions Total RAP publiées à l’euro. Les niveaux sont imbriqués, jamais additionnés ensemble. Aucun écart d’arrondi réparti. Négatifs et zéros explicites conservés.',
                groups=groups)
    dump(TARGET, data)
    dump(REPORT / 'reconciliation.json', checks)
    dump(REPORT / 'sources.json', source_checks)
    dump(REPORT / 'parents.json', dict(database=str(database), database_sha256=digest(database), rows=parents))
    dump(REPORT / 'rendered-pages.json', rendered)
    dump(REPORT / 'build-validation.json', dict(numeric_checks_passed=True, groups=12, actions=108,
         subactions=240, observations=348, all_subaction_sums_equal_action=True,
         sources_sha256_checked=3, fresh_extraction=True, rendered_pages=9,
         registry_sha256=digest(TARGET), visual_review='Required separately; rendering alone is not visual verification.'))
    print(json.dumps(dict(groups=12, actions=108, subactions=240, observations=348,
                          sha256=digest(TARGET)), ensure_ascii=False))


if __name__ == '__main__':
    main()
