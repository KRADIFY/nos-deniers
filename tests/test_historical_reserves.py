"""Independent historical RAP observations and their limits in the explorer."""
import unittest
from budget_service import reserves

class HistoricalReserveTests(unittest.TestCase):
 def setUp(self):
  self.p=dict(start=2017,end=2025,budget='BG',measure='CP',scope='TA',exclude=[],constant=False,base=2017,topic='',topic_mode='only')
  self.meta={'indices':{'2017':100,'2018':102,'2019':104,'2020':105,'2021':106,'2022':110,'2023':114,'2024':118,'2025':120}}
 def query(self,**changes):return reserves.query(dict(self.p,**changes),self.meta)
 def row(self,year,program,**changes):return next(r for r in self.query(**changes)['items'] if (r['year'],r['program'])==(year,program))
 def test_continuous_history_and_explicit_missing_tables(self):
  q=self.query()
  self.assertEqual(q['integrated_table_count'],76)
  self.assertEqual(q['count'],80)
  self.assertEqual(q['years_without_integrated_table'],[])
  for year in range(2017,2023):
   rows=[r for r in q['items'] if r['year']==year and r['table_available']]
   self.assertEqual({r['program'] for r in rows},{'113','159','174','181','203','205','217','345'})
  for year,page in [(2020,534),(2021,556),(2022,586),(2023,575)]:
   r=self.row(year,'355')
   self.assertEqual(r['page'],page)
   self.assertFalse(r['table_available'])
   self.assertTrue(all(c['value'] is None and c['status']=='table_unavailable' for c in r['cells'].values()))
  self.assertEqual(self.query(start=2026,end=2026)['years_without_integrated_table'],[2026])
 def test_2017_transport_signed_movements_and_blank_title_two(self):
  r=self.row(2017,'203')
  self.assertEqual(r['page'],62)
  self.assertEqual(r['context_pages'],[62,63])
  self.assertEqual({k:c['value'] for k,c in r['cells'].items()},dict(initial=238383395,surgels=152267490,degels=-26000000,cancellations=-208724575,remaining=155926310))
  self.assertTrue(all(c['source_cells']['title2_cents'] is None for c in r['cells'].values()))
  self.assertEqual(self.row(2017,'181')['cells']['remaining']['source_cells'],dict(title2_cents=22462200,other_titles_cents=0,total_cents=22462200))
 def test_2018_zero_table_does_not_erase_year_end_comment(self):
  r=self.row(2018,'205')
  self.assertEqual(r['cells']['initial']['value'],4380682)
  self.assertEqual(r['cells']['degels']['value'],0)
  self.assertEqual(r['cells']['remaining']['value'],4380682)
  self.assertIn('2 081 616',r['note'])
  self.assertEqual(self.row(2018,'217')['cells']['degels']['value'],-41520)
  self.assertIn('41 520 M€',self.row(2018,'217')['note'])
 def test_2019_column_discrepancy_and_missing_cancellation(self):
  r=self.row(2019,'217')
  self.assertEqual(r['cells']['initial']['value'],13829480)
  self.assertEqual(r['cells']['initial']['source_cells']['title2_cents'],1382948100)
  self.assertEqual(r['numeric_validation'],'published_with_column_difference')
  self.assertEqual([(c['field'],c['difference_cents']) for c in r['checks'] if not c['passed']],[('initial',-100),('remaining',-100)])
  self.assertEqual(self.row(2019,'217',measure='AE')['cells']['initial']['value'],13829481)
  self.assertIsNone(r['cells']['cancellations']['value'])
  self.assertEqual(r['cells']['cancellations']['status'],'not_reported')
 def test_2020_biodiversity_ae_cp_and_year_end_are_distinct(self):
  cp=self.row(2020,'113');ae=self.row(2020,'113',measure='AE')
  self.assertEqual(cp['cells']['degels']['value'],0)
  self.assertEqual(ae['cells']['degels']['value'],-7000000)
  self.assertEqual(cp['cells']['remaining']['value'],7410169)
  self.assertEqual(ae['cells']['remaining']['value'],162169)
  self.assertIn('explicitement exclu',cp['note'])
  self.assertEqual(cp['cells']['initial']['source_cells']['title2_cents'],0)
 def test_2022_annulation_and_surgel_are_separate(self):
  cp=self.row(2022,'203');ae=self.row(2022,'203',measure='AE')
  self.assertEqual(cp['cells']['surgels']['value'],59477730)
  self.assertEqual(ae['cells']['surgels']['value'],0)
  self.assertEqual(cp['cells']['cancellations']['value'],-59477730)
  self.assertEqual(ae['cells']['remaining']['value'],74894478)
  self.assertEqual(cp['cells']['remaining']['value'],136494068)
  self.assertEqual(self.row(2022,'205')['cells']['surgels']['value'],14957811)
  self.assertEqual(self.row(2022,'217')['context_pages'],[541,542])
 def test_mpr_action_exclusion_and_inflation_with_historical_data(self):
  base=self.row(2021,'203')
  self.assertEqual(self.row(2021,'203',topic='maprimerenov',topic_mode='without')['cells'],base['cells'])
  self.assertIsNone(self.row(2021,'174',topic='maprimerenov',topic_mode='without')['cells']['initial']['value'])
  self.assertEqual(self.row(2018,'174',topic='maprimerenov',topic_mode='without')['cells'],self.row(2018,'174')['cells'])
  self.assertEqual({r['program'] for r in self.query(topic='maprimerenov')['items']},{'174'})
  self.assertIsNone(self.row(2021,'203',exclude=['TA/203/41'])['cells']['initial']['value'])
  self.assertEqual(self.row(2022,'203',constant=True)['cells']['cancellations']['value'],-54070663.64)
  self.assertEqual(self.row(2022,'203',constant=True)['cells']['cancellations']['nominal_cents'],-5947773000)
 def test_historical_sources_stay_resolvable_without_mission_total(self):
  q=self.query(start=2017,end=2022)
  sources={s['id']:s['sha256'] for s in q['sources']}
  self.assertEqual(len(sources),6)
  for r in q['items']:self.assertEqual(sources[r['source']],r['source_sha256'])
  self.assertNotIn('total',q)
  self.assertNotIn('totals',q)
  self.assertEqual([len(c['integrated_programmes']) for c in q['coverage_by_year']],[8]*6)

if __name__=='__main__':unittest.main()