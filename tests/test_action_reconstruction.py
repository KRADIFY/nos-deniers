"""A documentary scope identity permits P224, without accepting the wrong RAP total."""
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from budget_service import action_details
from budget_service.api import cell,parameters,provenance
from budget_service.rap_validation import validate_action
from budget_service.reconciliation import action_cents

class SourceDB:
    def __init__(self,group,changed=None):
        self.group=group;self.changed=changed
        rec=group['action_reconstruction']
        self.hashes={group['source']:group['sha256'],rec['scope_proof']['source']:rec['scope_proof']['sha256'],rec['title2_parent']['source']:rec['title2_parent']['sha256']}
    def execute(self,sql,args):
        digest=self.hashes.get(args[0]);self.row=(json.dumps({'sha256':'changed' if args[0]==self.changed else digest}),) if digest else None
        return self
    def fetchone(self):return self.row

class ActionReconstructionTests(unittest.TestCase):
    def setUp(self):
        data=json.loads((Path(action_details.__file__).parent/'data/actions-national.json').read_text(encoding='utf-8'))
        self.group=copy.deepcopy(next(g for g in data['groups'] if (g['year'],g['program'],g['stage'],g['measure'])==(2023,'224','EXEC','AE')))
        self.rec=self.group['action_reconstruction']
    def rows(self,changed=None):
        with patch.object(action_details,'registry',return_value=({'groups':[self.group]},'fixture')):
            return action_details.attach(copy.deepcopy(self.group['parents']),SourceDB(self.group,changed))
    def result(self,scope='CB/224',excluded=(),changed=None):
        return cell(self.rows(changed),scope,2023,'EXEC',dict(parameters({}),exclude=list(excluded)),{})
    def proof(self,scope='CB/224/07',excluded=()):
        with patch('budget_service.api.selected_records',return_value=self.rows()),patch('budget_service.api.source',side_effect=lambda db,s:dict(id=s)),patch('budget_service.api.metadata',return_value={'issues':[]}):
            return provenance(None,dict(parameters({}),start=2023,end=2023,exclude=list(excluded)),2023,'EXEC',scope)
    def test_original_total_and_disagreement_are_preserved(self):
        validate_action(self.group)
        self.assertEqual(self.group['published_total_euros'],811055124)
        self.assertEqual(self.group['published_total_minus_parent_cents'],-675100)
        self.assertFalse(self.group['reconciliation']['accepted'])
        self.assertEqual(self.group['reconciliation'],self.rec['original_group']['reconciliation'])
        self.assertEqual(self.group['parents'],self.rec['original_group']['parents'])
    def test_parent_is_exact_and_not_replaced_by_action_sum(self):
        for scope in ('','CB','CB/224'):
            value=self.result(scope)
            self.assertEqual(value['nominal_cents'],81106187500)
            self.assertEqual(value['status'],'ok')
            self.assertFalse(value['approximate'])
        self.assertEqual(sum(action_cents(a) for a in self.group['actions']),81106187470)
        self.assertEqual(self.rec['unallocated_residual_cents'],30)
    def test_reconstructed_action_and_unchanged_published_action(self):
        value=self.result('CB/224/07')
        self.assertEqual(value['nominal_cents'],80305656370)
        self.assertIn('Montant reconstitué',value['precision'])
        self.assertIn('705 692 403,70',value['precision'])
        self.assertTrue(value['approximate'])
        self.assertEqual(self.result('CB/224/06')['nominal_cents'],800531100)
        self.assertIn('publié à l’euro',self.result('CB/224/06')['precision'])
    def test_all_sources_and_real_locations_are_present(self):
        proof=self.proof();row=proof['rows'][0]
        self.assertEqual(row['amount_kind'],'reconstructed')
        self.assertIn('Montant reconstitué',row['field'])
        self.assertNotIn('colonne Total',row['field'])
        self.assertEqual(len(proof['sources']),3)
        self.assertEqual({(c['source'],c.get('page')) for c in proof['citations']},{(self.group['source'],426),(self.rec['scope_proof']['source'],291),(self.rec['title2_parent']['source'],None)})
        self.assertEqual(row['reconstruction']['title2_parent']['row'],45)
        self.assertEqual(row['reconstruction']['ht2_components'][1]['raw_text'],'97 364 160')
    def test_whole_action_exclusions_keep_signed_proofs(self):
        for scope in ('','CB','CB/224'):
            value=self.result(scope,['CB/224/07'])
            self.assertEqual(value['nominal_cents'],800531130)
            self.assertEqual(value['status'],'ok')
        proof=self.proof('CB/224',['CB/224/07'])
        self.assertEqual(sum(r['cents'] for r in proof['rows']),800531130)
        subtraction=next(r for r in proof['rows'] if r.get('operation')=='subtract_action')
        self.assertEqual(subtraction['cents'],-80305656370)
        self.assertEqual(subtraction['amount_kind'],'reconstructed')
        self.assertEqual(len(proof['sources']),3)
        self.assertIn(dict(source=self.rec['scope_proof']['source'],page=291),proof['citations'])
        self.assertEqual(self.result(excluded=['CB/224/06'])['nominal_cents'],80305656400)
    def test_all_actions_excluded_does_not_leave_a_fictitious_30_cent_action(self):
        value=self.result(excluded=['CB/224/06','CB/224/07'])
        self.assertEqual(value['status'],'excluded');self.assertEqual(value['value'],0)
    def test_nonexistent_subaction_cannot_be_inferred(self):
        for scope,excluded in [('CB/224/07/01',[]),('CB/224',['CB/224/07/01'])]:
            self.assertEqual(self.result(scope,excluded)['status'],'detail_unavailable')
    def test_any_changed_source_disables_the_reconstruction(self):
        for source in SourceDB(self.group).hashes:
            with self.subTest(source=source):
                self.assertEqual(self.result('CB/224/07',changed=source)['status'],'detail_unavailable')
                self.assertEqual(self.result(changed=source)['nominal_cents'],81106187500)
    def test_exact_parent_is_required_even_if_grand_total_is_unchanged(self):
        self.group['parents'][0]['cents']+=1;self.group['parents'][1]['cents']-=1
        with self.assertRaises(AssertionError):validate_action(self.group)
        self.assertEqual(self.result('CB/224/07')['status'],'detail_unavailable')
    def test_missing_or_altered_evidence_is_rejected(self):
        mutations=[
            lambda g:g['action_reconstruction']['scope_proof'].update(raw_text='Titre 2 vide ailleurs'),
            lambda g:g['action_reconstruction']['scope_proof'].update(page=292),
            lambda g:g['action_reconstruction']['scope_proof'].update(sha256='0'*64),
            lambda g:g['action_reconstruction']['scope_proof'].update(action='06'),
            lambda g:g['action_reconstruction']['scope_proof'].update(bboxes=[]),
            lambda g:g['action_reconstruction'].update(method='ratio_allocation'),
            lambda g:g['action_reconstruction'].update(amount_cents=80305656371),
            lambda g:g['action_reconstruction'].update(unallocated_residual_cents=0),
            lambda g:g['action_reconstruction']['ht2_components'][1].update(raw_text='97 364 161'),
            lambda g:g['action_reconstruction']['ht2_components'][1].update(measure='CP'),
            lambda g:g['action_reconstruction']['ht2_components'][1].update(bbox=[]),
            lambda g:g['action_reconstruction']['title2_parent'].update(row=46),
            lambda g:g['action_reconstruction']['title2_parent'].update(raw_value='705692403,71'),
            lambda g:g['action_reconstruction'].update(citations=[]),
            lambda g:g['action_reconstruction'].update(formula='Somme prétendument imprimée'),
            lambda g:g['action_reconstruction']['title2_parent'].update(raw_value='not a number'),
            lambda g:g['action_reconstruction']['ht2_components'][1].update(column='Crédits de paiement'),
            lambda g:g['actions'][0].update(euros=8005312),
            lambda g:g['actions'][1].update(cents=80305656371),
            lambda g:g.update(published_total_euros=811061875),
            lambda g:g.update(published_total_cents=81106187500),
            lambda g:g.update(measure='CP'),
            lambda g:g.update(program='219'),
        ]
        original=copy.deepcopy(self.group)
        for i,mutate in enumerate(mutations):
            with self.subTest(mutation=i):
                self.group=copy.deepcopy(original);mutate(self.group)
                with self.assertRaises((AssertionError,KeyError)):validate_action(self.group)
    def test_remaining_sixteen_groups_stay_in_review(self):
        data=json.loads((Path(action_details.__file__).parent/'data/actions-national.json').read_text(encoding='utf-8'))
        self.assertEqual(sum(bool(g.get('review_required')) for g in data['groups']),16)
        self.assertEqual(sum(bool(g.get('action_reconstruction')) for g in data['groups']),1)

if __name__=='__main__':unittest.main()
