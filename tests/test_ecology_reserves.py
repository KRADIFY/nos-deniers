"""Independent controls from the reviewed RAP tables and selection rules."""
import json
import unittest
from pathlib import Path
from budget_service import reserves

class EcologyReserveTests(unittest.TestCase):
 def setUp(self):
  self.p=dict(start=2023,end=2025,budget='BG',measure='CP',scope='TA',exclude=[],constant=False,base=2017,topic='',topic_mode='only')
  self.meta={'indices':{'2017':100,'2023':114,'2024':118,'2025':120}}
 def query(self,**changes):return reserves.query(dict(self.p,**changes),self.meta)
 def row(self,program,year=2024,**changes):return next(r for r in self.query(**changes)['items'] if r['program']==program and r['year']==year)
 def test_source_programmes_and_no_assumed_zero(self):
  q=self.query()
  self.assertEqual(q['integrated_table_count'],28)
  self.assertEqual({r['program'] for r in q['items'] if r['year']==2025},{'113','159','174','181','203','205','217','235','345','380'})
  r=self.row('355',2023)
  self.assertFalse(r['table_available'])
  self.assertEqual(r['page'],575)
  self.assertTrue(all(c['value'] is None and c['status']=='table_unavailable' for c in r['cells'].values()))
  self.assertEqual(self.query(scope='TA/355')['years_without_integrated_table'],[2023,2024,2025])
  self.assertFalse(any(r['program']=='235' and r['year']<2025 for r in q['items']))
 def test_biodiversity_cp_exact_and_commentary(self):
  r=self.row('113')
  self.assertEqual(r['cells']['initial']['nominal_cents'],2516827100)
  self.assertEqual(r['cells']['surgels']['value'],106758217)
  self.assertEqual(r['cells']['degels']['value'],-46820533)
  self.assertEqual(r['cells']['remaining']['value'],85105955)
  self.assertEqual(r['context_pages'],[192,193])
  self.assertIsNone(r['cells']['cancellations']['value'])
 def test_title_two_included_and_signs_preserved(self):
  r=self.row('217',2025)
  self.assertEqual(r['cells']['initial']['value'],27445127)
  self.assertEqual(r['cells']['initial']['source_cells']['title2_cents'],1457777400)
  self.assertEqual(r['cells']['degels']['value'],-21344720)
  self.assertEqual(r['cells']['remaining']['value'],11866983)
 def test_published_discrepancy_not_silently_corrected(self):
  r=self.row('217',2023)
  self.assertEqual(r['cells']['remaining']['nominal'],25941092)
  self.assertEqual(r['cells']['remaining']['nominal']-sum(r['cells'][k]['nominal'] for k in ['initial','surgels','degels']),1)
  self.assertEqual(r['numeric_validation'],'published_with_balance_difference')
  self.assertIn('1 €',r['note'])
  self.assertTrue(any(c['difference_cents']==100 and not c['passed'] for c in r['checks']))
 def test_text_divergence_keeps_the_reconciled_table(self):
  r=self.row('159')
  self.assertEqual(r['cells']['remaining']['value'],1123243)
  self.assertIn('1 123 596',r['note'])
 def test_without_mpr_keeps_unrelated_programmes(self):
  full=self.query();without=self.query(topic='maprimerenov',topic_mode='without')
  for original in full['items']:
   r=next(r for r in without['items'] if (r['year'],r['program'])==(original['year'],original['program']))
   if r['program']=='174':
    self.assertTrue(all(c['value'] is None and c['status']=='detail_unavailable' for c in r['cells'].values()))
   else:self.assertEqual(r['cells'],original['cells'])
 def test_only_mpr_never_displays_other_programme_reserves(self):
  q=self.query(topic='maprimerenov')
  self.assertEqual({r['program'] for r in q['items']},{'174'})
  self.assertTrue(all(r['cells']['initial']['value'] is None for r in q['items']))
 def test_programme_and_action_exclusions_apply_only_where_required(self):
  q=self.query(exclude=['TA/345','TA/235','TA/113/07'])
  self.assertFalse(any(r['program'] in ('345','235') for r in q['items']))
  self.assertIsNone(self.row('113',exclude=['TA/113/07'])['cells']['initial']['value'])
  self.assertEqual(self.row('203',exclude=['TA/113/07'])['cells']['initial']['value'],231528038)
  self.assertEqual(self.row('203',scope='TA/203')['cells']['initial']['value'],231528038)
  self.assertIsNone(self.row('203',scope='TA/203/41')['cells']['initial']['value'])
 def test_constant_euros_convert_the_selected_year_only(self):
  r=self.row('235',2025,constant=True,measure='AE')
  self.assertEqual(r['cells']['initial']['nominal'],8300326)
  self.assertEqual(r['cells']['initial']['value'],6916938.33)
  q=reserves.query(dict(self.p,constant=True,base=2026),self.meta)
  self.assertTrue(all(r['cells']['initial']['status']=='inflation_missing' for r in q['items'] if r['table_available']))
 def test_previous_pilot_and_non_additivity_preserved(self):
  pilot=json.loads((Path(reserves.__file__).parent/'data/reserves-p174.json').read_text(encoding='utf-8'))
  current=reserves.registry()
  actual=[r for r in current['records'] if r['program']=='174']
  expected=sorted(pilot['records'],key=lambda r:(r['year'],int(r['program']),r['measure']))
  self.assertEqual(len(actual),len(expected))
  for row,original in zip(actual,expected):
   self.assertEqual({k:row[k] for k in original},original)
   self.assertTrue(row['checks'])
  self.assertNotIn('totals',self.query());self.assertNotIn('total',self.query())
 def test_mpr_did_not_exist_before_2020(self):
  r=self.row('174',2018,start=2018,end=2018,topic='maprimerenov')
  self.assertIsNone(r['cells']['initial']['value'])
  self.assertEqual(r['cells']['initial']['status'],'not_applicable')
  self.assertEqual(self.row('174',2018,start=2018,end=2018,topic='maprimerenov',topic_mode='without')['cells'],self.row('174',2018,start=2018,end=2018)['cells'])
 def test_sources_and_registry_version_in_selection(self):
  q=self.query();sources={s['id']:s for s in q['sources']}
  for r in q['items']:self.assertEqual(r['source_sha256'],sources[r['source']]['sha256'])
  self.assertNotEqual(q['selection_id'],self.query(exclude=['TA/345'])['selection_id'])

if __name__=='__main__':unittest.main()
