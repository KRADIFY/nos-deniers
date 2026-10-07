"""The published P169 action is usable; its contradictory children are evidence only."""
import copy
import json
import unittest
from unittest.mock import patch
from budget_service import action_details
from budget_service.api import cell,parameters,provenance
from budget_service.reconciliation import assess_difference

SOURCE='680dddd291a977e417ad'
NOTE=('Sous-actions 09 non utilisables dans les calculs ni les exclusions : '
      '33 677 229 € contre 33 693 979 €, écart 16 750 €. '
      'L’action 09 entière reste utilisable. Aucun montant de sous-action n’est déduit.')

class SourceDB:
    def __init__(self,group):self.group=group
    def execute(self,sql,args):
        assert args==(self.group['source'],)
        return self
    def fetchone(self):return (json.dumps({'sha256':self.group['sha256']}),)

class NestedActionReviewTests(unittest.TestCase):
    def setUp(self):
        group=next(g for g in action_details.registry()[0]['groups'] if
                   (g['program'],g['year'],g['stage'],g['measure'])==('169',2024,'EXEC','CP'))
        self.group=copy.deepcopy(group)
        self.group.update(published_total_euros=1882210033,total_page=12,review_required=False,
            reconciliation=assess_difference(188221003300,188221003311),
            action_reconciliation=assess_difference(188221003200,188221003311,5),
            published_total_minus_parent_cents=-11,action_sum_minus_parent_cents=-111,
            reconciliation_note='Récapitulation publiée page 12 ; total de référence conservé.')
        self.action=next(a for a in self.group['actions'] if a['code']=='09')
        self.action.update(euros=33693979,page=12,subactions_review=dict(
            status='review_required',accepted=False,note=NOTE,
            citations=[dict(source=SOURCE,page=p) for p in (12,29,32)]))

    def rows(self,other=False):
        with patch.object(action_details,'registry',return_value=({'groups':[self.group]},'fixture')):
            rows=action_details.attach(copy.deepcopy(self.group['parents']),SourceDB(self.group))
        if other:rows.append(dict(copy.deepcopy(self.group['parents'][0]),program='999',cents=10000))
        return rows

    def result(self,scope='MB/169',excluded=(),other=False):
        return cell(self.rows(other),scope,2024,'EXEC',dict(parameters({}),exclude=list(excluded)),{})

    def proof(self,scope,excluded=(),other=False):
        rows=self.rows(other)
        with patch('budget_service.api.selected_records',return_value=rows),patch('budget_service.api.source',side_effect=lambda db,s:dict(id=s)),patch('budget_service.api.metadata',return_value={'issues':[]}):
            return provenance(None,dict(parameters({}),start=2024,end=2024,exclude=list(excluded)),2024,'EXEC',scope)

    def test_canonical_total_unchanged_at_programme_mission_and_national(self):
        for scope in ('','MB','MB/169'):
            with self.subTest(scope=scope):
                result=self.result(scope)
                self.assertEqual(result['nominal_cents'],188221003311)
                self.assertEqual(result['status'],'ok')
                self.assertFalse(result['approximate'])

    def test_whole_action_09_is_consultable_and_subtractible(self):
        value=self.result('MB/169/09')
        self.assertEqual(value['status'],'ok')
        self.assertEqual(value['nominal_cents'],3369397900)
        self.assertIn(dict(source=SOURCE,page=12),value['citations'])
        self.assertIn(NOTE,value['reason'])
        for scope in ('','MB','MB/169'):
            result=self.result(scope,['MB/169/09'])
            self.assertEqual(result['status'],'ok')
            self.assertEqual(result['nominal_cents'],184851605411)

    def test_other_actions_are_independently_consultable_and_subtractible(self):
        for action in self.group['actions']:
            if action['code']=='09':continue
            path='MB/169/'+action['code']
            with self.subTest(path=path):
                self.assertEqual(self.result(path)['nominal_cents'],action['euros']*100)
                self.assertEqual(self.result(excluded=[path])['nominal_cents'],188221003311-action['euros']*100)

    def test_unaffected_subactions_remain_usable(self):
        for child in next(a for a in self.group['actions'] if a['code']=='03')['subactions']:
            path='MB/169/03/'+child['code']
            with self.subTest(path=path):
                self.assertEqual(self.result(path)['nominal_cents'],child['euros']*100)
                self.assertEqual(self.result(excluded=[path])['nominal_cents'],188221003311-child['euros']*100)

    def test_both_original_children_remain_in_navigation_with_published_values(self):
        names={action_details.path_of(r):r for r in action_details.navigation(self.rows())}
        self.assertEqual(names['MB/169/09/01']['cents'],3193786300)
        self.assertEqual(names['MB/169/09/02']['cents'],173936600)
        self.assertEqual(names['MB/169/09/01']['page'],29)
        self.assertNotIn(3195461300,[r['cents'] for r in names.values()])

    def test_neither_child_is_consultable_or_subtractible(self):
        for child in ('01','02'):
            path='MB/169/09/'+child
            for scope,excluded in [(path,[]),('MB/169/09',[path]),('MB/169',[path]),('MB',[path]),('',[path])]:
                with self.subTest(scope=scope,excluded=excluded):
                    result=self.result(scope,excluded)
                    self.assertEqual(result['status'],'detail_unavailable')
                    self.assertIsNone(result['value'])
                    self.assertIn('16 750',result['reason'])

    def test_excluding_both_children_cannot_collapse_to_whole_action(self):
        children=['MB/169/09/01','MB/169/09/02']
        for scope in ('MB/169/09','MB/169','MB',''):
            result=self.result(scope,children)
            self.assertEqual(result['status'],'detail_unavailable')
            self.assertIsNone(result['value'])
            resolved=list(action_details.resolve(self.rows(),scope,children))
            self.assertFalse(any(r.get('_fully_excluded') for r in resolved))
            self.assertNotIn('MB/169/09',action_details.effective_exclusions(self.rows(),scope,children))

    def test_mixed_valid_action_and_invalid_child_exclusions_remain_unavailable(self):
        for other in (False,True):
            for excluded in (['MB/169/02','MB/169/09/01'],['MB/169/02','MB/169/09/01','MB/169/09/02']):
                self.assertEqual(self.result('MB',excluded,other)['status'],'detail_unavailable')

    def test_excluding_all_other_actions_and_both_children_still_unavailable(self):
        excluded=['MB/169/'+a['code'] for a in self.group['actions'] if a['code']!='09']
        excluded+=['MB/169/09/01','MB/169/09/02']
        self.assertEqual(self.result(excluded=excluded)['status'],'detail_unavailable')

    def test_excluding_all_five_whole_actions_is_valid(self):
        excluded=['MB/169/'+a['code'] for a in self.group['actions']]
        result=self.result(excluded=excluded)
        self.assertEqual(result['status'],'excluded')
        self.assertEqual(result['value'],0)
        self.assertEqual(self.result('MB',excluded,other=True)['nominal_cents'],10000)

    def test_explicit_whole_action_supersedes_redundant_child_exclusions(self):
        self.assertEqual(self.result(excluded=['MB/169/09']),self.result(excluded=['MB/169/09','MB/169/09/01','MB/169/09/02']))

    def test_provenance_retains_both_presentations_for_blocked_child_and_exclusion(self):
        for scope,excluded in [('MB/169/09/01',[]),('MB/169',['MB/169/09/02']),('', ['MB/169/09/01','MB/169/09/02'])]:
            with self.subTest(scope=scope,excluded=excluded):
                proof=self.proof(scope,excluded)
                self.assertIn('16 750',proof['note'])
                self.assertTrue({12,29,32}<={c['page'] for c in proof['citations'] if c['source']==SOURCE})
                self.assertEqual(proof['rows'][0]['cents'],3369397900)
                self.assertNotIn(3195461300,[r['cents'] for r in proof['rows']])

    def test_provenance_keeps_blocked_branch_when_another_programme_has_a_value(self):
        proof=self.proof('MB',['MB/169/09/01'],other=True)
        self.assertIn('16 750',proof['note'])
        self.assertTrue({12,29}<={c['page'] for c in proof['citations'] if c['source']==SOURCE})
        self.assertTrue(any(r['program']=='999' for r in proof['rows']))

    def test_computed_disagreement_also_blocks_without_review_metadata(self):
        del self.action['subactions_review']
        self.assertEqual(self.result('MB/169/09/01')['status'],'detail_unavailable')
        self.assertEqual(self.result(excluded=['MB/169/09/01','MB/169/09/02'])['status'],'detail_unavailable')
        self.assertEqual(self.result('MB/169/09')['nominal_cents'],3369397900)

class NestedActionValidationTests(unittest.TestCase):
    def group(self):
        return copy.deepcopy(next(g for g in action_details.registry()[0]['groups'] if
            (g['program'],g['year'],g['stage'],g['measure'])==('169',2024,'EXEC','CP')))

    def test_promoted_action_group_passes_without_accepting_its_children(self):
        from budget_service.rap_validation import validate_action
        group=self.group()
        validate_action(group)
        self.assertFalse(group['review_required'])
        action=next(a for a in group['actions'] if a['code']=='09')
        self.assertEqual(action['subactions_review']['status'],'review_required')
        self.assertFalse(action['subactions_review']['accepted'])
        self.assertEqual(group['source_correction_review']['original_group']['published_total_euros'],1882193283)
        self.assertEqual(group['published_total_euros'],1882210033)

    def test_corrupted_nested_review_or_source_proof_is_rejected(self):
        from budget_service.rap_validation import validate_action
        mutations={
            'missing_block_marker':lambda g,a:a.pop('subactions_review'),
            'accepted_child_marker':lambda g,a:a['subactions_review'].update(accepted=True),
            'invented_child_remainder':lambda g,a:a['subactions'][0].update(euros=31954613),
            'wrong_child_difference':lambda g,a:a['subactions_review'].update(difference_cents=-1),
            'changed_parent':lambda g,a:g['parents'][0].update(cents=g['parents'][0]['cents']+1),
            'changed_action':lambda g,a:a.update(euros=a['euros']+1),
            'wrong_source_hash':lambda g,a:a['subactions_review'].update(sha256='f'*64),
            'wrong_source_page':lambda g,a:a.update(page=13),
            'lost_old_source_amount':lambda g,a:a['subactions_review']['proofs'][2].update(raw_text='33 693 979'),
            'lost_new_source_amount':lambda g,a:a['subactions_review']['proofs'][0].update(raw_text='33 677 229'),
            'missing_old_page_citation':lambda g,a:a['subactions_review'].update(citations=[c for c in a['subactions_review']['citations'] if c['page']!=29]),
            'derived_replacement_allowed':lambda g,a:a['subactions_review'].update(derived_subaction_replacement_allowed=True),
        }
        for name,mutate in mutations.items():
            with self.subTest(name=name):
                group=self.group();action=next(a for a in group['actions'] if a['code']=='09')
                mutate(group,action)
                with self.assertRaises(AssertionError):validate_action(group)

if __name__=='__main__':unittest.main()
