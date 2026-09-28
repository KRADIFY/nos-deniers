"""Prepare a reviewable extraction from the already collected 2023–2025 RAPs.

Does not write application data. Full pages, text and arithmetic checks stay in
reports so that integration follows the document review, including discrepancies.
"""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / 'reports/reserves-et-consignes-20260909'
OUT = ROOT / 'reports/reserves-ecologie-2023-2025'
POPPLER = Path('C:/Users/Jean-Christophe/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin')
LABELS = {
    'initial': 'Mise en réserve initiale',
    'surgels': 'Surgels',
    'degels': 'Dégels',
    'cancellations': 'Annulations / réserve en cours de gestion',
    'remaining': 'Réserve disponible avant mise en place',
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'pages').mkdir(exist_ok=True)
    inventory = json.loads((OLD / 'rap-reserves-pages.json').read_text(encoding='utf-8'))
    pilot = json.loads((ROOT / 'budget_service/data/reserves-p174.json').read_text(encoding='utf-8'))
    tables = []
    coverage = []
    for doc in sorted(inventory, key=lambda d: d['year']):
        year = doc['year']
        if year not in (2023, 2024, 2025):
            continue
        pdf = Path(doc['path'])
        assert hashlib.sha256(pdf.read_bytes()).hexdigest() == doc['sha256']
        source = next(s for s in pilot['sources'] if s['sha256'] == doc['sha256'])
        # Re-extract from the verified PDF, rather than trusting a cached text.
        text_path = OUT / f'rap-ecologie-{year}.txt'
        subprocess.run([(str(POPPLER / 'pdftotext.exe') if (POPPLER / 'pdftotext.exe').exists() else shutil.which('pdftotext')), '-layout', '-enc', 'UTF-8', str(pdf), str(text_path)], check=True, capture_output=True)
        pages = text_path.read_text(encoding='utf-8').split('\f')
        programme = None
        programmes = {}
        for index, text in enumerate(pages):
            heading = re.fullmatch(r'\s*PROGRAMME (\d{3})\s*:\s*(.+?)\s*', text, re.S)
            if heading and len(text) < 600:
                programme = dict(program=heading[1], program_label=' '.join(heading[2].split()), programme_page=index + 1)
                programmes[heading[1]] = programme
            if not re.search(r'^Mise en réserve initiale\s{2,}\d', text, re.M):
                continue
            assert programme is not None
            extracted = {}
            raw_lines = {}
            for line in text.splitlines():
                for key, label in LABELS.items():
                    if not line.startswith(label):
                        continue
                    fields = re.split(r'\s{2,}', line.strip())
                    assert len(fields) == 7, (year, index + 1, fields)
                    assert all(re.fullmatch(r'[+-]?\d{1,3}(?: \d{3})*', v) for v in fields[1:]), fields
                    assert key not in extracted
                    extracted[key] = [int(v.replace(' ', '')) * 100 for v in fields[1:]]
                    raw_lines[key] = line
            assert set(extracted) == set(LABELS) - {'cancellations'}
            rows = []
            checks = []
            for measure, offset in [('AE', 0), ('CP', 3)]:
                cells = {k: dict(title2_cents=v[offset], other_titles_cents=v[offset + 1], total_cents=v[offset + 2]) for k, v in extracted.items()}
                for field, cell in cells.items():
                    difference = cell['total_cents'] - cell['title2_cents'] - cell['other_titles_cents']
                    checks.append(dict(measure=measure, field=field, check='printed_columns', difference_cents=difference, passed=difference == 0))
                for column in ('title2_cents', 'other_titles_cents', 'total_cents'):
                    difference = cells['remaining'][column] - sum(v[column] for k, v in cells.items() if k != 'remaining')
                    checks.append(dict(measure=measure, field=column, check='printed_balance', difference_cents=difference, passed=difference == 0))
                rows.append(dict(year=year, budget='BG', mission='TA', **programme, measure=measure, source=source['id'], source_sha256=source['sha256'], page=index + 1, cells=cells, raw_lines=raw_lines))
            key = f'{year}-p{programme["program"]}'
            context = text + '\f' + (pages[index + 1] if index + 1 < len(pages) else '')
            (OUT / f'{key}-context.txt').write_text(context, encoding='utf-8')
            image = OUT / 'pages' / key
            subprocess.run([str(POPPLER / 'pdftoppm.exe'), '-f', str(index + 1), '-l', str(index + 1), '-scale-to', '1600', '-singlefile', '-png', str(pdf), str(image)], check=True, capture_output=True)
            tables.append(dict(key=key, year=year, **programme, page=index + 1, source=source, records=rows, checks=checks, context_file=f'{key}-context.txt', image=f'pages/{key}.png'))
            print(json.dumps(dict(key=key, page=index + 1, discrepancies=[c for c in checks if not c['passed']]), ensure_ascii=False), flush=True)
        found = {t['program'] for t in tables if t['year'] == year}
        assert found <= set(programmes)
        coverage.append(dict(year=year, programmes=list(programmes.values()), without_table=sorted(set(programmes) - found)))
    assert len(tables) == 28
    (OUT / 'coverage.json').write_text(json.dumps(coverage, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT / 'candidate-tables.json').write_text(json.dumps(tables, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Prepared 28 programme-year tables; no application data changed.')


if __name__ == '__main__':
    main()
