import unittest
from budget_service import import_fdc_forecast as fdc
from budget_service.normalize import column_key
from budget_service.api import cell

class ForecastImportTests(unittest.TestCase):
 def fixture(self):
  source={'budget':'BG','code_mission':'TA','mission':'Écologie','code_programme':'203.0','programme':'Transports','code_titre':'6.0','plf_2023_ae':'3840845046','plf_2023_cp':'4072626282','prevision_fdc_adp_2023_ae':'2201033333','prevision_fdc_adp_2023_cp':'2744108829','prevision_fdc_adp_2024_ae':'999999999999','prevision_fdc_adp_2024_cp':'888888888888'}
  table=[(2,{column_key(k):v for k,v in source.items()})]
  base=[(2023,'PLF',m,'BG','TA','Écologie','203','Transports','','','','','','6',a,'prior',2,'plf',0) for m,a in [('AE',384084504600),('CP',407262628200)]]
  return table,base
 def test_expected_forecasts_only_and_exact_provenance(self):
  t,b=self.fixture();rows,checks=fdc.parse_rows(t,b)
  self.assertEqual(len(rows),2)
  self.assertEqual([r[14] for r in rows],[220103333300,274410882900])
  self.assertTrue(all(r[0:2]==(2023,'FDC_PREVU') and r[15]==fdc.SOURCE_ID and r[16]==2 for r in rows))
  self.assertEqual(rows[1][17],'prevision_fdc_adp_2023_cp')
  self.assertTrue(all(c['passed'] for c in checks))
 def test_missing_does_not_turn_into_zero(self):
  t,b=self.fixture();t[0][1][column_key('prevision_fdc_adp_2023_cp')]=''
  with self.assertRaisesRegex(ValueError,'Missing 2023'):fdc.parse_rows(t,b)
  t[0][1][column_key('prevision_fdc_adp_2023_cp')]='0'
  self.assertEqual(fdc.parse_rows(t,b)[0][1][14],0)
 def test_source_duplicates_and_wrong_plf_are_rejected(self):
  t,b=self.fixture()
  with self.assertRaisesRegex(ValueError,'Duplicate'):fdc.parse_rows(t+t,b)
  t[0][1][column_key('plf_2023_cp')]='4072626283'
  with self.assertRaisesRegex(ValueError,'reconcile'):fdc.parse_rows(t,b)
 def test_programme_is_not_an_action_and_forecast_is_not_receipt(self):
  t,b=self.fixture();rows,_=fdc.parse_rows(t,b)
  names=['year','stage','measure','budget','mission','mission_label','program','program_label','action','action_label','subaction','subaction_label','category','title','cents','source','line','field','approximate']
  records=[dict(zip(names,r)) for r in rows if r[2]=='CP']
  p=dict(constant=False,base=2023,exclude=[])
  self.assertEqual(cell(records,'TA/203',2023,'FDC_PREVU',p,{2023:100})['nominal_cents'],274410882900)
  self.assertIsNone(cell(records,'TA/203/41',2023,'FDC_PREVU',p,{2023:100})['value'])
  self.assertIsNone(cell(records,'TA/203',2023,'FDC',p,{2023:100})['value'])
  self.assertIsNone(cell(records,'TA',2023,'FDC_PREVU',dict(p,exclude=['TA/203/41']),{2023:100})['value'])

if __name__=='__main__':unittest.main()