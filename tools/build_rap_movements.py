"""Build the checked P174 RAP recapitulations, distinct from the legal-act register.

Only 2023–2025, BG/TA/P174/HT2 are reviewed. PDF coordinates and all eight
columns are retained; empty cells never become zero or a new published act.
"""
import argparse
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import unicodedata

import fitz


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'reports/mouvements-rap-p174-20260910'
TARGET = ROOT / 'budget_service/data/mouvements-rap-p174.json'
DEFAULT_DATABASE = ROOT / 'deploy/update-20260910-fdc2023/staging/budget.sqlite'
POPPLER = Path('C:/Users/Jean-Christophe/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin')
SOURCES = {2023: 'c793d7737895c135ad70', 2024: '113330a8d3bb90c96604', 2025: '06557292eccf98885e32'}
PAGES = {2023: [423, 424], 2024: [429, 430], 2025: [403, 404, 405]}
CAPTIONS = {
    'ARRETES DE RATTACHEMENT DE FDC': ('RATTACHEMENT_FDC', 'FDC'),
    'ARRETES DE REPORT DE FDC': ('REPORT_FDC', 'REPORT_ENTRANT'),
    'ARRETES DE REPORT GENERAL HORS FDC HORS AENE': ('REPORT_GENERAL', 'REPORT_ENTRANT'),
    'DECRETS DE TRANSFERT': ('TRANSFERT', 'REGLEMENT'),
    "DECRETS D'ANNULATION": ('ANNULATION', 'LEGIS'),
    'DECRETS DE VIREMENT': ('VIREMENT', 'REGLEMENT'),
    'LOIS DE FINANCES RECTIFICATIVES': ('LOI_FINANCES', 'LEGIS'),
    'LOI DE FINANCES DE FIN DE GESTION': ('LOI_FINANCES', 'LEGIS'),
    'TOTAL DES OUVERTURES ET ANNULATIONS (Y.C. FDC ET ADP)': ('TOTAL', None),
}
COLUMNS = [dict(direction=direction, sign=sign, measure=measure, title=title)
           for direction, sign in [('opening', 1), ('cancellation', -1)]
           for measure in ('AE', 'CP') for title in ('2', 'HT2')]
# Independently transcribed published HT2 values: AE/CP openings, AE/CP cancellations.
# None is a blank source cell, not a statement of no movement.
EXPECTED = {
    (2023, 'RATTACHEMENT_FDC', '2023-04'): [9786, 9786, None, None],
    (2023, 'RATTACHEMENT_FDC', '2023-05'): [167548, 167548, None, None],
    (2023, 'REPORT_FDC', '2023-02-16'): [172634, 180358, None, None],
    (2023, 'REPORT_GENERAL', '2023-03-02'): [332500000, 556671718, None, None],
    (2023, 'TRANSFERT', '2023-06-27'): [None, None, 7630864, 7554519],
    (2023, 'TRANSFERT', '2023-11-20'): [14000000, 14000000, None, None],
    (2023, 'LOI_FINANCES', '2023-11-30'): [None, None, 780266868, 1092321217],
    (2024, 'REPORT_FDC', '2024-02-22'): [340578, 339968, None, None],
    (2024, 'REPORT_GENERAL', '2024-03-13'): [None, 47500000, None, None],
    (2024, 'ANNULATION', '2024-02-21'): [None, None, 950000000, 1300000000],
    (2024, 'TRANSFERT', '2024-06-26'): [None, None, 5120800, 5120800],
    (2024, 'TRANSFERT', '2024-11-28'): [None, None, 7356085, 7356085],
    (2024, 'LOI_FINANCES', '2024-12-07'): [None, None, None, 182000000],
    (2025, 'REPORT_FDC', '2025-02-05'): [302578, 302595, None, None],
    (2025, 'REPORT_GENERAL', '2025-03-10'): [400000000, 161600000, None, None],
    (2025, 'ANNULATION', '2025-04-25'): [None, None, 105005990, 40529252],
    (2025, 'TRANSFERT', '2025-07-09'): [None, None, 9533750, 9533750],
    (2025, 'TRANSFERT', '2025-12-03'): [None, None, 3390800, 3390800],
    (2025, 'VIREMENT', '2025-07-11'): [None, None, 300000, 300000],
    (2025, 'LOI_FINANCES', '2025-12-08'): [None, None, 2920000, 22920000],
}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def norm(text):
    return ' '.join(unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode().upper().split())


def lines_of(page):
    return sorted([dict(text=''.join(s['text'] for s in line['spans']).strip(),
                        bbox=[round(float(n), 3) for n in line['bbox']])
                   for block in page.get_text('dict')['blocks'] for line in block.get('lines', [])],
                  key=lambda line: (round(line['bbox'][1], 1), line['bbox'][0]))


def midpoint(line):
    return (line['bbox'][0] + line['bbox'][2]) / 2


def cells_at(lines, label, headers):
    values = [dict(column, amount_cents=None, raw_text=None) for column in COLUMNS]
    for line in lines:
        if abs(line['bbox'][1] - label['bbox'][1]) > 0.8 or line['bbox'][0] <= label['bbox'][2]:
            continue
        text = line['text']
        if not text:
            continue
        assert re.fullmatch(r'\d[\d\s]*(?:,\d{1,2})?', text), ('Unexpected numeric cell', line)
        index = min(range(8), key=lambda i: abs(midpoint(headers[i]) - midpoint(line)))
        assert abs(midpoint(headers[index]) - midpoint(line)) < 28, ('Ambiguous column', line)
        assert values[index]['amount_cents'] is None, ('Two numeric lines in one cell', index, line)
        amount = Decimal(re.sub(r'\s+', '', text).replace(',', '.')) * 100
        assert amount == amount.to_integral_value() and amount >= 0
        values[index].update(amount_cents=int(amount), raw_text=text, bbox=line['bbox'])
    return values


def parse_date(raw):
    if re.fullmatch(r'\d{2}/\d{4}', raw):
        return datetime.strptime(raw, '%m/%Y').strftime('%Y-%m'), 'month', 'month'
    assert re.fullmatch(r'\d{2}/\d{2}/\d{4}', raw), ('Unexpected date', raw)
    return datetime.strptime(raw, '%d/%m/%Y').date().isoformat(), 'day', 'signature'


def extract_page(page, year, number, source, sha):
    lines = lines_of(page)
    captions = [line for line in lines if norm(line['text']) in CAPTIONS]
    assert captions, ('No reviewed movement table', year, number)
    rows, totals = [], []
    for index, caption in enumerate(captions):
        end_y = captions[index + 1]['bbox'][1] if index + 1 < len(captions) else page.rect.height
        area = [line for line in lines if caption['bbox'][1] < line['bbox'][1] < end_y]
        headers = sorted([line for line in area if line['text'] in ('Titre 2', 'Autres titres')], key=lambda line: line['bbox'][0])
        assert len(headers) == 8 and [line['text'] for line in headers] == ['Titre 2', 'Autres titres'] * 4
        assert max(h['bbox'][1] for h in headers) - min(h['bbox'][1] for h in headers) < 0.5
        directions = sorted([line for line in area if norm(line['text']) in ('OUVERTURES', 'ANNULATIONS')], key=lambda line: line['bbox'][0])
        assert [norm(line['text']) for line in directions] == ['OUVERTURES', 'ANNULATIONS']
        measures = sorted([line for line in area if norm(line['text']) in ("AUTORISATIONS D'ENGAGEMENT", 'CREDITS DE PAIEMENT')], key=lambda line: line['bbox'][0])
        assert [norm(line['text']) for line in measures] == ["AUTORISATIONS D'ENGAGEMENT", 'CREDITS DE PAIEMENT'] * 2
        kind, stage = CAPTIONS[norm(caption['text'])]
        table_id = f'rap-{year}-p174-{number}-{kind.lower()}'
        dates = [line for line in area if re.fullmatch(r'\d{2}/(?:\d{2}/)?\d{4}', line['text'])]
        if kind != 'TOTAL':
            assert dates, ('No dated row', table_id)
        else:
            assert not dates, ('Unexpected dated grand total', table_id)
        table_rows = []
        for line in dates:
            date, precision, date_kind = parse_date(line['text'])
            assert int(date[:4]) == year
            values = cells_at(area, line, headers)
            assert all(values[i]['amount_cents'] is None for i in (0, 2, 4, 6)), 'Unexpected T2 amount: P174 HT2 pilot only'
            key = year, kind, date
            assert key in EXPECTED, ('New unreviewed source row', key)
            expected = [None if v is None else v * 100 for v in EXPECTED[key]]
            assert [values[i]['amount_cents'] for i in (1, 3, 5, 7)] == expected, ('Published transcription differs', key, values)
            row = dict(row_id=f'rap-{year}-p174-{kind.lower()}-{date}', table_id=table_id,
                       year=year, page=number, source=source, sha256=sha, kind=kind,
                       reconciles_stage=stage, date=date, date_precision=precision, date_kind=date_kind,
                       table_title=caption['text'], source_date=line['text'], cells=values,
                       bbox=[line['bbox'][0], line['bbox'][1], 550.0, line['bbox'][3]],
                       published_precision='Montants publiés à l’euro dans le RAP.')
            table_rows.append(row)
            rows.append(row)
        total_lines = [line for line in area if line['text'] == ('Total général' if kind == 'TOTAL' else 'Total')]
        assert len(total_lines) == 1, ('Single source total expected', table_id, total_lines)
        total_cells = cells_at(area, total_lines[0], headers)
        if table_rows:
            for i, cell in enumerate(total_cells):
                reported = [row['cells'][i]['amount_cents'] for row in table_rows if row['cells'][i]['amount_cents'] is not None]
                amount = sum(reported) if reported else None
                assert cell['amount_cents'] == amount, ('Published table total mismatch', table_id, i, amount, cell)
        totals.append(dict(table_id=table_id, year=year, page=number, source=source, sha256=sha, kind=kind,
                           table_title=caption['text'], cells=total_cells,
                           headers=[dict(column, printed_label=h['text'], bbox=h['bbox']) for column, h in zip(COLUMNS, headers)],
                           is_grand_total=kind == 'TOTAL', checked_against_dated_rows=bool(table_rows)))
    return rows, totals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=DEFAULT_DATABASE)
    args = parser.parse_args()
    database = args.database.resolve(strict=True)
    database_sha = digest(database)
    inventory = json.loads((ROOT / 'reports/reserves-et-consignes-20260909/rap-reserves-pages.json').read_text(encoding='utf-8'))
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        parents = [dict(row) for row in db.execute(
            "SELECT * FROM facts WHERE budget='BG' AND mission='TA' AND program='174' AND year BETWEEN 2023 AND 2025 "
            "AND stage IN ('LFI','OUVERT','FDC','REPORT_ENTRANT','REGLEMENT','LEGIS') ORDER BY year,measure,stage")]
        source_refs = {sid: json.loads(db.execute('SELECT data FROM sources WHERE id=?', (sid,)).fetchone()[0]) for sid in SOURCES.values()}
    assert len(parents) == 36 and all(row['title'] == 'HT2' and not row['action'] and not row['subaction'] for row in parents)
    assert len({(row['year'], row['measure'], row['stage']) for row in parents}) == 36
    REPORT.mkdir(parents=True, exist_ok=True)
    evidence, table_totals, references, rendered = [], [], [], []
    for year, pages in PAGES.items():
        record = next(row for row in inventory if row['year'] == year)
        pdf = Path(record['path']).resolve(strict=True)
        sha = digest(pdf)
        sid = SOURCES[year]
        assert sha == record['sha256'] == source_refs[sid]['sha256'], ('Reviewed PDF changed', year)
        references.append(dict(id=sid, sha256=sha, year=year, pages=pages))
        with fitz.open(pdf) as doc:
            for number in pages:
                page = doc[number - 1]
                rows, totals = extract_page(page, year, number, sid, sha)
                evidence.extend(rows)
                table_totals.extend(totals)
                (REPORT / f'rap-{year}-p{number}.txt').write_text(page.get_text(), encoding='utf-8')
                image = REPORT / f'rap-{year}-p{number}.png'
                subprocess.run([str(POPPLER / 'pdftoppm.exe'), '-f', str(number), '-singlefile', '-r', '125', '-png',
                                str(pdf), str(image.with_suffix(''))], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                rendered.append(dict(year=year, page=number, path=str(image), sha256=digest(image)))
    assert len(evidence) == 20 and {(row['year'], row['kind'], row['date']) for row in evidence} == set(EXPECTED)
    assert len({row['row_id'] for row in evidence}) == len(evidence)
    items = []
    for row in evidence:
        for cell in row['cells']:
            if cell['title'] != 'HT2' or cell['amount_cents'] is None:
                continue
            linked = 'JORFTEXT000049180270' if (row['year'], row['kind'], row['date']) == (2024, 'ANNULATION', '2024-02-21') else None
            items.append(dict(id=row['row_id'] + '/' + cell['measure'] + '/' + cell['direction'], row_id=row['row_id'],
                              year=row['year'], budget='BG', mission='TA', program='174', title='HT2',
                              measure=cell['measure'], kind=row['kind'], date=row['date'],
                              date_precision=row['date_precision'], date_kind=row['date_kind'], sign=cell['sign'],
                              amount_cents=cell['amount_cents'], source=row['source'], sha256=row['sha256'], page=row['page'],
                              field=f"{row['table_title']} · {row['source_date']} · {'Ouvertures' if cell['sign'] == 1 else 'Annulations'} · {cell['measure']} · Autres titres",
                              reconciles_stage=row['reconciles_stage'], linked_act_id=linked))
    assert len(items) == 38 and len({item['id'] for item in items}) == 38
    assert sum(item['linked_act_id'] is not None for item in items) == 2
    assert sum(item['date_precision'] == 'month' for item in items) == 4

    reconciliations = []
    for year in PAGES:
        total = next(t for t in table_totals if t['year'] == year and t['is_grand_total'])
        for i, column in enumerate(COLUMNS):
            values = [row['cells'][i]['amount_cents'] for row in evidence if row['year'] == year and row['cells'][i]['amount_cents'] is not None]
            assert total['cells'][i]['amount_cents'] == (sum(values) if values else None), ('Grand total differs', year, column)
        for measure in ('AE', 'CP'):
            for stage in ('FDC', 'REPORT_ENTRANT', 'REGLEMENT', 'LEGIS'):
                selected = [item for item in items if (item['year'], item['measure'], item['reconciles_stage']) == (year, measure, stage)]
                parent = next(row for row in parents if (row['year'], row['measure'], row['stage']) == (year, measure, stage))
                actual = sum(item['sign'] * item['amount_cents'] for item in selected) if selected else None
                delta = actual - parent['cents'] if actual is not None else None
                expected_delta = -19 if year == 2023 and stage == 'FDC' else 0
                assert delta is None or delta == expected_delta, ('Unreviewed annual category difference', year, measure, stage, delta)
                status = 'no_rows_in_rap_not_zero' if actual is None else 'exact' if delta == 0 else 'published_rounding_difference'
                reconciliations.append(dict(year=year, measure=measure, stage=stage, status=status,
                                            source=SOURCES[year], sha256=source_refs[SOURCES[year]]['sha256'],
                                            reported_net_cents=actual, canonical_cents=parent['cents'],
                                            difference_cents=delta, item_ids=[item['id'] for item in selected],
                                            canonical_source=parent['source'], canonical_line=parent['line'], canonical_field=parent['field']))
            lfi = next(row for row in parents if (row['year'], row['measure'], row['stage']) == (year, measure, 'LFI'))
            opened = next(row for row in parents if (row['year'], row['measure'], row['stage']) == (year, measure, 'OUVERT'))
            reported = sum(item['sign'] * item['amount_cents'] for item in items if (item['year'], item['measure']) == (year, measure))
            assert lfi['cents'] + reported == opened['cents'], ('RAP gross movements do not reproduce open credits', year, measure)
            reconciliations.append(dict(year=year, measure=measure, stage='OUVERT', status='exact',
                                        source=SOURCES[year], sha256=source_refs[SOURCES[year]]['sha256'],
                                        lfi_cents=lfi['cents'], reported_net_cents=reported,
                                        lfi_plus_reported_cents=lfi['cents'] + reported, canonical_cents=opened['cents'],
                                        difference_cents=0, canonical_source=opened['source'],
                                        canonical_line=opened['line'], canonical_field=opened['field']))
    assert digest(database) == database_sha, 'Canonical database changed during read-only extraction'
    limits = [
        'Récapitulations des RAP du programme 174, mission Écologie, 2023–2025, autres titres uniquement. Ce registre ne couvre pas toute la mission ni tous les actes de l’État.',
        'Les dates sont les dates de signature telles que publiées dans le RAP ; les rattachements FdC 2023 sont des agrégats mensuels. Aucun jour, date de publication ou date d’effet n’est inventé.',
        'Les montants sont publiés à l’euro. Les cellules blanches des huit colonnes sont conservées à null dans les preuves ; leur absence ne signifie pas montant nul ou absence de mouvement.',
        'Ces lignes expliquent les agrégats annuels et ne s’ajoutent ni aux crédits ouverts ni aux événements JORF. Les deux lignes du 21 février 2024 sont liées au même décret déjà intégré.',
        'Les reports de FdC appartiennent aux reports entrants, pas aux nouveaux rattachements FdC. Le tableau 2025 exclut explicitement le décret de services votés.',
        'La colonne annuelle LFR peut réunir lois de finances et décrets d’annulation ; les transferts et virements sont rapprochés de la colonne Mvts_reglementaires.',
        'Les contreparties des transferts, les actions, sous-actions et la part MaPrimeRénov’ ne sont pas établies par ces tableaux. Aucun gel ou dégel n’est déduit de ces montants.',
        'Les dates citées par les RAP restent des observations de la source tant que chaque acte n’est pas identifié. Le lien du décret du 21 février 2024 est le seul lien juridique établi dans ce lot.',
    ]
    registry = dict(updated_at='2026-09-10', source_kind='rap_recapitulation',
                    coverage='P174 Écologie, 2023–2025 : 20 lignes sources, 38 montants AE/CP publiés, autres titres ; récapitulations distinctes des actes JORF.',
                    scope=dict(years=[2023, 2024, 2025], budget='BG', mission='TA', program='174', title='HT2'),
                    limits=limits, sources=references, items=items, evidence_rows=evidence,
                    table_totals=table_totals, reconciliations=reconciliations)
    dump(TARGET, registry)
    dump(REPORT / 'parents.json', parents)
    dump(REPORT / 'rendered-pages.json', rendered)
    dump(REPORT / 'reconciliation.json', dict(passed=True, database=str(database), database_sha256=database_sha,
         observations=len(items), evidence_rows=len(evidence), original_cells=len(evidence) * 8,
         empty_original_cells=sum(c['amount_cents'] is None for row in evidence for c in row['cells']),
         explicit_zero_original_cells=sum(c['amount_cents'] == 0 for row in evidence for c in row['cells']),
         linked_existing_act_observations=2, monthly_observations=4,
         table_totals_checked=len(table_totals), annual_checks=reconciliations,
         registry_sha256=digest(TARGET), visual_review='Pages rendered; visual review to record separately.'))
    print(json.dumps(dict(passed=True, items=len(items), evidence_rows=len(evidence), table_totals=len(table_totals),
                          registry=str(TARGET), sha256=digest(TARGET)), ensure_ascii=False))


if __name__ == '__main__':
    main()
