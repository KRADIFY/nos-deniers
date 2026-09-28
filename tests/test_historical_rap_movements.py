import json
import unittest
from pathlib import Path
from budget_service import rap_movements
from budget_service.rap_validation import validate_movements

ROOT=Path(__file__).resolve().parents[1]
FILE=ROOT/'budget_service/data/mouvements-rap-historique.json'
DETAIL_FILE=ROOT/'budget_service/data/mouvements-rap-historique-detail.json'

class HistoricalRapMovementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=json.loads(FILE.read_text(encoding='utf8'))
        cls.detail=json.loads(DETAIL_FILE.read_text(encoding='utf8'))

    def test_annual_net_registries_are_reconciled(self):
        regs=self.data['registries']
        self.assertEqual(len(regs),108)
        self.assertEqual(sum(len(r['items']) for r in regs),432)
        for reg in regs:
            validate_movements(reg)
            self.assertEqual(reg['scope']['years'][0], int(reg['items'][0]['year']))
            self.assertTrue(all(r['date_precision']=='annual' for r in reg['items']))
            self.assertTrue(all(len(r['cells'])==8 for r in reg['evidence_rows']))

    def test_catalogue_source_ids_are_used(self):
        for reg in self.data['registries']:
            self.assertTrue(all(len(s['id'])==20 and len(s['sha256'])==64 for s in reg['sources']))
            self.assertTrue(all(row['source'] in {s['id'] for s in reg['sources']} for row in reg['items']))

    def test_detailed_historical_registries_are_reconciled(self):
        regs=self.detail['registries']
        self.assertEqual(len(regs),671)
        self.assertEqual(sum(len(r['items']) for r in regs),24470)
        self.assertEqual(sum(len(r['evidence_rows']) for r in regs),9398)
        for reg in regs:
            validate_movements(reg)

    def test_detail_replaces_overlapping_annual_summary(self):
        regs=[r for r in rap_movements._all_registries() if r['scope']['years'][0] <= 2022]
        keys=[(r['scope']['years'][0],r['scope']['budget'],r['scope']['mission'],r['scope']['program']) for r in regs]
        self.assertEqual(len(keys),852)
        self.assertEqual(sum(key[1] == 'BG' for key in keys),674)
        self.assertEqual(sum(key[1] in ('BA','CAS','CCF') for key in keys),178)
        self.assertEqual(len(keys),len(set(keys)))

if __name__=='__main__': unittest.main()
