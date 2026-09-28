#!/usr/bin/env python3
"""Check the reviewed Ecology action release through its real read-only HTTP API.

Run only after building, testing and starting the matching application image::

    python tools/validate_ecology_actions_http.py --unit-tests 108

The test count is supplied evidence from the preceding isolated unit-test run;
this script does not build, restart, deploy, or run that suite itself.
"""
import argparse
import csv
import hashlib
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlencode
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from budget_service import action_details  # noqa: E402

REPORT = ROOT / 'reports/actions-ecologie-complet-20260910/http-validation.json'
BASELINE = ROOT / 'deploy/update-20260910-fdc2023/release.json'
EXPECTED_DATA_VERSION = '0dd3cc2dc154bbdeb80b8d270c917963fdadee2f119a110544b6db0110b23344'
EXPECTED_PROGRAMS = ['113', '159', '174', '203', '205', '380']
RAP_2024 = '113330a8d3bb90c96604'


def signature(data):
    return {
        'data_version': data['data_version'],
        'calculation_version': data['calculation_version'],
        'totals': [
            {key: (value if key == 'year' else {
                field: value.get(field)
                for field in ('value', 'nominal_cents', 'status', 'sources')
            }) for key, value in annual.items()
             if key == 'year' or key in data['stages']}
            for annual in data['totals']
        ],
    }


class Validator:
    def __init__(self, base):
        self.base = base.rstrip('/')
        self.requests = 0
        self.assertions = 0
        self.cache = {}

    def check(self, condition, label):
        self.assertions += 1
        if not condition:
            raise AssertionError(label)

    def raw(self, route):
        self.requests += 1
        with urlopen(self.base + route, timeout=60) as response:
            self.check(response.status == 200, 'HTTP 200: ' + route)
            return response.read()

    def get(self, route):
        if route not in self.cache:
            self.cache[route] = json.loads(self.raw(route))
        return self.cache[route]

    def route(self, endpoint='/api/explorer', **parameters):
        return endpoint + '?' + urlencode(parameters)

    def explorer(self, **parameters):
        data = self.get(self.route(**parameters))
        self.check(data['data_version'] == EXPECTED_DATA_VERSION, 'Canonical data version unchanged')
        self.check(data['action_detail_version'] == self.action_version, 'HTTP action registry matches local reviewed file')
        self.check(data['topic_version'] == self.topic_version, 'HTTP MPR registry matches local reviewed file')
        return data

    def total(self, stage='EXEC', **parameters):
        data = self.explorer(**parameters)
        self.check(len(data['totals']) == 1, 'Exactly one requested annual total')
        return data['totals'][0][stage]

    def signed_proof(self, parameters, expected_cents, operations):
        proof = self.get(self.route('/api/provenance', **parameters, year=2024, stage='EXEC'))
        self.check(not proof['truncated'], 'Signed provenance is complete')
        self.check(proof['count'] == len(proof['rows']), 'All provenance rows returned')
        self.check(sum(row['cents'] for row in proof['rows']) == expected_cents, 'Signed nominal proof equals displayed nominal amount')
        self.check({row['operation'] for row in proof['rows']} == operations, 'Separate base, action exclusion and MPR subtraction')
        self.check(all(row['cents'] <= 0 for row in proof['rows'] if row['operation'].startswith('subtract')), 'Subtracted amounts retain negative sign')
        self.check({row['page'] for row in proof['rows'] if row['source'] == RAP_2024} == {426, 446}, 'Both RAP pages retained in signed proof')

    def run(self, report):
        registry, self.action_version = action_details.registry()
        groups = registry['groups']
        self.topic_version = hashlib.sha256((ROOT / 'budget_service/data/maprimerenov.json').read_bytes()).hexdigest()
        report.update(action_detail_version=self.action_version, topic_version=self.topic_version)
        self.check(len(groups) == 71, '71 reviewed groups')
        self.check(sum(len(group['actions']) for group in groups) == 408, '408 reviewed action observations')
        programs = sorted({group['program'] for group in groups})
        self.check(programs == EXPECTED_PROGRAMS, 'Six expected Ecology programmes')
        meta = self.get('/api/bootstrap')['meta']
        self.check(meta['fact_count'] == 120576, '120576 original facts')
        self.check(meta['source_count'] == 4280, '4280 public references')
        self.check(meta['data_version'] == EXPECTED_DATA_VERSION, 'Bootstrap canonical data version unchanged')
        self.check(meta['application_version'] == '0.3', 'Application version 0.3')
        report.update(data_version=meta['data_version'], fact_count=meta['fact_count'],
                      source_count=meta['source_count'], observations=408, groups=71, programs=programs)
        for source_id, sha in sorted({(group['source'], group['sha256']) for group in groups}):
            source = self.get('/api/source/' + source_id)
            self.check(source['sha256'] == sha, 'Published RAP source hash: ' + source_id)

        checked_observations = 0
        for group in groups:
            params = dict(start=group['year'], end=group['year'], measure=group['measure'],
                          budget=group['budget'], scope=group['mission'] + '/' + group['program'])
            data = self.explorer(**params)
            stage = group['stage']
            parent = data['totals'][0][stage]
            label = f"P{group['program']} {group['year']} {group['measure']} {stage}"
            self.check(parent['nominal_cents'] == group['parent']['cents'], label + ': authoritative programme total unchanged')
            self.check(parent['value'] == group['parent']['cents'] / 100, label + ': programme euro display')
            self.check(parent['status'] == 'ok', label + ': programme available')
            self.check(parent['count'] == 1, label + ': actions not added to canonical parent')
            self.check(parent['sources'] == [group['parent']['source']], label + ': canonical source retained')
            by_path = {row['id']: row for row in data['rows']}
            self.check(len(by_path) == len(data['rows']), label + ': unique navigation rows')
            for action in group['actions']:
                path = params['scope'] + '/' + action['code']
                self.check(path in by_path, label + ': action visible ' + action['code'])
                cell = by_path[path]['series'][0][stage]
                page = action.get('page', group['page'])
                self.check(cell['nominal_cents'] == action['euros'] * 100, label + ': published action amount ' + action['code'])
                self.check(cell['value'] == action['euros'], label + ': displayed action euros ' + action['code'])
                self.check(cell['status'] == 'ok' and cell['grain'] == 'action', label + ': action availability and grain ' + action['code'])
                self.check(cell['sources'] == [group['source']], label + ': action RAP source ' + action['code'])
                self.check(cell['citations'] == [{'source': group['source'], 'page': page}], label + ': physical page for action ' + action['code'])
                self.check(cell['count'] == 1, label + ': one published observation per action ' + action['code'])
                checked_observations += 1
        report['checked_action_observations'] = checked_observations
        report['canonical_programme_totals_checked'] = len(groups)

        baseline = json.loads(BASELINE.read_text(encoding='utf-8'))
        self.check(baseline['data_version'] == EXPECTED_DATA_VERSION, 'Frozen public baseline data version')
        checked_cases, changed_cells, skipped = [], [], []
        for case in baseline['cases']:
            query = parse_qs(case['query'])
            if query.get('topic', [''])[0]:
                skipped.append(case['name'])
                continue
            actual = signature(self.get('/api/explorer?' + case['query']))
            expected = json.loads(json.dumps(case['expected']))
            if case['name'] == 'fdc2023-action':
                # This old unavailable P203 action is intentionally opened by this release.
                # Only LFI and EXEC change; every other stage retains its previous signature.
                for stage in ('LFI', 'EXEC'):
                    group = next(g for g in groups if (g['program'], g['year'], g['measure'], g['stage']) == ('203', 2023, 'CP', stage))
                    action = next(a for a in group['actions'] if a['code'] == '41')
                    now = actual['totals'][0][stage]
                    self.check(now == dict(value=action['euros'], nominal_cents=action['euros'] * 100,
                                           status='ok', sources=[group['source']]), 'Intentional P203/41 availability: ' + stage)
                    changed_cells.append(dict(case=case['name'], year=2023, stage=stage,
                                              previous=expected['totals'][0][stage], current=now))
                    expected['totals'][0][stage] = now
            self.check(actual == expected, 'Frozen non-thematic case preserved: ' + case['name'])
            checked_cases.append(case['name'])
        report.update(baseline_cases_checked=checked_cases, intentional_new_action_cells=changed_cells,
                      historical_topic_cases_superseded_by_cited_mpr_checks=skipped)

        unavailable = self.total(start=2023, end=2023, measure='AE', scope='TA/203/41')
        self.check(unavailable['status'] == 'detail_unavailable' and unavailable['value'] is None,
                   'P203 EXEC AE2023 divergent group stays unavailable')
        self.check(not any((g['program'], g['year'], g['measure'], g['stage']) == ('203', 2023, 'AE', 'EXEC') for g in groups), 'Divergent group absent from reviewed registry')
        negative = self.total(start=2025, end=2025, measure='AE', scope='TA/203/51')
        self.check(negative['nominal_cents'] == -943137600 and negative['status'] == 'ok', 'Published negative AE2025 action51 retained')
        zero = self.total(start=2025, end=2025, measure='AE', scope='TA/203/53')
        self.check(zero['nominal_cents'] == 0 and zero['value'] == 0 and zero['status'] == 'ok', 'Published zero action53 available, not missing')
        report['p203_edge_cases'] = dict(divergent_2023_ae='detail_unavailable', action51_2025_ae_cents=-943137600, action53_2025_ae_cents=0)

        mpr = dict(start=2024, end=2024, measure='CP', budget='BG', scope='TA/174/02',
                   topic='maprimerenov', topic_mode='without')
        remainder = self.total(**mpr)
        self.check(remainder['nominal_cents'] == 77613622600 and remainder['status'] == 'ok', 'Action02 CP2024 without MPR')
        expected_pages = [{'source': RAP_2024, 'page': 426}, {'source': RAP_2024, 'page': 446}]
        self.check(remainder['citations'] == expected_pages, 'Same PDF, two independent citations retained')
        self.signed_proof(mpr, 77613622600, {'base', 'subtract'})
        compound = dict(mpr, scope='TA/174', exclude=json.dumps(['TA/174/03']))
        result = self.total(**compound)
        self.check(result['nominal_cents'] == 119632564097 and result['status'] == 'ok', 'P174 minus action03 minus MPR')
        self.signed_proof(compound, 119632564097, {'base', 'subtract_action', 'subtract'})
        real_params = dict(compound, constant=1, base=2025)
        real = self.total(**real_params)
        self.check(real['nominal_cents'] == 119632564097 and real['value'] == 1207555910.94 and real['status'] == 'ok', 'Compound exclusion before inflation conversion')
        self.check(real['citations'] == expected_pages, 'Constant-euro cell keeps both nominal source pages')
        self.signed_proof(real_params, 119632564097, {'base', 'subtract_action', 'subtract'})
        report.update(mpr_remainder_cents=77613622600, compound_exclusion_cents=119632564097,
                      compound_exclusion_euros_2025=1207555910.94, signed_nominal_provenance_checked=True)

        from openpyxl import load_workbook
        xlsx_bytes = self.raw(self.route('/api/export.xlsx', **mpr))
        workbook = load_workbook(io.BytesIO(xlsx_bytes), read_only=True, data_only=True)
        try:
            values = list(workbook['Crédits'].values)
            credit_rows = [dict(zip(values[0], row)) for row in values[1:]]
            matches = [row for row in credit_rows if row['Type'] == 'Total' and row['Étape'] == 'Consommé']
            self.check(len(matches) == 1, 'Single EXEC total in XLSX')
            exported = matches[0]
            self.check(exported['Montant EUR'] == 776136226 and exported['Statut'] == 'ok', 'XLSX amount/status match explorer')
            for page in (426, 446):
                self.check(f'{RAP_2024} · PDF p. {page}' in exported['Pages sources'], 'XLSX explicit source page ' + str(page))
            values = list(workbook['Sources'].values)
            source_rows = [dict(zip(values[0], row)) for row in values[1:]]
            rap_source = self.get('/api/source/' + RAP_2024)
            self.check(any(row['Identifiant'] == RAP_2024 and row['URL'] == rap_source['url'] for row in source_rows), 'XLSX Sources includes matching shared PDF URL')
        finally:
            workbook.close()
        csv_bytes = self.raw(self.route('/api/export', **mpr))
        rows = list(csv.DictReader(io.StringIO(csv_bytes.decode('utf-8-sig')), delimiter=';'))
        matches = [row for row in rows if row['Type de ligne'] == 'Total du périmètre' and row['Étape'] == 'Consommé']
        self.check(len(matches) == 1, 'Single EXEC total in CSV')
        links = matches[0]['Sources officielles'].split()
        self.check(links == [rap_source['url'] + '#page=426', rap_source['url'] + '#page=446'], 'CSV contains both exact page links for same PDF')
        report['exports'] = dict(xlsx_bytes=len(xlsx_bytes), xlsx_sha256=hashlib.sha256(xlsx_bytes).hexdigest(),
                                 xlsx_source_pages=[426, 446], xlsx_shared_pdf_url_verified=True,
                                 csv_bytes=len(csv_bytes), csv_sha256=hashlib.sha256(csv_bytes).hexdigest(),
                                 csv_distinct_page_links=links,
                                 note='XLSX lists the two page references and the shared source URL; CSV contains both #page links.')
        # Do not certify a registry that changed during this validation.
        action_details.registry.cache_clear()
        self.check(action_details.registry()[1] == self.action_version, 'Action registry unchanged during HTTP checks')
        self.check(hashlib.sha256((ROOT / 'budget_service/data/maprimerenov.json').read_bytes()).hexdigest() == self.topic_version, 'MPR registry unchanged during HTTP checks')
        report['passed'] = True


def positive_integer(value):
    count = int(value)
    if count <= 0:
        raise argparse.ArgumentTypeError('Provide the positive count from the completed unit-test run.')
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--http', default='http://127.0.0.1:8552', help='Already running matching application')
    parser.add_argument('--unit-tests', type=positive_integer, required=True,
                        help='Number passed in the preceding unit-test run; not run by this script')
    args = parser.parse_args()
    report = dict(passed=False, started_at=datetime.now(timezone.utc).isoformat(), http_base=args.http,
                  unit_tests=args.unit_tests, unit_test_count_origin='Supplied by caller after separate completed suite',
                  performed_activation=False)
    validator = Validator(args.http)
    try:
        validator.run(report)
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        report.update(finished_at=datetime.now(timezone.utc).isoformat(),
                      http_requests=validator.requests, assertions=validator.assertions)
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(passed=True, report=str(REPORT), observations=408, groups=71,
                          http_requests=validator.requests, assertions=validator.assertions), ensure_ascii=False))


if __name__ == '__main__':
    main()
