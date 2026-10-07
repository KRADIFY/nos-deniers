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


class SubactionDetailTests(unittest.TestCase):
    def setUp(self):
        self.parent = dict(year=2024, stage='EXEC', measure='CP', budget='BG', mission='TA',
                           mission_label='Écologie', program='345', program_label='Énergie',
                           action='', action_label='', subaction='', subaction_label='', category='',
                           title='HT2', cents=10001, source='csv', line=12, field='consomme', approximate=0)
        group = {k: self.parent[k] for k in ('year', 'stage', 'measure', 'budget', 'mission', 'program')}
        group.update(parents=[self.parent], source='rap', sha256='reviewed-pdf', page=24,published_total_euros=100,
                     actions=[dict(code='01', label='Action A', euros=70, page=24,
                                   subactions=[dict(code='01', label='Sous-action positive', euros=75, page=24),
                                               dict(code='02', label='Sous-action négative', euros=-5, page=25)]),
                              dict(code='02', label='Action B', euros=30, page=25)])
        self.mock = patch.object(action_details, 'registry', return_value=({'groups': [group]}, 'test-version'))
        self.mock.start()
        self.addCleanup(self.mock.stop)
        self.records = action_details.attach([copy.deepcopy(self.parent)], SourceDB())

    def result(self, scope='TA/345', excluded=(), **options):
        return cell(self.records, scope, 2024, 'EXEC', dict(parameters({}), exclude=list(excluded), **options),
                    {2024: '98', 2025: '100'})

    def test_totals_never_add_parent_actions_and_subactions(self):
        self.assertEqual(self.result()['nominal_cents'], 10001)
        self.assertEqual(self.result('TA/345/01')['nominal_cents'], 7000)
        self.assertEqual(self.result('TA/345/01/01')['nominal_cents'], 7500)
        value = self.result('TA/345/01/02')
        self.assertEqual(value['nominal_cents'], -500)
        self.assertEqual(value['grain'], 'sous-action')
        self.assertEqual(value['citations'], [{'source': 'rap', 'page': 25}])
        self.assertEqual(len(list(action_details.navigation(self.records))), 5)

    def test_negative_subaction_exclusion_adds_back_its_negative_value(self):
        self.assertEqual(self.result(excluded=['TA/345/01/02'])['nominal_cents'], 10501)
        self.assertEqual(self.result('TA/345/01', excluded=['TA/345/01/02'])['nominal_cents'], 7500)
        proof = action_details.proofs(action_details.resolve(self.records, 'TA/345', ['TA/345/01/02']))
        self.assertEqual([r['cents'] for r in proof], [10001, 500])
        self.assertEqual(proof[1]['operation'], 'subtract_action')
        self.assertEqual(proof[1]['subaction'], '02')

    def test_complete_subaction_exclusion_collapses_to_published_action(self):
        excluded = ['TA/345/01/01', 'TA/345/01/02']
        value = self.result(excluded=excluded)
        self.assertEqual(value['nominal_cents'], 3001)
        proof = action_details.proofs(action_details.resolve(self.records, 'TA/345', excluded))
        self.assertEqual(len(proof), 2)
        self.assertEqual(proof[1]['action'], '01')
        self.assertEqual(proof[1]['subaction'], '')
        self.assertEqual(proof[1]['cents'], -7000)
        self.assertEqual(self.result('TA/345/01', excluded=excluded)['status'], 'excluded')

    def test_redundant_ancestor_and_descendant_are_subtracted_once(self):
        self.assertEqual(self.result(excluded=['TA/345/01']),
                         self.result(excluded=['TA/345/01', 'TA/345/01/02', 'TA/345/01/02']))

    def test_complete_mixed_depth_exclusion_leaves_no_rounding_residual(self):
        value = self.result(excluded=['TA/345/01/01', 'TA/345/01/02', 'TA/345/02'])
        self.assertEqual(value['status'], 'excluded')
        self.assertEqual(value['value'], 0)
        self.assertIn('TA/345', action_details.effective_exclusions(self.records, 'TA',
                      ['TA/345/01/01', 'TA/345/01/02', 'TA/345/02']))

    def test_unknown_subaction_and_action_without_children_remain_unavailable(self):
        for scope, excluded in [('TA/345/01/99', []), ('TA/345/02/01', []),
                                ('TA/345', ['TA/345/01/99']), ('TA/345/02', ['TA/345/02/01'])]:
            value = self.result(scope, excluded)
            self.assertEqual(value['status'], 'detail_unavailable')
            self.assertIsNone(value['value'])

    def test_inflation_and_proof_use_the_same_nominal_base(self):
        from budget_service.model import constant_cents
        value = self.result(excluded=['TA/345/01/01'], constant=True, base=2025)
        self.assertEqual(value['nominal_cents'], 2501)
        self.assertEqual(value['value'], constant_cents(2501, 2024, 2025, {2024: '98', 2025: '100'}) / 100)
        proof = action_details.proofs(action_details.resolve(self.records, 'TA/345', ['TA/345/01/01']))
        self.assertEqual(sum(r['cents'] for r in proof), value['nominal_cents'])


if __name__ == '__main__':
    unittest.main()
