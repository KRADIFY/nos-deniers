import unittest
from budget_service import topics


class MprLfi2022PartTests(unittest.TestCase):
    def setUp(self):
        self.p=dict(budget='BG',measure='CP',exclude=[],constant=False,base=2022)

    def test_p362_lfi_is_not_the_plf_amount(self):
        lfi=topics.subset('PR/362',2022,'LFI',self.p,{2022:100})
        plf=topics.subset('PR/362',2022,'PLF',self.p,{2022:100})
        self.assertEqual(lfi['nominal_cents'],56560000000)
        self.assertEqual(plf['nominal_cents'],56550000000)
        self.assertTrue(lfi['approximate'])
        self.assertIn('0,1 M€',lfi['precision'])
        self.assertIn(dict(source='2f15709320cdd6cb8d0a',page=55),lfi['citations'])

    def test_missing_p135_keeps_national_lfi_unavailable(self):
        for measure in ('AE','CP'):
            p=dict(self.p,measure=measure)
            national=topics.subset('',2022,'LFI',p,{2022:100})
            self.assertIsNone(national['nominal_cents'])
            self.assertEqual(national['status'],'topic_unavailable')
            self.assertIsNone(topics.subset('VA/135',2022,'LFI',p,{2022:100})['value'])

    def test_explicit_ae_zero_is_not_an_inferred_cp_zero(self):
        ae=topics.subset('PR/362',2022,'LFI',dict(self.p,measure='AE'),{2022:100})
        self.assertEqual(ae['nominal_cents'],0)
        self.assertEqual(ae['count'],1)
        self.assertEqual(ae['status'],'ok')
        self.assertFalse(ae['approximate'])

    def test_amount_does_not_create_action_allocation(self):
        result=topics.subset('PR/362/01',2022,'LFI',self.p,{2022:100})
        self.assertIsNone(result['value'])
        self.assertEqual(result['status'],'detail_unavailable')
