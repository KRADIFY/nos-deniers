import copy,json,sys,unittest
from pathlib import Path
from budget_service.reconciliation import assess_difference
from budget_service.rap_validation import validate_action,validate_movements,validate_reserve

ROOT=Path(__file__).resolve().parents[1];DATA=ROOT/'budget_service/data'
def read(name):return json.loads((DATA/name).read_text(encoding='utf8'))

class RecoveryTests(unittest.TestCase):
    def test_small_rounding_and_source_disagreement_are_distinct(self):
        self.assertEqual(assess_difference(100000100,100000000)['status'],'published_rounding_difference')
        self.assertEqual(assess_difference(122706324400,122653824370)['status'],'material_difference')
        self.assertFalse(assess_difference(100100000,100000000)['accepted'])
        self.assertFalse(assess_difference(100100001,100000000)['accepted'])
        self.assertFalse(assess_difference(200,0)['accepted'])

    def test_source_disagreement_retains_both_figures_and_note(self):
        g=next(g for g in read('actions-national.json')['groups'] if
               (g['year'],g['program'],g['stage'],g['measure'])==(2023,'124','EXEC','AE'))
        self.assertEqual(sum(r['cents'] for r in g['parents']),122653824370)
        self.assertEqual(g['published_total_euros'],1227063244)
        self.assertIn('525 000,30',g['reconciliation_note'])
        # Retain the two published figures, but revoke their old automatic approval.
        with self.assertRaises(AssertionError):validate_action(g)
        bad=copy.deepcopy(g);bad['actions'][0]['euros']+=10000
        with self.assertRaises(AssertionError):validate_action(bad)

    def test_wrong_programme_zero_actions_are_removed(self):
        g=next(g for g in read('actions-national.json')['groups'] if
               (g['year'],g['program'],g['stage'],g['measure'])==(2024,'425','LFI','AE'))
        self.assertEqual([a['code'] for a in g['actions']],['01','02','03'])
        self.assertTrue(all(a['page']==129 and a['euros']==0 for a in g['actions']))

    def test_police_and_gendarmerie_reserves_are_not_swapped(self):
        rows=[r for r in read('reserves-national.json')['records'] if r['year']==2025 and r['mission']=='SB' and r['measure']=='AE']
        self.assertEqual(next(r for r in rows if r['program']=='176')['page'],56)
        self.assertEqual(next(r for r in rows if r['program']=='152')['page'],141)

    def test_one_euro_source_error_stays_visible(self):
        row=next(r for r in read('reserves-national.json')['records'] if (r['year'],r['program'],r['measure'])==(2025,'350','CP'))
        self.assertEqual(row['cells']['remaining']['total_cents'],0)
        self.assertEqual(row['numeric_validation'],'published_with_balance_difference')
        self.assertTrue(any(not c['passed'] for c in row['checks']));validate_reserve(row)
        bad=copy.deepcopy(row);bad['cells']['remaining']['total_cents']+=1000
        with self.assertRaises(AssertionError):validate_reserve(bad)

    def test_missing_movement_cell_cannot_silently_disappear(self):
        r=copy.deepcopy(read('mouvements-rap-national.json')['registries'][0])
        r['items'].pop()
        with self.assertRaises(AssertionError):validate_movements(r)

    def test_zeroes_have_an_explicit_published_total(self):
        plan=read('rap-explicit-zeros.json')
        self.assertEqual(len(plan['rows']),46)
        for row,proof in zip(plan['rows'],plan['proofs']):
            self.assertEqual(row['cents'],0);self.assertEqual(row['line'],proof['page'])
            self.assertRegex(proof['raw_line'],r'Total des (AE|CP)')
            self.assertRegex(proof['raw_line'],r'\s0\s*$')

if __name__=='__main__':unittest.main()
