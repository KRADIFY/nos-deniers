import copy
import json
import unittest
from unittest.mock import patch
from budget_service import action_details
from budget_service.api import cell, parameters, provenance


class SourceDB:
    def __init__(self, altered=False):
        self.altered = altered

    def execute(self, sql, args):
        g = next(g for g in action_details.registry()[0]['groups'] if g['source'] == args[0])
        self.row = (json.dumps({'sha256': 'changed' if self.altered else g['sha256']}),)
        return self

    def fetchone(self):
        return self.row


class ActionDetailTests(unittest.TestCase):
    def rows(self, year=2024, measure='CP', stage='EXEC', changed=False):
        group = next(g for g in action_details.registry()[0]['groups'] if (g['year'], g['measure'], g['stage']) == (year, measure, stage))
        return action_details.attach([copy.deepcopy(group['parent'])], SourceDB(changed))

    def result(self, scope='TA/174', excluded=(), year=2024, measure='CP', stage='EXEC', **options):
        p = dict(parameters({}), exclude=list(excluded), **options)
        return cell(self.rows(year, measure, stage), scope, year, stage, p, {2024: '98', 2025: '100'})

    def test_parent_and_mission_keep_cents_instead_of_sum_of_rounded_actions(self):
        for scope in ('', 'TA', 'TA/174'):
            value = self.result(scope)
            self.assertEqual(value['nominal_cents'], 379744710997)
            self.assertFalse(value['approximate'])
            self.assertEqual(value['sources'], ['d5dc9d71f6165da67f38'])
        children = [self.result('TA/174/' + str(i).zfill(2)) for i in range(1, 7)]
        self.assertEqual(sum(c['nominal_cents'] for c in children), 379744711100)

    def test_action_uses_published_total_and_precise_page(self):
        value = self.result('TA/174/02')
        self.assertEqual(value['nominal_cents'], 146815394700)
        self.assertTrue(value['approximate'])
        self.assertEqual(value['grain'], 'action')
        self.assertEqual(value['citations'], [{'source': '113330a8d3bb90c96604', 'page': 426}])
        self.assertIn('publié à l’euro', value['precision'])
        self.assertEqual(self.result('TA/174/05', year=2023, measure='AE')['nominal_cents'], 5184776600)

    def test_exclusion_subtracts_from_original_total_with_no_double_counting(self):
        result = self.result(excluded=['TA/174/02', 'TA/174/02'])
        self.assertEqual(result['nominal_cents'], 232929316297)
        self.assertEqual(result['nominal_cents'] + self.result('TA/174/02')['nominal_cents'], self.result()['nominal_cents'])
        self.assertEqual(set(result['sources']), {'d5dc9d71f6165da67f38', '113330a8d3bb90c96604'})
        rows = list(action_details.resolve(self.rows(), 'TA/174', ['TA/174/02']))
        proofs = action_details.proofs(rows)
        self.assertEqual(sum(r['cents'] for r in proofs), result['nominal_cents'])
        self.assertEqual(proofs[1]['operation'], 'subtract_action')
        self.assertFalse(any(k.startswith('_') for r in proofs for k in r))

    def test_all_actions_excluded_does_not_leave_rounding_residual(self):
        result = self.result(excluded=['TA/174/' + str(i).zfill(2) for i in range(1, 7)])
        self.assertEqual(result['status'], 'excluded')
        self.assertEqual(result['value'], 0)
        self.assertEqual(self.result(excluded=['TA/174', 'TA/174/02'])['value'], 0)

    def test_all_actions_excluded_keeps_other_program_complete(self):
        rows=self.rows()
        rows.append(dict(action_details.public_row(rows[0]),program='203',cents=10000))
        p=dict(parameters({}),exclude=['TA/174/'+str(i).zfill(2) for i in range(1,7)])
        value=cell(rows,'TA',2024,'EXEC',p,{})
        self.assertEqual(value['nominal_cents'],10000)
        self.assertEqual(value['status'],'ok')

    def test_excluding_action_and_its_subaction_does_not_require_finer_data(self):
        self.assertEqual(self.result(excluded=['TA/174/02','TA/174/02/01']),self.result(excluded=['TA/174/02']))

    def test_complete_action_exclusion_does_not_subtract_mpr_again(self):
        from budget_service import topics
        rows=self.rows()
        rows.append(dict(action_details.public_row(rows[0]),program='203',cents=10000))
        p=dict(parameters({}),topic='maprimerenov',topic_mode='without',exclude=['TA/174/'+str(i).zfill(2) for i in range(1,7)])
        base=cell(rows,'TA',2024,'EXEC',p,{})
        result=topics.calculate(rows,base,'TA',2024,'EXEC',p,{})
        self.assertEqual(result['nominal_cents'],10000)
        self.assertEqual(result['status'],'ok')

    def test_unknown_action_and_subaction_do_not_produce_invented_amounts(self):
        for scope, excluded in [('TA/174/99', []), ('TA/174/02/01', []), ('TA/174', ['TA/174/02/01']), ('TA/174', ['TA/174/99'])]:
            result = self.result(scope, excluded)
            self.assertEqual(result['status'], 'detail_unavailable')
            self.assertIsNone(result['value'])

    def test_changed_parent_source_or_pdf_disables_previously_checked_detail(self):
        group = action_details.registry()[0]['groups'][0]
        for field, value in [('cents', group['parent']['cents'] + 1), ('source', 'other'), ('action', '02')]:
            parent = dict(group['parent'], **{field: value})
            self.assertNotIn('_action_details', action_details.attach([parent], SourceDB())[0])
        self.assertNotIn('_action_details', self.rows(changed=True)[0])
        doubled = [copy.deepcopy(group['parent']) for _ in range(2)]
        self.assertTrue(all('_action_details' not in r for r in action_details.attach(doubled, SourceDB())))

    def test_exclusion_applied_before_inflation(self):
        from budget_service.model import constant_cents
        value = self.result(excluded=['TA/174/02'], constant=True, base=2025)
        self.assertEqual(value['value'], constant_cents(232929316297, 2024, 2025, {2024: '98', 2025: '100'}) / 100)

    def test_reviewed_groups_have_complete_actions_and_explicit_rounding(self):
        groups = [g for g in action_details.registry()[0]['groups'] if 'parents' not in g and g.get('year', 9999) >= 2023]
        self.assertEqual(len(groups), 71)
        self.assertEqual(sum(len(g['actions']) for g in groups),408)
        for g in groups:
            expected={'174':['01','02','03','04','05','06'],'113':['01','02','07'],
                      '159':['10','11','12','13'],'205':['01','02','03','04','05','07','08'],
                      '380':['01','02','03'],
                      '203':['01','04','41','42','43','44','45','47','50','51','52','53']}[g['program']]
            self.assertEqual([a['code'] for a in g['actions']], expected)
            delta = sum(a['euros'] * 100 for a in g['actions']) - g['parent']['cents']
            self.assertEqual(delta, g['action_sum_minus_parent_cents'])
            self.assertLessEqual(abs(delta), len(expected)*50 if g['stage'] == 'EXEC' else 0)

    def test_biodiversity_lfi_does_not_add_forecast_funds(self):
        group=next(g for g in action_details.registry()[0]['groups'] if (g['program'],g['year'],g['measure'],g['stage'])==('113',2023,'CP','LFI'))
        records=action_details.attach([copy.deepcopy(group['parent'])],SourceDB())
        p=parameters({})
        result=cell(records,'TA/113',2023,'LFI',p,{})
        self.assertEqual(result['nominal_cents'],27450946800)
        result=cell(records,'TA/113/07',2023,'LFI',p,{})
        self.assertEqual(result['nominal_cents'],25870372400)
        self.assertEqual(result['citations'][0]['page'],171)

    def test_multipage_transport_table_keeps_each_action_page(self):
        group=next(g for g in action_details.registry()[0]['groups'] if (g['program'],g['year'],g['measure'],g['stage'])==('203',2024,'CP','EXEC'))
        records=action_details.attach([copy.deepcopy(group['parent'])],SourceDB())
        for action,amount,page in [('42',25742632900,44),('43',16238814800,45)]:
            result=cell(records,'TA/203/'+action,2024,'EXEC',parameters({}),{})
            self.assertEqual(result['nominal_cents'],amount)
            self.assertEqual(result['citations'],[{'source':'113330a8d3bb90c96604','page':page}])
        p=dict(parameters({}),exclude=['TA/203/42','TA/203/43'])
        result=cell(records,'TA/203',2024,'EXEC',p,{})
        self.assertEqual(result['nominal_cents'],group['parent']['cents']-25742632900-16238814800)
        self.assertEqual([c['page'] for c in result['citations']],[44,45])

    def test_published_negative_and_zero_are_preserved(self):
        group=next(g for g in action_details.registry()[0]['groups'] if (g['program'],g['year'],g['measure'],g['stage'])==('203',2025,'AE','EXEC'))
        records=action_details.attach([copy.deepcopy(group['parent'])],SourceDB())
        for code,amount in [('51',-943137600),('53',0)]:
            result=cell(records,'TA/203/'+code,2025,'EXEC',parameters({}),{})
            self.assertEqual(result['nominal_cents'],amount)
            self.assertEqual(result['status'],'ok')
        p=dict(parameters({}),exclude=['TA/203/51'])
        result=cell(records,'TA/203',2025,'EXEC',p,{})
        self.assertEqual(result['nominal_cents'],group['parent']['cents']+943137600)

    def test_small_transport_difference_is_documented_and_usable(self):
        groups=action_details.registry()[0]['groups']
        recovered=next(g for g in groups if (g['program'],g['year'],g['measure'],g['stage'])==('203',2023,'AE','EXEC'))
        self.assertEqual(recovered['published_total_minus_parent_cents'],600)
        self.assertIn('6,00 €',recovered['reconciliation_note'])
        attached=action_details.attach(copy.deepcopy(recovered['parents']),SourceDB())
        total=cell(attached,'TA/203',2023,'EXEC',parameters({}),{})
        self.assertEqual(total['nominal_cents'],811347669000)
        self.assertIn('6,00 €',total['reason'])
        detail=cell(attached,'TA/203/41',2023,'EXEC',parameters({}),{})
        self.assertIsNotNone(detail['value'])
        # A different source/parent must still disable the detail.
        group=next(g for g in groups if (g['program'],g['year'],g['measure'],g['stage'])==('203',2024,'AE','EXEC'))
        parent=dict(group['parent'],year=2023,cents=811347669000)
        records=action_details.attach([parent],SourceDB())
        value=cell(records,'TA/203',2023,'EXEC',parameters({}),{})
        self.assertEqual(value['nominal_cents'],811347669000)
        value=cell(records,'TA/203/41',2023,'EXEC',parameters({}),{})
        self.assertEqual(value['status'],'detail_unavailable')
        self.assertIsNone(value['value'])

    def test_source_discrepancy_provenance_exposes_both_sources(self):
        g=next(g for g in action_details.registry()[0]['groups'] if (g['program'],g['year'],g['measure'],g['stage'])==('124',2023,'AE','EXEC'))
        records=action_details.attach(copy.deepcopy(g['parents']),SourceDB())
        with patch('budget_service.api.selected_records',return_value=records),patch('budget_service.api.source',side_effect=lambda db,s:dict(id=s)),patch('budget_service.api.metadata',return_value={'issues':[]}):
            proof=provenance(None,dict(parameters({}),start=2023,end=2023),2023,'EXEC','SE/124')
        self.assertIn('525 000,30',proof['note'])
        self.assertEqual(sum(r['cents'] for r in proof['rows']),122653824370)
        self.assertEqual(proof['count'],2)
        self.assertEqual({s['id'] for s in proof['sources']},{g['source'],g['parents'][0]['source']})
        self.assertIn(dict(source=g['source'],page=137),proof['citations'])

    def test_reviewed_conflict_keeps_parent_and_displays_actions_with_alert(self):
        g=next(g for g in action_details.registry()[0]['groups'] if (g['program'],g['year'],g['measure'],g['stage'])==('124',2023,'AE','EXEC'))
        records=action_details.attach(copy.deepcopy(g['parents']),SourceDB())
        p=parameters({})
        parent=cell(records,'SE/124',2023,'EXEC',p,{})
        self.assertEqual(parent['nominal_cents'],122653824370)
        self.assertEqual(len(parent['source_disagreements']),1)
        scope='SE/124/'+g['actions'][0]['code']
        action=cell(records,scope,2023,'EXEC',p,{})
        self.assertEqual(action['nominal_cents'],g['actions'][0]['euros']*100)
        self.assertEqual(action['source_disagreements'],parent['source_disagreements'])
        remaining=cell(records,'SE/124',2023,'EXEC',dict(p,exclude=[scope]),{})
        self.assertEqual(remaining['nominal_cents']+action['nominal_cents'],parent['nominal_cents'])
        self.assertEqual(remaining['source_disagreements'],parent['source_disagreements'])


if __name__ == '__main__':
    unittest.main()
