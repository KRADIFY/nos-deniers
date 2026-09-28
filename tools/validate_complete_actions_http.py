#!/usr/bin/env python3
"""Validate the already running complete Ecology action/subaction release.

Run only after the matching image and its unit suite have been verified.
--unit-tests records evidence supplied by the caller; this script never builds,
restarts, publishes or executes that unit suite itself.
"""
import argparse
import csv
import hashlib
import io
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from budget_service import action_details  # noqa: E402

REPORT = ROOT / 'reports/actions-completes-20260910/http-validation.json'
BASELINE = ROOT / 'deploy/update-20260910-ecologie-actions/release.json'
EXPECTED_DATA_VERSION = '0dd3cc2dc154bbdeb80b8d270c917963fdadee2f119a110544b6db0110b23344'
EXPECTED_PROGRAMS = ['113', '159', '174', '181', '203', '205', '217', '235', '345', '355', '380']


def signature(data):
    return {
        'data_version': data['data_version'],
        'calculation_version': data['calculation_version'],
        'totals': [
            {key: (value if key == 'year' else {field: value.get(field)
             for field in ('value', 'nominal_cents', 'status', 'sources')})
             for key, value in annual.items() if key == 'year' or key in data['stages']}
            for annual in data['totals']
        ],
    }


def parents_of(group):
    return group.get('parents') or [group['parent']]


def node_record(group, item, action=None):
    return dict(source=group['source'], program=group['program'],
                action=action['code'] if action else item['code'],
                subaction=item['code'] if action else '',
                page=item.get('page', group['page']), cents=item['euros'] * 100)


def node_path(row):
    return '/'.join(['TA', row['program'], row['action']] + ([row['subaction']] if row['subaction'] else []))


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

    def route(self, endpoint='/api/explorer', **params):
        return endpoint + '?' + urlencode(params)

    def explorer(self, **params):
        data = self.get(self.route(**params))
        self.check(data['data_version'] == EXPECTED_DATA_VERSION, 'Canonical data version unchanged')
        self.check(data['action_detail_version'] == self.action_version, 'HTTP registry matches reviewed local registry')
        self.check(data['topic_version'] == self.topic_version, 'HTTP MPR registry matches local file')
        return data

    def total(self, stage='EXEC', **params):
        data = self.explorer(**params)
        self.check(len(data['totals']) == 1, 'One requested annual total')
        return data['totals'][0][stage]

    def check_node(self, cell, group, item, grain, label):
        self.check(cell.get('nominal_cents') == item['euros'] * 100, label + ': nominal amount')
        self.check(cell['value'] == item['euros'], label + ': displayed euros')
        self.check(cell['status'] == 'ok' and cell['grain'] == grain, label + ': available at correct grain')
        self.check(cell['sources'] == [group['source']], label + ': source')
        self.check(cell.get('citations') == [{'source': group['source'], 'page': item.get('page', group['page'])}], label + ': exact physical page')
        self.check(cell['count'] == 1, label + ': one observation, no parent plus children')

    def signed_proof(self, label, params, stage, base_rows, removed):
        nominal = sum(r['cents'] for r in base_rows) - sum(r['cents'] for r in removed)
        cell = self.total(stage=stage, **params)
        self.check(cell.get('nominal_cents') == nominal and cell['status'] == 'ok', label + ': nominal subtraction')
        proof = self.get(self.route('/api/provenance', **params, year=params['start'], stage=stage))
        self.check(not proof['truncated'], label + ': complete provenance')
        self.check(proof['count'] == len(base_rows) + len(removed) == len(proof['rows']), label + ': exact proof row count')
        self.check(sum(r['cents'] for r in proof['rows']) == nominal, label + ': signed proof sum')
        remaining = list(proof['rows'])
        for row in base_rows:
            matches = [i for i, actual in enumerate(remaining)
                       if actual.get('operation', 'base') == 'base' and all(actual.get(k) == v for k, v in row.items())]
            self.check(len(matches) == 1, label + ': unchanged canonical/published base row')
            remaining.pop(matches[0])
        for row in removed:
            expected = dict(row, cents=-row['cents'], operation='subtract_action')
            matches = [i for i, actual in enumerate(remaining) if all(actual.get(k) == v for k, v in expected.items())]
            self.check(len(matches) == 1, label + ': exact signed excluded node with citation')
            remaining.pop(matches[0])
        self.check(not remaining, label + ': no duplicate parent/action/subaction in proof')
        if params.get('constant'):
            data = self.explorer(**params)
            indices = data['inflation']['indices']
            converted = int((Decimal(nominal) * Decimal(str(indices[str(params['base'])])) /
                             Decimal(str(indices[str(params['start'])]))).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
            self.check(cell['value'] == converted / 100, label + ': exclusions before annual IPC and cent rounding')
        return dict(nominal_cents=nominal, displayed_euros=cell['value'], proof_rows=proof['count'],
                    citations=cell.get('citations', []))

    def run(self, report):
        registry, self.action_version = action_details.registry()
        groups = registry['groups']
        self.topic_version = hashlib.sha256((ROOT / 'budget_service/data/maprimerenov.json').read_bytes()).hexdigest()
        actions = sum(len(g['actions']) for g in groups)
        subactions = sum(len(a.get('subactions', [])) for g in groups for a in g['actions'])
        self.check(len(groups) == 115, '115 reviewed groups')
        self.check(actions == 780 and subactions == 240, '780 actions and 240 subactions')
        self.check(sorted({g['program'] for g in groups}) == EXPECTED_PROGRAMS, 'Eleven reviewed programmes')
        self.check(len({tuple(g[k] for k in ('year', 'stage', 'measure', 'budget', 'mission', 'program')) for g in groups}) == 115, 'Unique reviewed group keys')
        debt_groups = [g for g in groups if g['program'] == '355']
        self.check(len(debt_groups) == 4 and all(g['year'] == 2023 and g['mission'] == 'TA' for g in debt_groups), 'P355 only in its reviewed TA2023 perimeter')
        meta = self.get('/api/bootstrap')['meta']
        self.check(meta['fact_count'] == 120576, '120576 original facts preserved')
        self.check(meta['source_count'] == 4280, '4280 public references preserved')
        self.check(meta['data_version'] == EXPECTED_DATA_VERSION, 'Bootstrap data version preserved')
        report.update(groups=len(groups), actions=actions, subactions=subactions, observations=actions + subactions,
                      programs=EXPECTED_PROGRAMS, fact_count=meta['fact_count'], source_count=meta['source_count'],
                      data_version=meta['data_version'], action_detail_version=self.action_version, topic_version=self.topic_version)
        for source_id, sha in sorted({(g['source'], g['sha256']) for g in groups}):
            self.check(self.get('/api/source/' + source_id)['sha256'] == sha, 'Published source hash: ' + source_id)

        checked_actions = checked_subactions = 0
        for group in groups:
            params = dict(start=group['year'], end=group['year'], measure=group['measure'], budget=group['budget'],
                          scope=group['mission'] + '/' + group['program'])
            data = self.explorer(**params)
            stage = group['stage']
            cell = data['totals'][0][stage]
            parents = parents_of(group)
            label = f"P{group['program']} {group['year']} {group['measure']} {stage}"
            nominal = sum(r['cents'] for r in parents)
            self.check(cell.get('nominal_cents') == nominal and cell['value'] == nominal / 100, label + ': canonical programme total')
            self.check(cell['status'] == 'ok' and cell['grain'] == 'programme', label + ': programme grain')
            self.check(cell['count'] == len(parents), label + ': original title row count')
            self.check(cell['sources'] == sorted({r['source'] for r in parents}), label + ': original sources')
            self.check(cell['approximate'] == any(r.get('approximate', 0) for r in parents), label + ': original precision flag')
            rows = {r['id']: r for r in data['rows']}
            self.check(len(rows) == len(data['rows']), label + ': unique navigation rows')
            for action in group['actions']:
                path = params['scope'] + '/' + action['code']
                self.check(path in rows, label + ': action visible ' + action['code'])
                self.check_node(rows[path]['series'][0][stage], group, action, 'action', label + '/' + action['code'])
                checked_actions += 1
                if not action.get('subactions'):
                    continue
                action_data = self.explorer(**dict(params, scope=path))
                self.check_node(action_data['totals'][0][stage], group, action, 'action', label + ': published action total above subactions')
                children = {r['id']: r for r in action_data['rows']}
                self.check(len(children) == len(action_data['rows']), label + ': unique subaction navigation')
                for child in action['subactions']:
                    child_path = path + '/' + child['code']
                    self.check(child_path in children, label + ': subaction visible ' + child_path)
                    self.check_node(children[child_path]['series'][0][stage], group, child, 'sous-action', label + '/' + child_path)
                    direct = self.total(stage=stage, **dict(params, scope=child_path))
                    self.check_node(direct, group, child, 'sous-action', label + ': selected subaction ' + child_path)
                    checked_subactions += 1
        self.check((checked_actions, checked_subactions) == (780, 240), 'Every reviewed node checked')
        report.update(checked_action_observations=checked_actions, checked_subaction_observations=checked_subactions,
                      canonical_programme_totals_checked=len(groups))

        baseline = json.loads(BASELINE.read_text(encoding='utf-8'))
        self.check(baseline['release'] == '20260910-ecologie-actions', 'Correct frozen predecessor')
        self.check(len(baseline['cases']) == 17, 'Exactly 17 frozen baseline cases')
        checked_cases = []
        for case in baseline['cases']:
            self.check(signature(self.get('/api/explorer?' + case['query'])) == case['expected'],
                       'Strict frozen baseline preserved: ' + case['name'])
            checked_cases.append(case['name'])
        report.update(baseline_cases_checked=checked_cases, baseline_comparison='strict equality; no skipped cases or replaced cells')

        group = next(g for g in groups if (g['program'], g['year'], g['measure'], g['stage']) == ('345', 2023, 'AE', 'EXEC'))
        action17 = next(a for a in group['actions'] if a['code'] == '17')
        child03 = next(a for a in action17['subactions'] if a['code'] == '03')
        self.check(child03['euros'] < 0, 'Official negative P345/17/03 EXEC AE2023')
        negative_node = node_record(group, child03, action17)
        params = dict(start=2023, end=2023, measure='AE', budget='BG', scope='TA/345')
        negative = self.total(**dict(params, scope='TA/345/17/03'))
        self.check(negative['nominal_cents'] == negative_node['cents'] and negative['status'] == 'ok', 'Negative subaction displayed without clamping')
        other_action = next(a for a in group['actions'] if a['code'] != '17' and a['euros'] != 0)
        other_node = node_record(group, other_action)
        mixed = dict(params, exclude=json.dumps([node_path(other_node), node_path(negative_node)]))
        report['mixed_action_subaction_exclusion'] = self.signed_proof('Mixed action/subaction exclusion', mixed, 'EXEC', parents_of(group), [other_node, negative_node])
        report['mixed_exclusion_constant_euros'] = self.signed_proof('Mixed exclusions in constant euros', dict(mixed, constant=1, base=2025), 'EXEC', parents_of(group), [other_node, negative_node])
        report['negative_subaction_2023_ae'] = dict(path=node_path(negative_node), cents=negative_node['cents'], page=negative_node['page'])

        all_children = ['TA/345/17/' + a['code'] for a in action17['subactions']]
        grouped = dict(params, exclude=json.dumps(all_children))
        action_node = node_record(group, action17)
        report['complete_subaction_branch_exclusion'] = self.signed_proof('All subactions collapse to their published action total', grouped, 'EXEC', parents_of(group), [action_node])
        explicit = self.total(**dict(params, exclude=json.dumps(['TA/345/17'])))
        self.check(explicit['nominal_cents'] == report['complete_subaction_branch_exclusion']['nominal_cents'], 'Grouped subactions equal whole action exclusion')
        fully = self.total(**dict(grouped, scope='TA/345/17'))
        self.check(fully['status'] == 'excluded' and fully['value'] == 0 and fully['count'] == 0, 'Entire action excluded without rounding residue')
        leaves = ['TA/345/' + a['code'] + '/' + child['code'] for a in group['actions'] for child in a.get('subactions', [])]
        leaves += ['TA/345/' + a['code'] for a in group['actions'] if not a.get('subactions')]
        fully = self.total(**dict(params, exclude=json.dumps(leaves)))
        self.check(fully['status'] == 'excluded' and fully['value'] == 0 and fully['count'] == 0, 'All branches exclude entire programme, no parent/child residual')
        redundant = self.total(**dict(params, exclude=json.dumps(['TA/345/17', 'TA/345/17/03', 'TA/345/17/03'])))
        self.check(redundant['nominal_cents'] == explicit['nominal_cents'], 'Duplicate and nested exclusion only subtracted once')
        missing = self.total(**dict(params, scope='TA/345/17/99'))
        self.check(missing['status'] == 'detail_unavailable' and missing['value'] is None, 'Unknown subaction stays unavailable')

        multi = next(g for g in groups if (g['program'], g['year'], g['measure'], g['stage']) == ('217', 2024, 'CP', 'EXEC'))
        action07 = next(a for a in multi['actions'] if a['code'] == '07')
        multi_params = dict(start=2024, end=2024, measure='CP', budget='BG', scope='TA/217', exclude=json.dumps(['TA/217/07']))
        self.check(len(parents_of(multi)) == 2 and action07['euros'] == 875409404, 'Known two-title P217 fixture')
        report['multi_parent_exclusion'] = self.signed_proof('P217 two parents less action07', multi_params, 'EXEC', parents_of(multi), [node_record(multi, action07)])
        self.check(report['multi_parent_exclusion']['nominal_cents'] == 220648815692 and report['multi_parent_exclusion']['proof_rows'] == 3, 'Two parents plus one subtraction, exact remainder')
        report['multi_parent_constant_euros'] = self.signed_proof('P217 exclusion before IPC', dict(multi_params, constant=1, base=2025), 'EXEC', parents_of(multi), [node_record(multi, action07)])

        divergent = self.total(start=2023, end=2023, measure='AE', scope='TA/203/41')
        self.check(divergent['status'] == 'detail_unavailable' and divergent['value'] is None, 'Previously divergent P203 group remains unavailable')
        zero = self.total(start=2025, end=2025, measure='AE', scope='TA/203/53')
        self.check(zero['value'] == 0 and zero['status'] == 'ok', 'Published zero remains available')
        export_params = dict(params, scope='TA/345/17/03')
        csv_bytes = self.raw(self.route('/api/export', **export_params))
        csv_rows = list(csv.DictReader(io.StringIO(csv_bytes.decode('utf-8-sig')), delimiter=';'))
        totals = [r for r in csv_rows if r['Type de ligne'] == 'Total du périmètre' and r['Étape'] == 'Consommé']
        self.check(len(totals) == 1, 'One negative subaction CSV total')
        self.check(Decimal(totals[0]['Montant EUR'].replace(',', '.')) == Decimal(child03['euros']), 'CSV preserves negative subaction')
        source_url = self.get('/api/source/' + group['source'])['url']
        self.check(totals[0]['Sources officielles'].split() == [source_url + '#page=' + str(negative_node['page'])], 'CSV exact subaction PDF page')
        report['subaction_csv_export'] = dict(bytes=len(csv_bytes), sha256=hashlib.sha256(csv_bytes).hexdigest(), page=negative_node['page'], euros=child03['euros'])

        action_details.registry.cache_clear()
        self.check(action_details.registry()[1] == self.action_version, 'Registry unchanged during validation')
        self.check(hashlib.sha256((ROOT / 'budget_service/data/maprimerenov.json').read_bytes()).hexdigest() == self.topic_version, 'MPR registry unchanged during validation')
        report['passed'] = True


def positive_integer(value):
    count = int(value)
    if count <= 0:
        raise argparse.ArgumentTypeError('Provide the positive count from the completed unit-test suite.')
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--http', default='http://127.0.0.1:8552')
    parser.add_argument('--unit-tests', type=positive_integer, required=True,
                        help='Passed count supplied from the separate, completed unit suite')
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
        report.update(finished_at=datetime.now(timezone.utc).isoformat(), http_requests=validator.requests, assertions=validator.assertions)
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(passed=True, report=str(REPORT), groups=115, observations=1020,
                          http_requests=validator.requests, assertions=validator.assertions), ensure_ascii=False))


if __name__ == '__main__':
    main()
