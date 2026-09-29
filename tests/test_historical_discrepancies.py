"""Historical publication differences must remain notices, never fact edits."""
import json
import unittest
from pathlib import Path
from budget_service import historical_discrepancies


class HistoricalDiscrepancyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = json.loads((Path(historical_discrepancies.__file__).with_name('data') /
                                  'historical_discrepancy_notices_2017_2022.json').read_text(encoding='utf-8'))['entries']

    def test_register_is_complete_and_arithmetic_is_exact(self):
        self.assertEqual(len(self.entries), 43)
        keys = {(r['year'], r['budget'], r['mission'], r['program'], r['measure'], r['stage'])
                for r in self.entries}
        self.assertEqual(len(keys), 43)
        for row in self.entries:
            self.assertEqual(row['site_cents'] - row['other_publication_cents'], row['difference_cents'])
        self.assertEqual(sum(r['status'] == 'Rapprochement exact (documents)' for r in self.entries), 1)

    def test_notice_only_for_unchanged_complete_programme(self):
        row = next(r for r in self.entries if r['id'] == 'E18')
        scope = row['mission'] + '/' + row['program']
        p = {'budget': row['budget'], 'measure': row['measure'], 'exclude': [], 'topic': ''}
        result = {'nominal_cents': row['site_cents']}
        self.assertEqual(historical_discrepancies.matching(p, row['year'], row['stage'], scope, result)['id'], 'E18')
        self.assertIsNone(historical_discrepancies.matching(p, row['year'], row['stage'], scope + '/01', result))
        self.assertIsNone(historical_discrepancies.matching(p, row['year'], row['stage'], scope,
                                                             {'nominal_cents': row['site_cents'] + 1}))
        self.assertIsNone(historical_discrepancies.matching(dict(p, exclude=[scope + '/01']),
                                                             row['year'], row['stage'], scope, result))
        self.assertIsNone(historical_discrepancies.matching(dict(p, topic='maprimerenov'),
                                                             row['year'], row['stage'], scope, result))

    def test_documentary_bridge_keeps_administrative_limit(self):
        row = next(r for r in self.entries if r['id'] == 'E18')
        self.assertEqual(abs(row['difference_cents']), 221600)
        self.assertIn('reste à confirmer', row['limit'])
        self.assertTrue(any('legifrance.gouv.fr' in link for link in row['links']))


if __name__ == '__main__':
    unittest.main()
