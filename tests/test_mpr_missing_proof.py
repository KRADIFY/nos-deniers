import copy,unittest
from unittest.mock import patch
from budget_service import topics

class MissingProofTests(unittest.TestCase):
    def cell(self,stage,measure='CP',scope='PR/362'):
        return topics.subset(scope,2024,stage,dict(budget='BG',measure=measure,exclude=[],constant=False,base=2025),{})
    def test_cp_zero_is_printed_rounded_and_cited(self):
        for stage in ('LFI','OUVERT'):
            c=self.cell(stage);self.assertEqual(c['nominal_cents'],0);self.assertTrue(c['approximate']);self.assertIn('0,1 Md€',c['precision']);self.assertIn(dict(source='296835325a7d511d6a5a',page=48),c['citations'])
    def test_cp_does_not_establish_ae(self):
        for stage in ('LFI','OUVERT'):
            for scope in ('PR','PR/362'):
                c=self.cell(stage,'AE',scope);self.assertIsNone(c['value']);self.assertEqual(c['status'],'topic_unavailable')
    def test_coverage_without_fact_does_not_create_zero(self):
        registry=copy.deepcopy(topics.registry());registry['facts']=[r for r in registry['facts'] if not (r['year']==2024 and r['program']=='362' and r['stage']=='LFI' and r['measure']=='CP')]
        with patch.object(topics,'registry',return_value=registry):self.assertIsNone(self.cell('LFI')['value'])
    def test_existing_execution_zeros_still_documented(self):
        for measure in ('AE','CP'):
            c=self.cell('EXEC',measure);self.assertEqual(c['nominal_cents'],0);self.assertTrue(c['citations'])
    def test_added_observations_only_cp(self):
        rows=[r for r in topics.registry()['facts'] if r['year']==2024 and r['program']=='362' and r['stage'] in ('LFI','OUVERT')]
        self.assertEqual([(r['stage'],r['measure']) for r in rows],[('LFI','CP'),('OUVERT','CP')])

if __name__=='__main__':unittest.main()
