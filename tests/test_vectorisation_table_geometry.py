import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('table_geometry', ROOT / 'tools/vectorisation_table_geometry.py')
geometry = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(geometry)


class GeometryTests(unittest.TestCase):
    def test_coverage_accepts_spacing_but_preserves_all_numbers(self):
        words = [[0, 0, 1, 1, text] for text in ['AE', '153', '345', '027']]
        self.assertTrue(geometry.coverage_for_words(words, [['AE', '153 345 027']])['complete'])
        missing = geometry.coverage_for_words(words, [['AE', '153 345']])
        self.assertFalse(missing['complete'])
        self.assertEqual(missing['missing_numeric_tokens'], {'027': 1})

    def test_multiline_header_covers_ae_cp_without_converting_numbers(self):
        words = [[0, 0, 1, 1, text] for text in ['Autorisations', "d'engagement", 'Crédits', 'de', 'paiement']]
        result = geometry.coverage_for_words(words, [["Autorisations\nd'engagement", 'Crédits\nde paiement']])
        self.assertTrue(result['complete'])

    def test_combined_ae_cp_header_is_ambiguous(self):
        self.assertEqual(geometry.combined_credit_headers(['Libellé', "Autorisations Crédits\nd'engagement de paiement"]), [2])
        self.assertEqual(geometry.combined_credit_headers(["Autorisations d'engagement", 'Crédits de paiement']), [])

    def test_presentation_panel_not_numeric_grid(self):
        self.assertFalse(geometry.meaningful_grid([['Programme 362', '2021'], ['Objectif', 'Écologie']])['plausible'])

    def test_real_mpr_and_missing_totals(self):
        try:
            import fitz
        except ImportError:
            self.skipTest('PyMuPDF unavailable')
        probe_root = ROOT / 'reports/audit-vectorisation-20260911/probes'
        cases = [('d10eb8327053-p8', 8, ['MaPrime', '2021']),
                 ('f51582832fff-p190', 190, ['153345027', '1454571682'])]
        for directory, page_no, expected in cases:
            metadata = probe_root / directory / 'candidates.json'
            if not metadata.exists():
                self.skipTest('Real source probes are not present on this machine')
            path = json.loads(metadata.read_text(encoding='utf8'))['source_path']
            if not Path(path).exists():
                self.skipTest('Source PDF not present on this machine')
            with fitz.open(path) as doc:
                result = geometry.recovery_candidates(doc[page_no - 1])
            self.assertTrue(result['tables'], (directory, result['diagnostics'], [t['rejection_reasons'] for t in result['rejected_candidates']]))
            rendered = ''.join(str(cell) for table in result['tables'] for row in table['rows'] for cell in row)
            compact = ''.join(rendered.split())
            for marker in expected:
                self.assertIn(marker, compact)
            for table in result['tables']:
                self.assertTrue(table['coverage']['complete'])
                self.assertFalse(table['allow_automatic_numeric_fact'])
                self.assertTrue(table['header_geometry']['source_words'])

    def test_real_presentation_pages_keep_raw_without_fake_table(self):
        try:
            import fitz
        except ImportError:
            self.skipTest('PyMuPDF unavailable')
        path = ROOT / 'vectorisation-nos-deniers-20260909/sources-documentaires/pdf/2021/plf-pap/e1de6edd1cf0_FR_2021_PLF_BG_PGM_362.pdf'
        if not path.exists():
            self.skipTest('Source PDF not present on this machine')
        with fitz.open(path) as doc:
            for page_no in [3, 5]:
                result = geometry.recovery_candidates(doc[page_no - 1])
                self.assertEqual(result['tables'], [])
                self.assertTrue(result['fallback']['words'])
                self.assertFalse(result['automatic_numeric_fact'])


if __name__ == '__main__':
    unittest.main()
