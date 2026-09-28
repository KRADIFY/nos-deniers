"""Add the reviewed 2017–2022 annex cells to a copy of the prepared database.

The predecessor and publication bundle are immutable. Disputed rows are stored
as documentary reviews, never as numeric facts. Re-running verifies the receipt.
"""
import collections
import hashlib
import json
import os
import re
import shutil
import sqlite3
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'outputs/recherche-manques-suite-20260928'
BASE = ROOT / 'reports/integration-classeurs-20260928/data'
OUT = ROOT / 'reports/integration-annexes-20260928'
TARGET = OUT / 'data'
FIELDS = ['LFI', 'LEGIS', 'REPORT_ENTRANT', 'REGLEMENT', 'FDC', 'FONGIBILITE',
          'OUVERT', 'EXEC', 'PLRG_OUVERTURE', 'PLRG_ANNULATION', 'REPORT_SORTANT']
KEY = ('year', 'stage', 'measure', 'budget', 'path')
EXPECTED_BASE = '7eb26dbe49fed6e93c2f10aebe4f7bce5b3a8814eae6c05972f053bcb37e7baf'


def read(path):
    return json.loads(Path(path).read_text('utf-8'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), 'utf-8')
    tmp.replace(path)


def euro(cents):
    return f'{Decimal(cents) / 100:,.2f}'.replace(',', ' ').replace('.', ',') + ' €'


def reread_pdf_rows(rows):
    """Re-read every used total row; keep actual page, raw cell and coordinates."""
    import pymupdf as fitz
    docs = {}
    spans_cache = {}
    evidence = {}
    try:
        for row in rows:
            sid = row['source']
            if sid not in docs:
                docs[sid] = fitz.open(RESEARCH / 'pdf' / (sid + '.pdf'))
            values = []
            for index, number in enumerate(row['pages']):
                key = sid, number
                if key not in spans_cache:
                    page = docs[sid][number - 1]
                    spans_cache[key] = [
                        dict(text=s['text'].strip(), bbox=list(fitz.Rect(s['bbox']) * page.rotation_matrix))
                        for b in page.get_text('dict')['blocks']
                        for line in b.get('lines', []) for s in line['spans']]
                spans = [s for s in spans_cache[key] if abs(s['bbox'][1] - row['y']) < .9]
                if index == 0:
                    totals = [s for s in spans if s['text'] == 'Total']
                    assert len(totals) == 1, (key, row['y'], 'Total non unique')
                    spans = [s for s in spans if s['bbox'][0] > totals[0]['bbox'][2]]
                for span in sorted(spans, key=lambda s: s['bbox'][0]):
                    if re.fullmatch(r'-?\d[\d ]*(?:,\d{2})?', span['text']):
                        amount = int(Decimal(span['text'].replace(' ', '').replace(',', '.')) * 100)
                        values.append(dict(cents=amount, page=number, raw=span['text'], bbox=span['bbox']))
            assert len(values) == 11, (row['year'], row['program'], row['measure'])
            assert [v['cents'] for v in values] == [row['cells'][s] for s in FIELDS]
            evidence[row['year'], row['program'], row['measure']] = dict(zip(FIELDS, values))
    finally:
        for doc in docs.values():
            doc.close()
    return evidence


def create_plan():
    baseline = BASE / 'derived/budget.sqlite'
    assert sha(baseline) == EXPECTED_BASE, 'Le prédécesseur a changé ; intégration interrompue.'
    findings = read(RESEARCH / 'findings.json')
    assert len(findings) == 12016
    assert len({tuple(r[k] for k in KEY) for r in findings}) == len(findings)
    row_keys = {(r['year'], r['program'], r['measure']) for r in findings}
    annexes = [r for r in read(RESEARCH / 'annex-rows.json')
               if r['controlled'] and (r['year'], r['program'], r['measure']) in row_keys]
    assert len(annexes) == 1497
    for row in annexes:
        c = row['cells']
        assert sum(c[s] for s in FIELDS[:6]) == c['OUVERT']
        assert c['OUVERT'] + c['PLRG_OUVERTURE'] == c['EXEC'] + c['PLRG_ANNULATION'] + c['REPORT_SORTANT']
    with sqlite3.connect(baseline.resolve().as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        catalog = {r['id']: json.loads(r['data']) for r in db.execute('select * from sources')}
        known = collections.defaultdict(list)
        for row in db.execute('select * from facts'):
            known[row['year'], row['budget'], row['mission'] + '/' + row['program']].append(dict(row))
        prior_reviews = {tuple(r[k] for k in KEY): json.loads(r['data']) for r in db.execute('select * from cell_reviews')}
    source_ids = sorted({r['source'] for r in findings})
    assert len(source_ids) == 6
    for sid in source_ids:
        assert sha(RESEARCH / 'pdf' / (sid + '.pdf')) == catalog[sid]['sha256']
    pdf_evidence = reread_pdf_rows(annexes)
    facts, reviews, held = [], [], []
    for row in findings:
        key = tuple(row[k] for k in KEY)
        peers = known[row['year'], row['budget'], row['path']]
        assert peers and not any(p['stage'] == row['stage'] and p['measure'] == row['measure'] for p in peers)
        assert prior_reviews.get(key, {}).get('status') in (None, 'pending'), key
        comparison = row['comparison']
        exact_enough = sum(abs(c['gap_cents']) <= 1000 for c in comparison.values()) >= 2
        divergent = any(abs(c['gap_cents']) > 1000 for c in comparison.values())
        assert exact_enough
        approved = row['status'] == 'Retrouvé et rapproché'
        assert approved == (not divergent)
        source = catalog[row['source']]
        locator = pdf_evidence[row['year'], row['program'], row['measure']][row['stage']]
        assert locator['cents'] == row['cents']
        evidence = (f"P{row['program']}, {row['year']}, {row['measure']}, ligne Total, "
                    f"{row['stage_label']} : {euro(row['cents'])}. Valeur imprimée : {locator['raw']}.")
        proofs = [dict(source_id=row['source'], physical_page=locator['page'],
                       evidence=evidence, sha256=source['sha256'], publisher_url=source['url'],
                       bbox=locator['bbox'], raw_text=locator['raw'], unit='EUR')]
        for number in row['pages']:
            if number != locator['page']:
                proofs.append(dict(source_id=row['source'], physical_page=number,
                                   evidence='Autre partie du même tableau : programme, en-têtes et totaux de contrôle.',
                                   sha256=source['sha256'], publisher_url=source['url']))
        method = ('Lecture du total publié dans l’annexe du budget général ; programme, année, AE/CP et colonne contrôlés. '
                  'Identités des crédits ouverts et du solde de clôture exactes dans cette annexe. '
                  'Comparaison avec les étapes déjà intégrées ; les montants des sources restent distincts.')
        details = ' '.join(f"{stage} : référence {euro(c['site_cents'])}, annexe {euro(c['source_cents'])}, "
                          f"écart {euro(c['gap_cents'])}." for stage, c in comparison.items() if c['gap_cents'])
        explanation = (f"{row['stage_label']} du programme {row['program']} en {row['year']} ({row['measure']}) : "
                       f"{euro(row['cents'])}, total publié dans {source['title']}. ")
        if row['cents'] == 0:
            explanation += 'Le document imprime explicitement zéro ; ce n’est pas une case vide. '
        if row['cents'] < 0:
            explanation += 'Le signe négatif publié est conservé : il s’agit d’un mouvement net de diminution. '
        if approved:
            explanation += 'Les étapes comparables concordent à 10 € près au maximum. '
        else:
            explanation = ('Montant repéré dans l’annexe, mais pas encore intégré au calcul. '
                           'Le consommé ou les crédits de référence diffèrent entre publications ; la cause doit être qualifiée. '
                           + explanation)
        explanation += details
        review = dict((k, row[k]) for k in KEY)
        review.update(status='verified' if approved else 'pending', method=method, explanation=explanation,
                      proofs=proofs, comparison=comparison, source_cents=row['cents'],
                      input_id=row['id'], batch='annexes-2017-2022-20260928',
                      review_before=prior_reviews.get(key))
        reviews.append(review)
        if not approved:
            held.append(row)
            continue
        mission, program = row['path'].split('/')
        fact = dict(year=row['year'], stage=row['stage'], measure=row['measure'], budget=row['budget'],
                    mission=mission, mission_label=peers[0]['mission_label'], program=program,
                    program_label=peers[0]['program_label'], action='', action_label='',
                    subaction='', subaction_label='', category='', title='', cents=row['cents'],
                    source=row['source'], line=locator['page'], approximate=0,
                    field='Annexe BG : total du programme ; ' + row['stage_label'] + ' (EUR)')
        facts.append(fact)
    assert len(facts) == 11672 and len(held) == 344
    return dict(version='annexes-reviewed-1', baseline_sha256=EXPECTED_BASE, facts=facts, reviews=reviews,
                held=held, source_evidence={sid: dict(catalog[sid], imported=True, numeric_import=True) for sid in source_ids},
                input_sha256={name: sha(RESEARCH / name) for name in ('findings.json', 'annex-rows.json', 'sources.json')},
                checked_pdf_rows=len(annexes), added_core=40, added_management=11632,
                held_management=344, disputed_programme_measure_rows=43)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    receipt_path = OUT / 'receipt.json'
    if receipt_path.exists():
        receipt = read(receipt_path)
        assert sha(TARGET / 'derived/budget.sqlite') == receipt['database_sha256']
        assert sha(OUT / 'plan.json') == receipt['plan_sha256']
        assert sha(BASE / 'derived/budget.sqlite') == EXPECTED_BASE
        print('Déjà intégré : base, plan et prédécesseur inchangés.'); return
    plan = create_plan()
    if (OUT / 'plan.json').exists():
        assert read(OUT / 'plan.json') == plan, 'Plan préexistant différent'
    dump(OUT / 'plan.json', plan)
    # Only immutable assets are linked. The new database is built transactionally.
    for src in BASE.rglob('*'):
        if not src.is_file() or src.name in ('budget.sqlite', 'data-audit.json'):
            continue
        dest = TARGET / src.relative_to(BASE)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            os.link(src, dest)
    derived = TARGET / 'derived'
    derived.mkdir(parents=True, exist_ok=True)
    target_db = derived / 'budget.sqlite'
    assert not target_db.exists(), 'Base finale sans reçu : inspection nécessaire'
    build = derived / 'budget.build.sqlite'
    shutil.copyfile(BASE / 'derived/budget.sqlite', build)
    for sid, record in plan['source_evidence'].items():
        dest = (TARGET / record['path']).resolve()
        assert dest.is_relative_to(TARGET.resolve())
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            assert sha(dest) == record['sha256']
        else:
            shutil.copyfile(RESEARCH / 'pdf' / (sid + '.pdf'), dest)
        assert sha(dest) == record['sha256']
    with sqlite3.connect(build) as db:
        fields = [r[1] for r in db.execute('pragma table_info(facts)')]
        assert len(fields) == 19
        db.executemany('insert into facts values (' + ','.join('?' for _ in fields) + ')',
                       [tuple(r[k] for k in fields) for r in plan['facts']])
        db.executemany('insert or replace into cell_reviews values (?,?,?,?,?,?)',
                       [tuple(r[k] for k in KEY) + (json.dumps(r, ensure_ascii=False),) for r in plan['reviews']])
        for sid, record in plan['source_evidence'].items():
            db.execute('update sources set data=? where id=?', (json.dumps(record, ensure_ascii=False), sid))
        count = db.execute('select count(*) from facts').fetchone()[0]
        assert count == 135155
        stats = {f'{y}/{s}/{b}': n for y, s, b, n in db.execute('select year,stage,budget,count(*) from facts group by year,stage,budget')}
        meta = dict(fact_count=count, stats=stats,
                    imported_source_count=db.execute('select count(distinct source) from facts').fetchone()[0],
                    data_version=hashlib.sha256((EXPECTED_BASE + sha(OUT / 'plan.json')).encode()).hexdigest(),
                    catalogue_updated_at='2026-09-28',
                    annex_review_20260928=dict(plan_sha256=sha(OUT / 'plan.json'), added=11672,
                                              core=40, management=11632, pending_management=344,
                                              source_rows_reread=1497, remaining_core=28))
        for key, value in meta.items():
            db.execute('insert or replace into meta values (?,?)', (key, json.dumps(value, ensure_ascii=False)))
        assert db.execute('pragma integrity_check').fetchone()[0] == 'ok'
    db.close()
    build.replace(target_db)
    assert sha(BASE / 'derived/budget.sqlite') == EXPECTED_BASE
    receipt = dict(**meta, database_sha256=sha(target_db), baseline_sha256=EXPECTED_BASE,
                   plan_sha256=sha(OUT / 'plan.json'), sources=6, publication='not_published')
    dump(receipt_path, receipt)
    print(json.dumps({k: v for k, v in receipt.items() if k != 'stats'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
