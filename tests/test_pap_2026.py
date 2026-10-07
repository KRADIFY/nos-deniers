import copy,json,unittest
from pathlib import Path
from budget_service.import_pap_2026 import validate_plan

class Pap2026Tests(unittest.TestCase):
    def setUp(self):
        self.plan=json.loads((Path(__file__).resolve().parents[1]/'budget_service/data/pap-ecologie-2026.json').read_text(encoding='utf8'))
    def test_reviewed_totals_are_distinct_from_expected_funds(self):
        validate_plan(self.plan)
        rows=self.plan['rows']
        expected={('PLF','AE'):2423762153700,('PLF','CP'):2181444542200,('FDC_PREVU','AE'):352509996000,('FDC_PREVU','CP'):357380246000}
        for (stage,measure),cents in expected.items():self.assertEqual(sum(r['cents'] for r in rows if r['stage']==stage and r['measure']==measure),cents)
    def test_no_blank_cell_is_imported_as_zero(self):
        self.assertFalse(any(r['program']=='362' for r in self.plan['rows']))
        self.assertFalse(any(r['cents']==0 for r in self.plan['rows']))
        self.assertFalse(any(r['stage']=='FDC_PREVU' and r['program'] in ('174','345','380') for r in self.plan['rows']))
    def test_altered_totals_or_duplicates_are_refused(self):
        for kind in ('amount','duplicate','stage'):
            plan=copy.deepcopy(self.plan)
            if kind=='amount':plan['rows'][0]['cents']+=1
            elif kind=='duplicate':plan['rows'][1]=plan['rows'][0]
            else:plan['rows'][0]['stage']='LFI'
            with self.assertRaises(ValueError):validate_plan(plan)
    def test_proofs_have_correct_source_pages_and_units(self):
        for row in self.plan['rows']:
            self.assertEqual(row['source'],'b3b6f06b6363f6f7df96')
            self.assertIn(row['page'],(17,18,19,20))
            self.assertEqual(row['page'],row['line'])
            self.assertEqual(row['cents']%100,0)

if __name__=='__main__':unittest.main()