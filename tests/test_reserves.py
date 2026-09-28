import unittest
from budget_service import reserves

class ReservePilotTests(unittest.TestCase):
 def setUp(self):
  self.p=dict(start=2017,end=2026,budget='BG',measure='CP',scope='TA/174',exclude=[],constant=False,base=2025,topic='',topic_mode='only')
  self.meta={'indices':{'2017':100,'2018':102,'2019':103,'2020':104,'2021':105,'2022':109,'2023':114,'2024':118,'2025':120},'inflation_source':'test'}
 def rows(self,**changes):
  return reserves.query(dict(self.p,**changes),self.meta)
 def test_exact_published_cp_and_source(self):
  q=self.rows(start=2024,end=2024);r=q['items'][0]
  self.assertEqual(r['cells']['initial']['nominal'],298406398)
  self.assertEqual(r['cells']['surgels']['nominal'],1403516085)
  self.assertEqual(r['cells']['degels']['nominal'],-1444830817)
  self.assertEqual(r['cells']['remaining']['nominal'],257091666)
  self.assertEqual(r['page'],437)
  self.assertEqual(q['sources'][0]['sha256'],r['source_sha256'])
 def test_older_table_has_separate_annulations_and_blank_title2(self):
  r=self.rows(start=2017,end=2017)['items'][0]
  self.assertEqual(r['cells']['cancellations']['nominal'],-41175881)
  self.assertIsNone(r['cells']['initial']['source_cells']['title2_cents'])
  self.assertEqual(r['cells']['remaining']['nominal'],0)
 def test_absent_annulations_is_not_zero(self):
  c=self.rows(start=2025,end=2025)['items'][0]['cells']['cancellations']
  self.assertIsNone(c['value']);self.assertEqual(c['status'],'not_reported')
 def test_missing_2026_not_zero(self):
  q=self.rows();self.assertEqual(len(q['items']),9);self.assertEqual(q['years_without_integrated_table'],[2026])
 def test_source_cutoff_remains_visible(self):
  r=self.rows(start=2018,end=2018)['items'][0]
  self.assertEqual(r['cells']['degels']['nominal'],0)
  self.assertIn('fin d’exercice',r['note']);self.assertIn('avant',r['remaining_label'])
 def test_ae_and_inflation(self):
  r=self.rows(start=2017,end=2017,measure='AE',constant=True)['items'][0]
  self.assertEqual(r['cells']['initial']['nominal'],35526681)
  self.assertEqual(r['cells']['initial']['value'],42632017.2)
 def test_action_or_action_exclusion_refuses_allocation(self):
  for p in [dict(scope='TA/174/02'),dict(exclude=['TA/174/02'])]:
   for r in self.rows(**p)['items']:
    self.assertIsNone(r['cells']['initial']['value'])
    self.assertEqual(r['cells']['initial']['status'],'detail_unavailable')
 def test_mpr_isolation_and_subtraction_refuse_allocation(self):
  for mode in ['only','without']:
   for r in self.rows(start=2020,topic='maprimerenov',topic_mode=mode)['items']:
    self.assertIsNone(r['cells']['initial']['value']);self.assertIsNone(r['cells']['initial']['nominal'])
 def test_unrelated_scope_and_excluded_programme(self):
  national=self.rows(scope='VA/135')['items']
  self.assertTrue(national)
  self.assertTrue(all(row['path']=='VA/135' for row in national))
  for p in [dict(budget='BA'),dict(exclude=['TA/174']),dict(exclude=['TA'])]:
   self.assertEqual(self.rows(**p)['items'],[])
 def test_no_mission_total_returned(self):
  q=self.rows();self.assertNotIn('total',q);self.assertNotIn('totals',q)
 def test_versioned_selection(self):
  self.assertNotEqual(self.rows()['selection_id'],self.rows(constant=True)['selection_id'])

if __name__=='__main__':unittest.main()
