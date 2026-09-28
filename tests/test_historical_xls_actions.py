"""Regression checks for cent precision and independent XLS coordinates."""
import importlib.util
import unittest
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('historical_xls_actions',ROOT/'tools/extract_historical_xls_actions.py')
extractor=importlib.util.module_from_spec(spec);spec.loader.exec_module(extractor)

class CentPrecisionTests(unittest.TestCase):
    def test_source_cents_survive_large_binary_float_noise(self):
        self.assertEqual(extractor.cents(601793375.8299999),60179337583)
        self.assertEqual(extractor.cents(60825512.65),6082551265)
        self.assertEqual(extractor.cents(Decimal('-1.235')),-124)

    def test_blank_and_explicit_zero_remain_distinct(self):
        self.assertIsNone(extractor.cents(''))
        self.assertIsNone(extractor.cents(None))
        self.assertEqual(extractor.cents(0.0),0)
        with self.assertRaises(ValueError):extractor.cents('#VALUE!')
        with self.assertRaises(ValueError):extractor.cents(True)

    def test_cent_precision_does_not_allow_euro_rounding_envelope(self):
        self.assertFalse(extractor.reconcile(10000,10303,4)['accepted'])
        self.assertTrue(extractor.reconcile(10000,10000,4)['accepted'])

class PublishedXlsSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=extractor.DEFAULT_SOURCE_ROOT/'public/selenium/rap/2021/RAP_synthese_2021-95a0343007b6.xls'
        if not path.exists():raise unittest.SkipTest('Official historical XLS source unavailable')
        cls.programs,cls.header=extractor.read_source(path,2021)

    def test_reads_current_year_execution_with_real_excel_coordinates(self):
        p=self.programs['BG','JA','101'];a=p['actions'][0];proof=a['proofs']['AE']
        self.assertEqual(p['proofs']['AE']['cents'],60131290203)
        self.assertEqual((proof['sheet'],proof['cell'],proof['row'],proof['column']),('Crédits','S730',730,'S'))
        self.assertEqual(proof['cents'],55306477480)
        self.assertEqual(self.header['columns']['CP']['label'],'CP 2021')

    def test_keeps_nested_source_rows_without_treating_empty_cells_as_zero(self):
        p=self.programs['BA','XJ','624'];blank=next(a for a in p['actions'] if a['code']=='02')
        self.assertIsNone(blank['proofs']['AE']['cents'])
        p=self.programs['BG','TA','345'];a=next(a for a in p['actions'] if a['code']=='09')
        sub=next(z for z in a['subactions'] if z['code']=='01')
        self.assertEqual(sub['proofs']['AE']['cents'],185159514900)
        self.assertEqual(sub['proofs']['AE']['cell'],'S491')

if __name__=='__main__':unittest.main()
