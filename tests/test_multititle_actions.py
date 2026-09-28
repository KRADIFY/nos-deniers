import copy
import json
import unittest
from unittest.mock import patch
from budget_service import action_details
from budget_service.api import cell, parameters


class SourceDB:
    def execute(self, sql, args):
        return self

    def fetchone(self):
        return (json.dumps({'sha256': 'reviewed-pdf'}),)


class MultiTitleActionTests(unittest.TestCase):
    def setUp(self):
        parent = dict(year=2024, stage='EXEC', measure='CP', budget='BG', mission='TA',
                      mission_label='Écologie', program='181', program_label='Prévention',
                      action='', action_label='', subaction='', subaction_label='', category='',
                      title='2', cents=6001, source='csv-t2', line=12, field='consomme', approximate=0)
        self.parents = [parent, dict(parent, title='HT2', cents=4000, source='csv-ht2', line=13)]
        self.group = {k: parent[k] for k in ('year', 'stage', 'measure', 'budget', 'mission', 'program')}
        self.group.update(parents=self.parents, source='rap', sha256='reviewed-pdf', page=24,published_total_euros=100,
                          actions=[dict(code='01', label='Action A', euros=70, page=24),
                                   dict(code='02', label='Action B', euros=30, page=25)])
        self.mock = patch.object(action_details, 'registry', return_value=({'groups': [self.group]}, 'test-version'))
        self.mock.start()
        self.addCleanup(self.mock.stop)

    def records(self, parents=None):
        return action_details.attach(copy.deepcopy(self.parents if parents is None else parents), SourceDB())

    def result(self, records, scope='TA/181', excluded=(), **options):
        return cell(records, scope, 2024, 'EXEC', dict(parameters({}), exclude=list(excluded), **options),
                    {2024: '98', 2025: '100'})

    def test_programme_and_mission_keep_all_original_title_rows(self):
        for parents in (self.parents, list(reversed(self.parents))):
            records = self.records(parents)
            for scope in ('', 'TA', 'TA/181'):
                actual = self.result(records, scope)
                self.assertEqual(actual, self.result(copy.deepcopy(parents), scope))
                proof = action_details.proofs(action_details.resolve(records, scope, []))
                self.assertEqual(proof, parents)
            self.assertEqual(len(list(action_details.navigation(records))), 4)

    def test_action_total_not_counted_once_per_title(self):
        records = self.records()
        result = self.result(records, 'TA/181/01')
        self.assertEqual(result['nominal_cents'], 7000)
        self.assertEqual(result['sources'], ['rap'])
        self.assertEqual(result['count'], 1)
        proof = action_details.proofs(action_details.resolve(records, 'TA/181/01', []))
        self.assertEqual(len(proof), 1)
        self.assertEqual(proof[0]['cents'], 7000)
        self.assertEqual(proof[0]['page'], 24)

    def test_exclusion_keeps_both_original_proofs_and_one_subtraction(self):
        records = self.records(list(reversed(self.parents)))
        result = self.result(records, excluded=['TA/181/01'])
        self.assertEqual(result['nominal_cents'], 3001)
        self.assertEqual(result['sources'], ['csv-ht2', 'csv-t2', 'rap'])
        proof = action_details.proofs(action_details.resolve(records, 'TA/181', ['TA/181/01']))
        self.assertEqual(len(proof), 3)
        self.assertEqual(sum(r['cents'] for r in proof), 3001)
        self.assertEqual(proof[-1]['operation'], 'subtract_action')
        self.assertEqual(proof[-1]['cents'], -7000)
        self.assertFalse(any(k.startswith('_') for r in proof for k in r))

    def test_full_exclusion_removes_both_titles_and_rounding_residual(self):
        records = self.records()
        excluded = ['TA/181/01', 'TA/181/02']
        result = self.result(records, excluded=excluded)
        self.assertEqual(result['status'], 'excluded')
        self.assertEqual(result['value'], 0)
        other = dict(self.parents[0], program='203', cents=12345)
        result = self.result(records + [other], 'TA', excluded=excluded)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['nominal_cents'], 12345)

    def test_missing_changed_or_duplicate_title_disables_detail(self):
        variants = [self.parents[:1], [self.parents[0], dict(self.parents[1], cents=4001)],
                    self.parents + [self.parents[0]], [self.parents[0], self.parents[0]]]
        for parents in variants:
            records = self.records(parents)
            self.assertTrue(all('_action_details' not in r for r in records))
            self.assertEqual(self.result(records, 'TA/181/01')['status'], 'detail_unavailable')

    def test_unknown_action_or_subaction_is_never_allocated(self):
        records = self.records()
        for scope, excluded in [('TA/181/99', []), ('TA/181/01/01', []), ('TA/181', ['TA/181/01/01'])]:
            result = self.result(records, scope, excluded=excluded)
            self.assertEqual(result['status'], 'detail_unavailable')
            self.assertIsNone(result['value'])

    def test_inflation_follows_combined_subtraction(self):
        from budget_service.model import constant_cents
        result = self.result(self.records(), excluded=['TA/181/01'], constant=True, base=2025)
        self.assertEqual(result['nominal_cents'], 3001)
        self.assertEqual(result['value'], constant_cents(3001, 2024, 2025, {2024: '98', 2025: '100'}) / 100)


if __name__ == '__main__':
    unittest.main()
