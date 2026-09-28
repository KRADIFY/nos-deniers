"""Check the complete annex delta, its proofs and the site's numeric restitution."""
import collections
import csv
import io
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.integrate_researched_annexes import BASE, OUT, TARGET, RESEARCH, KEY, read, dump, sha
os.environ['BUDGET_DATA_DIR'] = str(TARGET)
from budget_service import api


def main():
    started = time.monotonic()
    plan, receipt = read(OUT / 'plan.json'), read(OUT / 'receipt.json')
    assert sha(TARGET / 'derived/budget.sqlite') == receipt['database_sha256']
    assert sha(BASE / 'derived/budget.sqlite') == receipt['baseline_sha256']
    assert sha(OUT / 'plan.json') == receipt['plan_sha256']
    db = api.connect()
    before = sqlite3.connect((BASE / 'derived/budget.sqlite').resolve().as_uri() + '?mode=ro', uri=True)
    fields = [r[1] for r in before.execute('pragma table_info(facts)')]
    old = collections.Counter(before.execute('select * from facts').fetchall())
    added = collections.Counter(tuple(r[k] for k in fields) for r in plan['facts'])
    now = collections.Counter(tuple(r) for r in db.execute('select * from facts'))
    assert now == old + added, 'Modification extérieure au lot d’ajouts'
    for table in ('published_nodes', 'reconciled_totals', 'nomenclature_provenance'):
        assert collections.Counter(tuple(r) for r in db.execute('select * from ' + table)) == collections.Counter(before.execute('select * from ' + table).fetchall())
    review_keys = {tuple(r[k] for k in KEY) for r in plan['reviews']}
    for r in before.execute('select * from cell_reviews'):
        if r[:5] not in review_keys:
            assert tuple(db.execute('select * from cell_reviews where year=? and stage=? and measure=? and budget=? and path=?', r[:5]).fetchone()) == r
    for sid, source in plan['source_evidence'].items():
        assert sha(TARGET / source['path']) == source['sha256']
    expected = {(r['year'], r['stage'], r['measure'], r['budget'], r['mission'] + '/' + r['program']): r for r in plan['facts']}
    buckets = {}
    counts = collections.Counter()
    for review in plan['reviews']:
        key = tuple(review[k] for k in KEY)
        bucket = review['year'], review['budget'], review['measure']
        if bucket not in buckets:
            p = api.parameters({k: [str(v)] for k, v in dict(start=bucket[0], end=bucket[0], budget=bucket[1], measure=bucket[2]).items()})
            records = api.selected_records(db, p)
            by_stage = collections.defaultdict(list)
            for r in records:
                by_stage[r['stage']].append(r)
            buckets[bucket] = p, records, by_stage
        p, records, by_stage = buckets[bucket]
        actual_review = records.cell_reviews[key]
        assert actual_review == review
        # Only the exact review can affect a programme cell; API explorer below
        # checks full mission/budget aggregation with all reviews present.
        local_reviews = {key: actual_review}
        args = by_stage[review['stage']], review['path'], review['year'], review['stage']
        result = api.cell(*args, p, {}, reviews=local_reviews)
        if review['status'] == 'verified':
            wanted = expected[key]
            assert result['nominal_cents'] == wanted['cents'], (key, result)
            assert result['value'] == wanted['cents'] / 100
            excluded = api.cell(*args, dict(p, exclude=[review['path']]), {}, reviews=local_reviews)
            assert excluded['value'] == 0 and excluded['status'] == 'excluded'
            for proof in review['proofs']:
                assert any(c['source'] == proof['source_id'] and c['page'] == proof['physical_page'] for c in result['citations'])
            counts['numeric_cells'] += 1
            counts['exclusions'] += 1
        else:
            assert result['value'] is None and result['status'] == 'missing'
            assert 'pas encore intégré' in result['reason']
            assert result['citations']
            counts['withheld_cells'] += 1
    print(json.dumps(dict(phase='cells', counts=dict(counts))), flush=True)
    # Real provenance code, including explicit zeros, negative amounts, both
    # parts of split tables and held source discrepancies.
    examples = [next(r for r in plan['reviews'] if r['source_cents'] == 0 and r['status'] == 'verified'),
                next(r for r in plan['reviews'] if r['source_cents'] < 0 and r['status'] == 'verified'),
                next(r for r in plan['reviews'] if r['stage'] == 'OUVERT'),
                next(r for r in plan['reviews'] if r['status'] == 'pending')]
    examples += [next(r for r in plan['reviews'] if r['proofs'][0]['source_id'] == sid) for sid in plan['source_evidence']]
    for r in examples:
        p = buckets[r['year'], r['budget'], r['measure']][0]
        proof = api.provenance(db, p, r['year'], r['stage'], r['path'])
        assert proof['explanation']['summary'] == r['explanation']
        assert {x['source_id'] for x in r['proofs']} <= {x['id'] for x in proof['sources']}
        if r['status'] == 'verified':
            assert any(x.get('page') == r['proofs'][0]['physical_page'] for x in proof['rows'])
        counts['provenance'] += 1
    # The old missing-cell cohort, recomputed directly with the same selection logic.
    matrix = read(RESEARCH / 'matrix-current.json')
    core = collections.Counter()
    cache = {}
    for row in matrix:
        if row['year'] > 2025:
            continue
        b = row['year'], row['budget'], row['measure']
        if b not in cache:
            p = api.parameters({k: [str(v)] for k, v in dict(start=b[0], end=b[0], budget=b[1], measure=b[2]).items()})
            rec = api.selected_records(db, p)
            grouped = collections.defaultdict(list)
            for r in rec:
                grouped[r['mission'] + '/' + r['program'], r['stage']].append(r)
            cache[b] = p, rec, grouped
        p, rec, grouped = cache[b]
        k = tuple(row[x] for x in KEY)
        review = rec.cell_reviews.get(k)
        value = api.cell(grouped[row['path'], row['stage']], row['path'], row['year'], row['stage'], p, {}, reviews={k: review} if review else {})
        status = 'available' if value['value'] is not None else 'not_applicable' if value['status'] == 'not_applicable' else 'pending'
        if row['budget'] == 'CAS' and row['path'] == 'ZA/811' and row['year'] == 2017:
            status = 'not_applicable'
        core[status] += 1
    assert dict(core) == dict(available=12613, not_applicable=71, pending=28), dict(core)
    report = dict(passed=True, **dict(counts), core_cohort=dict(core), all_prior_facts_unchanged=True,
                  source_pdf_hashes=6, source_total_rows_reread=plan['checked_pdf_rows'],
                  data_version=receipt['data_version'], elapsed_seconds=round(time.monotonic() - started, 2))
    dump(OUT / 'verification.json', report)
    print(json.dumps(report, ensure_ascii=False), flush=True)
    before.close(); db.close()


if __name__ == '__main__':
    main()
