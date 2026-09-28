#!/usr/bin/env python3
"""Validate the running RAP recapitulation API without changing data or services.

Run only after the matching image has passed its separate unit-test suite and
has been started. The mandatory unit-test count records that preceding result;
this script does not execute the suite itself.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
import sqlite3
from urllib.parse import urlencode
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / 'budget_service/data/mouvements-rap-p174.json'
REPORT = ROOT / 'reports/mouvements-rap-p174-20260910/http-validation.json'
EVENT_DATABASE = ROOT / 'reports/restore-20260910-actions-mpr/data/derived/events.sqlite'
EVENT_SHA = '7b2dbd157b1440194addc2394ccdd031be92c50e0ec3a1a2f35c8a4a65728aae'
EVENT_VERSION = 'b49805f822c1404fa6b0c21cfac56283fd7904117db84b2f933a59cdbdd63a28'
DATA_VERSION = '0dd3cc2dc154bbdeb80b8d270c917963fdadee2f119a110544b6db0110b23344'
ACT_ID = 'JORFTEXT000049180270'
ENDPOINT = '/api/rap-movements'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def semantic_version(registry):
    return 'rap-p174-' + sha(json.dumps(registry, sort_keys=True, ensure_ascii=False).encode())[:16]


def rows_by(rows, key):
    return {row[key]: row for row in rows}


class Validator:
    def __init__(self, base):
        self.base = base.rstrip('/')
        self.requests = 0
        self.assertions = 0
        self.cache = {}
        raw = REGISTRY.read_bytes()
        self.registry = json.loads(raw)
        self.registry_sha = sha(raw)
        self.api_version = semantic_version(self.registry)

    def check(self, condition, description):
        self.assertions += 1
        if not condition:
            raise AssertionError(description)

    def get(self, endpoint=ENDPOINT, **parameters):
        route = endpoint + ('?' + urlencode(parameters) if parameters else '')
        if route not in self.cache:
            self.requests += 1
            with urlopen(self.base + route, timeout=60) as response:
                self.check(response.status == 200, 'HTTP 200: ' + route)
                body = response.read()
                self.cache[route] = json.loads(body), dict(response.headers), body
        return self.cache[route]

    def query(self, **parameters):
        data = self.get(**parameters)[0]
        self.check(data['version'] == self.api_version, 'HTTP semantic version matches the reviewed registry')
        return data

    def check_item(self, item, original, indices=None, base=2025):
        for field, value in original.items():
            self.check(item.get(field) == value, 'Original RAP field retained: ' + original['id'] + '/' + field)
        signed = original['sign'] * original['amount_cents']
        adjusted = signed
        if indices is not None:
            adjusted = int((Decimal(signed) * Decimal(str(indices[str(base)])) /
                            Decimal(str(indices[str(original['year'])]))).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        self.check(item['status'] == 'published' and item['source_verified'], 'Reviewed RAP amount available')
        self.check(item['nominal_cents'] == signed and item['nominal'] == signed / 100, 'Signed nominal amount exact')
        self.check(item['value_cents'] == adjusted and item['value'] == adjusted / 100, 'Displayed amount and inflation conversion exact')
        self.check(item['citation']['url'] == '/api/download/' + original['source'] + '#page=' + str(original['page']), 'Exact PDF page citation')
        self.check('publication_date' not in item and 'effective_date' not in item, 'No invented publication or effective date')
        self.check(item['linked_act_relation'] == ('same_operation' if original['linked_act_id'] else None), 'Existing-act relationship is explicit')

    def check_unavailable(self, parameters):
        data = self.query(**parameters)
        self.check(data['count'] == 20 and len(data['items']) == 20, 'Programme observations retained for explanation of unavailable fine selection')
        self.check(all(row['status'] == 'detail_unavailable' and row['value'] is None and
                       row['value_cents'] is None and row['nominal'] is None and row['nominal_cents'] is None
                       for row in data['items']), 'Fine or thematic amount never allocated')
        self.check(data['evidence_scope']['grain'] == 'programme' and
                   data['evidence_scope']['applies_to_selection'] is False, 'Preserved evidence explicitly belongs to programme, not requested detail')
        self.check(rows_by(data['proofs'], 'row_id') == rows_by(self.registry['evidence_rows'], 'row_id'), 'Full source evidence unchanged despite unavailable allocation')

    def run(self, report):
        reg = self.registry
        self.check(len(reg['items']) == 38 and len(reg['evidence_rows']) == 20, 'Reviewed registry dimensions')
        counts = Counter(row['measure'] for row in reg['items'])
        self.check(counts == {'AE': 18, 'CP': 20}, '18 AE and 20 CP published observations')
        self.check(sum(cell['amount_cents'] is None for row in reg['evidence_rows'] for cell in row['cells']) == 122, '122 source blanks retained')
        bootstrap = self.get('/api/bootstrap')[0]
        self.check(bootstrap['meta']['fact_count'] == 120576 and bootstrap['meta']['source_count'] == 4280, 'No added canonical facts or corpus sources')
        self.check(bootstrap['meta']['data_version'] == DATA_VERSION, 'Canonical numeric data version unchanged')
        common = dict(start=2023, end=2025, budget='BG', scope='TA/174')
        by_measure = {}
        for measure in ('AE', 'CP'):
            data = self.query(**common, measure=measure)
            by_measure[measure] = data
            expected = rows_by([row for row in reg['items'] if row['measure'] == measure], 'id')
            actual = rows_by(data['items'], 'id')
            self.check(len(actual) == data['count'] == counts[measure], 'Exactly the expected RAP items, without duplicated totals')
            self.check(set(actual) == set(expected), 'Exact reviewed observation identities')
            for identifier, original in expected.items():
                self.check_item(actual[identifier], original)
            self.check(data['proofs'] == data['evidence_rows'], 'Proof alias preserves full evidence')
            self.check(rows_by(data['proofs'], 'row_id') == rows_by(reg['evidence_rows'], 'row_id'), 'All 20 original evidence rows unchanged')
            self.check(data['evidence_row_count'] == 20 and all(len(row['cells']) == 8 for row in data['proofs']), 'Eight original columns in every evidence row')
            self.check(sum(cell['amount_cents'] is None for row in data['proofs'] for cell in row['cells']) == 122, 'All 122 blanks remain null over HTTP')
            self.check(data['table_totals'] == reg['table_totals'], 'All 19 original table totals preserved separately')
            self.check(data['reconciliations'] == [row for row in reg['reconciliations'] if row['measure'] == measure], 'Exact source/canonical reconciliation evidence')
            self.check(all(row['verified'] and row['expected_sha256'] == row['catalog_sha256'] for row in data['source_checks']) and
                       len(data['source_checks']) == 3, 'All three PDF hashes confirmed against catalogue')
            self.check({(row['id'], row['sha256']) for row in data['sources']} == {(row['id'], row['sha256']) for row in reg['sources']}, 'Exactly the three expected existing sources')
            self.check(data['evidence_scope']['original_columns_preserved'] and data['evidence_scope']['applies_to_selection'], 'Evidence scope accurately identifies programme selection')
            self.check(data['notes'] == reg['limits'], 'Coverage and limitations delivered intact')

        for year in (2023, 2024, 2025):
            for measure in ('AE', 'CP'):
                data = self.query(start=year, end=year, budget='BG', scope='TA/174', measure=measure)
                expected = [row for row in reg['items'] if row['year'] == year and row['measure'] == measure]
                self.check({row['id'] for row in data['items']} == {row['id'] for row in expected}, 'Year/measure filter exact')
                self.check(all(row['year'] == year for row in data['proofs'] + data['table_totals'] + data['reconciliations']), 'Proofs and reconciliations follow selected year')
                self.check(len(data['source_checks']) == 1 and data['source_checks'][0]['verified'], 'Only selected year source checked')
        wide = self.query(start=2017, end=2026, budget='BG', scope='TA/174', measure='CP')
        self.check(wide['count'] == 20 and wide['years_without_integrated_rows'] == [2017, 2018, 2019, 2020, 2021, 2022, 2026], 'Uncovered years explicit, without fabricated rows')
        for scope in ('', 'TA'):
            ancestor = self.query(**dict(common, scope=scope), measure='CP')
            self.check(ancestor['items'] == by_measure['CP']['items'], 'Ancestor scope contains only the reviewed P174 subset')
        for params in [dict(common, scope='TA/203'), dict(common, budget='BA'),
                       dict(common, exclude=json.dumps(['TA/174'])), dict(common, exclude=json.dumps(['TA']))]:
            data = self.query(**params, measure='CP')
            self.check(data['count'] == 0 and not data['items'] and not data['proofs'], 'Outside programme or wholly excluded scope returns no observations')
        sibling = self.query(**common, measure='CP', exclude=json.dumps(['TA/203']))
        self.check(sibling['items'] == by_measure['CP']['items'], 'Excluding another programme leaves RAP observations unchanged')
        for parameters in [dict(common, measure='CP', scope='TA/174/02'),
                           dict(common, measure='CP', exclude=json.dumps(['TA/174/02'])),
                           dict(common, measure='CP', topic='maprimerenov', topic_mode='only'),
                           dict(common, measure='CP', topic='maprimerenov', topic_mode='without')]:
            self.check_unavailable(parameters)

        indices = bootstrap['meta']['indices']
        real = self.query(**common, measure='CP', constant=1, base=2025)
        original = rows_by(reg['items'], 'id')
        for item in real['items']:
            self.check_item(item, original[item['id']], indices=indices)
        self.check(real['proofs'] == by_measure['CP']['proofs'], 'Inflation never changes original proof amounts')
        self.check(real['selection_id'] != by_measure['CP']['selection_id'], 'Inflation selection fingerprint distinct')

        self.check(sha(EVENT_DATABASE.read_bytes()) == EVENT_SHA, 'Frozen previous event SQLite hash')
        with sqlite3.connect(EVENT_DATABASE.resolve().as_uri() + '?mode=ro', uri=True) as db:
            db.row_factory = sqlite3.Row
            original_events = [dict(row) for row in db.execute('SELECT * FROM events')]
            original_meta = {row['key']: json.loads(row['value']) for row in db.execute('SELECT * FROM meta')}
        self.check(len(original_events) == 186 and original_meta['version'] == EVENT_VERSION, 'Original register has only the established 186 observations')
        served_events = []
        for measure in ('AE', 'CP'):
            for budget, count in [('BG', 86), ('BA', 5), ('CCF', 2)]:
                expected_subset = [row for row in original_events if row['measure'] == measure and row['budget'] == budget]
                self.check(len(expected_subset) == count, 'Verified original event count by budget and measure')
                data = self.get('/api/events', start=2017, end=2026, budget=budget, measure=measure)[0]
                self.check(data['version'] == EVENT_VERSION and data['coverage'] == original_meta['coverage'], 'JORF register version and coverage unchanged')
                self.check(data['count'] == count, 'Original JORF observations for ' + budget + '/' + measure)
                served_events.extend(data['items'])
        actual_events = rows_by(served_events, 'event_id')
        expected_events = rows_by(original_events, 'event_id')
        self.check(len(actual_events) == 186 and set(actual_events) == set(expected_events), 'No RAP row inserted or double-counted in JORF register')
        for identifier, expected in expected_events.items():
            self.check({key: actual_events[identifier].get(key) for key in expected} == expected, 'Original JORF row byte-equivalent in fields: ' + identifier)
        linked = [row for measure in by_measure.values() for row in measure['items'] if row['linked_act_id']]
        self.check(len(linked) == 2, 'Only two links to the existing decree')
        for row in linked:
            event = actual_events[ACT_ID + '/174/' + row['measure']]
            self.check(row['linked_act_id'] == ACT_ID and row['sign'] == event['sign'] and
                       row['amount_cents'] == event['amount_cents'] and row['date'] == event['act_date'], 'RAP citation and existing event describe the same operation')
            self.check(row['date'] == '2024-02-21' and event['publication_date'] == '2024-02-22', 'Signature and publication remain distinct')

        exported, headers, payload = self.get(**common, measure='CP', download=1)
        self.check(exported == by_measure['CP'], 'JSON export preserves exact API result and complete evidence')
        disposition = next((value for key, value in headers.items() if key.lower() == 'content-disposition'), '')
        self.check('attachment' in disposition and 'nos-deniers-mouvements-rap.json' in disposition, 'JSON export download disposition')
        explorer = self.get('/api/explorer', **common, measure='CP')[0]
        self.check(explorer['stages']['LEGIS'] == 'Ajustements nets de crédits', 'Corrected shared LEGIS label')
        self.check(any('LFR' in note and 'décrets d’annulation' in note and 'reports' in note for note in explorer['notes']), 'Explanation preserves mixed legal/source categories and separates reports')
        self.check(explorer['data_version'] == DATA_VERSION, 'Explorer numeric data version unchanged')
        parents = json.loads((ROOT / 'reports/mouvements-rap-p174-20260910/parents.json').read_text(encoding='utf-8'))
        for annual in explorer['totals']:
            for stage in ('LFI', 'OUVERT', 'FDC', 'REPORT_ENTRANT', 'REGLEMENT', 'LEGIS'):
                expected = next(row for row in parents if (row['year'], row['measure'], row['stage']) == (annual['year'], 'CP', stage))
                self.check(annual[stage]['nominal_cents'] == expected['cents'], 'RAP observations do not add to canonical annual total')
        self.check(sha(REGISTRY.read_bytes()) == self.registry_sha, 'Registry unchanged during validation')
        self.check(sha(EVENT_DATABASE.read_bytes()) == EVENT_SHA, 'Original event snapshot unchanged during validation')
        report.update(passed=True, version=self.registry_sha, api_version=self.api_version,
                      observations=38, observations_by_measure=dict(counts), evidence_rows=20,
                      original_cells=160, preserved_null_cells=122, original_table_totals=19,
                      reconciliations=30, existing_event_count=186, existing_event_version=EVENT_VERSION,
                      existing_event_counts_per_measure={'BG': 86, 'BA': 5, 'CCF': 2},
                      existing_event_database_sha256=EVENT_SHA, existing_act_links_checked=2,
                      monthly_observations=4, nominal_and_constant_euros_checked=True,
                      exclusions_and_unavailable_detail_checked=True, events_kept_separate=True,
                      fact_count=120576, source_count=4280, data_version=DATA_VERSION,
                      export_json_bytes=len(payload), export_json_sha256=sha(payload),
                      legis_label='Ajustements nets de crédits')


def positive(value):
    result = int(value)
    if result <= 0:
        raise argparse.ArgumentTypeError('Use the positive count from the preceding completed test suite.')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--http', default='http://127.0.0.1:8552')
    parser.add_argument('--unit-tests', type=positive, required=True)
    args = parser.parse_args()
    report = dict(passed=False, started_at=datetime.now(timezone.utc).isoformat(), http_base=args.http,
                  unit_tests=args.unit_tests, unit_test_count_origin='Supplied after a separate completed suite',
                  performed_activation=False)
    validator = Validator(args.http)
    try:
        validator.run(report)
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        report.update(finished_at=datetime.now(timezone.utc).isoformat(), http_requests=validator.requests,
                      assertions=validator.assertions)
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(passed=True, report=str(REPORT), http_requests=validator.requests,
                          assertions=validator.assertions, observations=38), ensure_ascii=False))


if __name__ == '__main__':
    main()
