import unittest
from budget_service.model import cents, constant_cents, parts, safe_csv
from budget_service.normalize import column_key
from budget_service.api import cell, parameters

def fact(program='174',action='',amount=10000,stage='EXEC',year=2024):
    return dict(year=year,stage=stage,measure='CP',budget='BG',mission='EA',program=program,
                action=action,subaction='',cents=amount,source='test',approximate=0)

class BudgetCalculationTests(unittest.TestCase):
    def setUp(self): self.p=parameters({})

    def test_french_and_scientific_amounts_preserve_cents_and_absence(self):
        self.assertEqual(cents('1\u202f234\u00a0567,89'),123456789)
        self.assertEqual(cents('1,24824E+11'),12482400000000)
        self.assertEqual(cents('-20,01'),-2001)
        self.assertEqual(cents('0'),0)
        self.assertIsNone(cents(''))
        with self.assertRaises(ValueError): cents('Expr1')

    def test_outgoing_reports_never_overwrite_incoming_reports(self):
        self.assertNotEqual(column_key('Report_N-1'),column_key('Report_N+1'))
        self.assertEqual(column_key('Report_N−1'),column_key('Report_N-1'))

    def test_nested_action_identifiers(self):
        self.assertEqual(parts('146.0','','146-09-84'),('146','09','84'))
        self.assertEqual(parts('146','9','84'),('146','09','84'))

    def test_constant_euros_and_multiyear_sum(self):
        indices={2023:'97.12',2024:'99.07',2025:'100'}
        self.assertEqual(constant_cents(971200,2023,2025,indices),1000000)
        self.assertEqual(constant_cents(990700,2024,2025,indices),1000000)
        self.assertIsNone(constant_cents(100,2026,2025,indices))
        self.assertEqual(sum(constant_cents(v,y,2025,indices) for y,v in [(2023,971200),(2024,990700)]),2000000)

    def test_program_exclusion_recalculates_mission(self):
        rows=[fact(amount=12000),fact('203',amount=45000)]
        self.p['exclude']=['EA/174']
        result=cell(rows,'EA',2024,'EXEC',self.p,{})
        self.assertEqual(result['value'],450)
        self.assertEqual(result['status'],'ok')

    def test_action_exclusion_does_not_allocate_program_total(self):
        self.p['exclude']=['EA/174/02']
        result=cell([fact()],'EA',2024,'EXEC',self.p,{})
        self.assertIsNone(result['value'])
        self.assertEqual(result['status'],'detail_unavailable')

    def test_overlapping_exclusions_do_not_subtract_twice(self):
        self.p['exclude']=['EA/174','EA/174/02']
        rows=[fact(action='02',amount=3000),fact('203','01',amount=8000)]
        self.assertEqual(cell(rows,'EA',2024,'EXEC',self.p,{})['value'],80)

    def test_missing_child_and_real_zero_are_distinct(self):
        self.assertIsNone(cell([fact()],'EA/174/02',2024,'EXEC',self.p,{})['value'])
        self.assertEqual(cell([fact(amount=0)],'EA',2024,'EXEC',self.p,{})['value'],0)
        self.assertEqual(cell([],'EA',2024,'EXEC',self.p,{})['status'],'missing')

    def test_incomplete_program_coverage_is_not_a_complete_total(self):
        rows=[fact(),fact('203',stage='LFI')]
        result=cell(rows,'EA',2024,'EXEC',self.p,{})
        self.assertEqual(result['status'],'partial')
        self.assertIn('203',result['reason'])

    def test_query_bounds_and_formula_injection(self):
        for query in [{'start':['2016']},{'end':['2027']},{'scope':['../../secrets']},{'exclude':['["/etc/passwd"]']}]:
            with self.assertRaises(ValueError): parameters(query)
        self.assertEqual(safe_csv('=HYPERLINK("x")'),'\'=HYPERLINK("x")')
        self.assertEqual(safe_csv('Écologie'),'Écologie')

if __name__=='__main__': unittest.main()
