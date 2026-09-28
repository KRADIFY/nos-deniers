import json
import unittest
from pathlib import Path
from budget_service import reserves
from budget_service.rap_validation import validate_reserve

ROOT=Path(__file__).resolve().parents[1]
FILE=ROOT/'budget_service/data/reserves-national.json'

class NationalReserveTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.data=json.loads(FILE.read_text(encoding='utf-8'))
  cls.records=cls.data['records']

 def test_expected_unique_coverage(self):
  self.assertEqual(len(self.records),606)
  self.assertEqual(len({(r['year'],r['mission'],r['program']) for r in self.records}),303)
  self.assertEqual(len({r['source'] for r in self.records}),85)
  self.assertEqual(len({(r['year'],r['mission'],r['program'],r['measure']) for r in self.records}),606)

 def test_every_published_column_and_balance_is_exact(self):
  for row in self.records:
   with self.subTest(year=row['year'],mission=row['mission'],program=row['program'],measure=row['measure']):
    validate_reserve(row)

 def test_real_selection_and_fine_grain_refusal(self):
  row=self.records[0];scope=row['mission']+'/'+row['program']
  p=dict(start=row['year'],end=row['year'],budget='BG',measure=row['measure'],scope=scope,
         exclude=[],constant=False,base=2025,topic='',topic_mode='only')
  meta={'indices':{str(row['year']):100,'2025':100}}
  result=reserves.query(p,meta)
  selected=next(item for item in result['items'] if item['program']==row['program'])
  self.assertTrue(selected['table_available'])
  self.assertEqual(selected['cells']['initial']['status'],'published')
  self.assertTrue(all(cell['status'] in ('published','not_reported') for cell in selected['cells'].values()))
  p['scope']=scope+'/01'
  detailed=reserves.query(p,meta)
  selected=next(item for item in detailed['items'] if item['program']==row['program'])
  self.assertTrue(all(cell['status']=='detail_unavailable' and cell['value'] is None for cell in selected['cells'].values()))

if __name__=='__main__':unittest.main()
