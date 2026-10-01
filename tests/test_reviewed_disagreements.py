import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from budget_service import action_details
from budget_service.api import cell, parameters, provenance
from budget_service.reconciliation import action_cents


class SourceDB:
    def __init__(self, group):
        self.group = group

    def execute(self, sql, args):
        self.row = (json.dumps({'sha256': self.group['sha256']}),) if args[0] == self.group['source'] else None
        return self

    def fetchone(self):
        return self.row


class ReviewedDisagreementsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = json.loads((Path(action_details.__file__).parent / 'data/actions-national.json').read_text(encoding='utf-8'))
        cls.groups = [g for g in data['groups'] if g.get('review_required')]

    def rows(self, group):
        with patch.object(action_details, 'registry', return_value=({'groups': [group]}, 'fixture')):
            return action_details.attach(copy.deepcopy(group['parents']), SourceDB(group))

    def result(self, group, scope=None, excluded=()):
        scope = scope or group['mission'] + '/' + group['program']
        return cell(self.rows(group), scope, group['year'], group['stage'],
                    dict(parameters({}), exclude=list(excluded)), {})

    def test_all_sixteen_exact_actions_canonical_totals_and_alerts(self):
        self.assertEqual(len(self.groups), 16)
        self.assertEqual({action_details.key(g) for g in self.groups}, action_details.PUBLISHED_DISAGREEMENTS)
        for group in self.groups:
            with self.subTest(key=action_details.key(group)):
                self.assertTrue(action_details.published_disagreement(group))
                parent = self.result(group)
                canonical = sum(p['cents'] for p in group['parents'])
                self.assertEqual(parent['nominal_cents'], canonical)
                warning = parent['source_disagreements']
                self.assertEqual(len(warning), 1)
                self.assertEqual(warning[0]['difference_cents'], warning[0]['rap_cents'] - canonical)
                self.assertLessEqual(abs(sum(action_cents(a) for a in group['actions']) - warning[0]['rap_cents']), 100)
                self.assertIn('Écart entre sources', parent['reason'])
                self.assertIn(group['source'], parent['sources'])
                for action in group['actions']:
                    scope = group['mission'] + '/' + group['program'] + '/' + action['code']
                    child = self.result(group, scope)
                    self.assertEqual(child['nominal_cents'], action_cents(action))
                    self.assertEqual(child['source_disagreements'], warning)
                    self.assertIn(group['source'], child['sources'])
                    self.assertFalse('aucun détail utilisé automatiquement' in child['reason'])

    def test_exclusion_and_reactivation_use_published_action_without_allocation(self):
        group = next(g for g in self.groups if g['program'] == '354' and g['measure'] == 'AE')
        scope = group['mission'] + '/' + group['program']
        selected = group['actions'][0]
        excluded = self.result(group, scope, [scope + '/' + selected['code']])
        restored = self.result(group, scope)
        self.assertEqual(excluded['nominal_cents'] + action_cents(selected),
                         restored['nominal_cents'])
        self.assertEqual(excluded['source_disagreements'],
                         restored['source_disagreements'])

    def test_mission_total_lists_the_contributing_rap_disagreement(self):
        group = next(g for g in self.groups if g['program'] == '354' and g['measure'] == 'AE')
        rows = self.rows(group)
        result = cell(rows, group['mission'], group['year'], group['stage'],
                      parameters({'measure': ['AE']}), {})
        self.assertEqual(result['nominal_cents'], sum(r['cents'] for r in group['parents']))
        self.assertEqual([(r['kind'], r['program']) for r in result['documented_discrepancies']],
                         [('RAP', '354')])

    def test_changed_source_still_blocks_detail(self):
        group = copy.deepcopy(self.groups[0])
        with patch.object(action_details, 'registry', return_value=({'groups': [group]}, 'fixture')):
            rows = action_details.attach(copy.deepcopy(group['parents']), SourceDB(dict(group, sha256='changed')))
        result = cell(rows, group['mission'] + '/' + group['program'] + '/' + group['actions'][0]['code'],
                      group['year'], group['stage'], parameters({}), {})
        self.assertEqual(result['status'], 'detail_unavailable')

    def test_provenance_contains_both_source_totals_and_warning(self):
        group = next(g for g in self.groups if g['program'] == '354' and g['measure'] == 'AE')
        rows = self.rows(group)
        params = dict(parameters({}), start=2023, end=2023)
        scope = group['mission'] + '/' + group['program'] + '/' + group['actions'][0]['code']
        with patch('budget_service.api.selected_records', return_value=rows), \
             patch('budget_service.api.source', side_effect=lambda db, sid: {'id': sid}), \
             patch('budget_service.api.metadata', return_value={'issues': []}):
            proof = provenance(None, params, 2023, 'EXEC', scope)
        self.assertEqual(proof['explanation']['title'], 'Alerte : écart entre les sources')
        self.assertEqual(proof['explanation']['source_comparisons'], self.result(group)['source_disagreements'])
        self.assertIn('Écart entre sources', proof['explanation']['summary'])
        self.assertTrue(proof['explanation']['references'])
        self.assertIn(group['source'], [s['id'] for s in proof['sources']])
        self.assertIn(group['parents'][0]['source'], [s['id'] for s in proof['sources']])


if __name__ == '__main__':
    unittest.main()
