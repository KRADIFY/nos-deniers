import copy
import json
import unittest
from pathlib import Path
from budget_service.rap_validation import validate_reserve

DATA=Path(__file__).resolve().parents[1]/'budget_service/data'

class HistoricalReserveCorrections(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=json.loads((DATA/'reserves-historique-2017-2022.json').read_text(encoding='utf-8'))['records']

    def find(self,year,program,measure):
        return next(r for r in self.rows if (r['year'],r['program'],r['measure'])==(year,program,measure))

    def test_every_table_retains_printed_checks_and_reconciles(self):
        self.assertGreaterEqual(len(self.rows),950)
        for row in self.rows:
            with self.subTest(year=row['year'],program=row['program'],measure=row['measure']):
                validate_reserve(row)

    def test_defense_cancellation_is_not_lost(self):
        row=self.find(2017,'146','CP')
        self.assertEqual(row['cells']['cancellations']['total_cents'],-85000000000)
        self.assertEqual(row['cells']['remaining']['total_cents'],70000000000)
        bad=copy.deepcopy(row);bad['cells'].pop('cancellations')
        with self.assertRaises(AssertionError):validate_reserve(bad)

    def test_page_continuation_has_its_own_provenance(self):
        row=self.find(2019,'156','AE')
        self.assertEqual(row['cells']['remaining']['total_cents'],6637376500)
        self.assertEqual(row['field_pages']['initial'],29)
        self.assertEqual(row['field_pages']['remaining'],30)
        self.assertEqual(row['context_pages'],[29,30])

    def test_blank_measure_does_not_create_zero(self):
        self.assertFalse(any((r['year'],r['program'],r['measure'])==(2018,'344','AE') for r in self.rows))
        self.assertEqual(self.find(2018,'344','CP')['cells']['initial']['total_cents'],551750300)

    def test_page_header_is_not_a_money_cell(self):
        self.assertEqual(self.find(2022,'119','AE')['cells']['initial']['total_cents'],17995198100)
        self.assertEqual(self.find(2020,'216','CP')['cells']['initial']['total_cents'],2478365700)

if __name__=='__main__':unittest.main()
