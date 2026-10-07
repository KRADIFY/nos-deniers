import unittest
from budget_service.reconciliation import assess_difference, difference_note


class ReconciliationPolicyTests(unittest.TestCase):
    def test_ten_euros_is_inclusive_in_both_directions(self):
        for difference in (-1000,1000):
            with self.subTest(difference=difference):
                self.assertTrue(assess_difference(10**12+difference,10**12)['accepted'])

    def test_one_cent_above_cap_requires_investigation_even_on_billions(self):
        for difference in (-1001,1001,1882228800):
            for terms in (1,10000):
                with self.subTest(difference=difference,terms=terms):
                    check=assess_difference(10**12+difference,10**12,terms)
                    self.assertFalse(check['accepted'])
                    self.assertTrue(check['review_required'])
                    self.assertLessEqual(check['rounding_bound_cents'],1000)
                    self.assertLessEqual(check['materiality_bound_cents'],1000)
                    self.assertIn('à analyser avant validation',difference_note(check))

    def test_old_approval_cannot_be_described_as_a_current_tolerated_difference(self):
        check={'status':'source_difference','difference_cents':52500030}
        note=difference_note(check)
        self.assertIn('à analyser avant validation',note)
        self.assertNotIn('0,1 %',note)
        self.assertEqual(check['difference_cents'],52500030)

    def test_existing_stricter_small_reference_rule_is_not_relaxed(self):
        self.assertFalse(assess_difference(200,0)['accepted'])
        self.assertEqual(assess_difference(100,100)['status'],'exact')
        self.assertEqual(assess_difference(10100,10000)['status'],'published_rounding_difference')


if __name__=='__main__':unittest.main()
