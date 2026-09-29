import json, sqlite3, tempfile, unittest
from contextlib import closing
from pathlib import Path
from zero_reconcile import reconcile


class ZeroReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        self.coverage = self.out / 'coverage'
        self.coverage.mkdir()
        self.item = dict(status='undetermined', budget='BG', year=2020,
                         path='AA/307', measure='AE', stage='EXEC', source='s',
                         sha256='a'*64, raw='unread', reason='unread')
        (self.out/'zeros-sources.json').write_text(json.dumps(dict(items=[self.item], counts={'undetermined':1})), 'utf-8')
        with closing(sqlite3.connect(self.out/'zeros-sources.sqlite')) as db, db:
            db.execute('create table items(status text, search text, data text)')
            db.execute('insert into items values(?,?,?)', ('undetermined','',json.dumps(self.item)))
        self.cell = dict(status='matched', expected_cents=0, actual_cents=[0],
                         source='s', sha256='a'*64, budget='BG', year=2020,
                         program='307', measure='AE', stage='EXEC', page=19,
                         raw='0,00', bbox=[1,2,3,4])
        (self.coverage/'coverage.json').write_text(json.dumps(dict(documents_read=1,
            documents_expected=1, reader_sha256='reader', database_sha256='database')), 'utf-8')

    def run_join(self, cells):
        (self.coverage/'cells.json').write_text(json.dumps(cells), 'utf-8')
        return reconcile(self.out, self.coverage)

    def test_exact_zero_is_confirmed_in_all_outputs(self):
        result = self.run_join([self.cell])
        self.assertEqual(result['documentary_zeros_confirmed'], 1)
        self.assertEqual(result['still_undetermined'], 0)
        item = json.loads((self.out/'zeros-sources.json').read_text('utf-8'))['items'][0]
        self.assertEqual(item['source_reader_status'], 'undetermined')
        self.assertEqual(item['location']['page'], 19)
        self.assertEqual(item['documentary_proof']['expected_cents'], 0)
        with closing(sqlite3.connect(self.out/'zeros-sources.sqlite')) as db, db:
            self.assertEqual(db.execute('select status from items').fetchone()[0], 'documentary_zero')
        self.assertIn('Zéro confirmé', (self.out/'zeros-sources.csv').read_text('utf-8-sig'))

    def test_nonzero_blank_wrong_document_and_ambiguous_proofs_remain_unknown(self):
        bad = []
        for field, value in [('expected_cents', 1), ('actual_cents', [1]),
                             ('sha256', 'b'*64), ('stage', 'LFI'), ('raw', '')]:
            cell = self.cell.copy(); cell[field] = value; bad.append(cell)
        result = self.run_join(bad)
        self.assertEqual(result['documentary_zeros_confirmed'], 0)
        self.assertEqual(result['still_undetermined'], 1)
        # Even two otherwise valid rows do not identify one unique PDF cell.
        result = self.run_join([self.cell, self.cell])
        self.assertEqual(result['documentary_zeros_confirmed'], 0)

    def test_incomplete_documentary_reading_never_confirms(self):
        p = self.coverage/'coverage.json'
        data = json.loads(p.read_text('utf-8'));data['documents_read']=0
        p.write_text(json.dumps(data), 'utf-8')
        with self.assertRaisesRegex(ValueError, 'incomplète'):
            self.run_join([self.cell])


if __name__ == '__main__': unittest.main()
