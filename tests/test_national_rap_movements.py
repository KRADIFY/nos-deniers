import json
import sqlite3
import unittest
from pathlib import Path

from budget_service import rap_movements
from budget_service.rap_validation import validate_movements

ROOT=Path(__file__).resolve().parents[1]
FILE=ROOT/'budget_service/data/mouvements-rap-national.json'

class NationalRapMovementsTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.data=json.loads(FILE.read_text(encoding='utf-8'))
  cls.registries=cls.data['registries']

 def test_expected_exact_coverage(self):
  self.assertEqual(len(self.registries),354)
  self.assertEqual(sum(len(r['items']) for r in self.registries),10451)
  self.assertEqual(sum(len(r['evidence_rows']) for r in self.registries),4798)
  self.assertEqual(sum(len(r['table_totals']) for r in self.registries),2323)
  self.assertEqual(len({s['id'] for r in self.registries for s in r['sources']}),96)
  self.assertFalse(any(r['scope']['mission']=='TA' and r['scope']['program']=='174' for r in self.registries))

 def test_every_programme_reconciles_exactly_to_opened_credits(self):
  for registry in self.registries:
   with self.subTest(scope=registry['scope']):
    self.assertEqual({r['measure'] for r in registry['reconciliations']},{'AE','CP'})
    validate_movements(registry)
    self.assertEqual(len(registry['items']),len({r['id'] for r in registry['items']}))
    self.assertTrue(all(r['amount_cents']>=0 and r['sign'] in (-1,1) for r in registry['items']))

 def test_all_eight_source_columns_and_blanks_are_preserved(self):
  rows=[row for reg in self.registries for row in reg['evidence_rows']]
  self.assertTrue(rows)
  self.assertTrue(all(len(row['cells'])==8 for row in rows))
  self.assertTrue(any(cell['amount_cents'] is None for row in rows for cell in row['cells']))
  self.assertEqual({(c['measure'],c['title'],c['direction']) for c in rows[0]['cells']},
   {(m,t,d) for m in ('AE','CP') for t in ('2','HT2') for d in ('opening','cancellation')})

 def test_real_query_exposes_title_and_refuses_action_allocation(self):
  registry=self.registries[0];scope=registry['scope'];year=scope['years'][0]
  db=sqlite3.connect(':memory:');self.addCleanup(db.close)
  db.execute('CREATE TABLE sources (id TEXT PRIMARY KEY, data TEXT)')
  for source in registry['sources']:
   db.execute('INSERT INTO sources VALUES (?,?)',(source['id'],json.dumps(source)))
  p=dict(start=year,end=year,budget='BG',measure='CP',
         scope=scope['mission']+'/'+scope['program'],exclude=[],constant=False,base=2025,topic='',topic_mode='only')
  result=rap_movements.query(db,p,{'indices':{str(year):100,'2025':100},'inflation_source':'ipc'})
  self.assertTrue(result['items'])
  self.assertTrue(all(r['status']=='published' and r['value'] is not None for r in result['items']))
  self.assertTrue(all(r['title_label'] in ('Titre 2','Autres titres') for r in result['items']))
  p['scope']+='/01'
  detailed=rap_movements.query(db,p,{'indices':{str(year):100,'2025':100},'inflation_source':'ipc'})
  self.assertTrue(detailed['items'])
  self.assertTrue(all(r['status']=='detail_unavailable' and r['value'] is None for r in detailed['items']))

if __name__=='__main__':unittest.main()
