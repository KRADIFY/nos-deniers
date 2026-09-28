import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
SPEC = importlib.util.spec_from_file_location('coverage_audit', Path(__file__).resolve().parents[1] / 'tools/audit_vectorisation_coverage.py')
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class CoverageTests(unittest.TestCase):
    def test_atomic_status_retries_transient_permission_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'status.json'
            target.write_text('{"documents_complete": 3192}', encoding='utf-8')
            pending = target.with_suffix('.json.partial')
            attempts = []
            original_replace = Path.replace

            def transient(source, destination):
                attempts.append((source, destination))
                if len(attempts) < 3:
                    raise PermissionError('Windows reader holds destination')
                return original_replace(source, destination)

            with patch.object(Path, 'replace', autospec=True, side_effect=transient), \
                    patch('prepare_vectorisation_tables.time.sleep') as sleep:
                audit.atomic_json(target, {'documents_complete': 3193})
            self.assertEqual(len(attempts), 3)
            self.assertEqual(sleep.call_count, 2)
            self.assertEqual(json.loads(target.read_text()), {'documents_complete': 3193})
            self.assertFalse(pending.exists())

    def test_atomic_status_persistent_denial_preserves_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'status.json'
            previous = '{"documents_complete": 3192}'
            target.write_text(previous, encoding='utf-8')
            with patch.object(Path, 'replace', side_effect=PermissionError('still locked')) as replace, \
                    patch('prepare_vectorisation_tables.time.sleep') as sleep:
                with self.assertRaises(PermissionError):
                    audit.atomic_json(target, {'documents_complete': 3193})
            self.assertEqual(replace.call_count, 30)
            self.assertEqual(sleep.call_count, 29)
            self.assertEqual(target.read_text(), previous)
            self.assertEqual(json.loads(target.with_suffix('.json.partial').read_text()),
                             {'documents_complete': 3193})

    def page(self):
        return {'kind': 'page', 'page': 1, 'page_count': 1, 'blocks': [
            {'bbox': [1, 1, 9, 9], 'text': "Autorisations d'engagement\nTotal Actions\n153 345 027"}],
            'tables': [{'bbox': [0, 0, 10, 10], 'rows': [['Total Actions', None]],
                        'header': {'names': []}, 'cells': [[0, 0, 5, 5], None]}], 'issues': []}

    def test_recognized_table_drops_number_and_ae_header(self):
        result = audit.inspect_page(self.page())
        self.assertEqual(result['missing_numbers'], {'153345027': 1})
        self.assertIn('autorisations', result['missing_header_words'])
        self.assertEqual(result['severity'], 'chiffres_non_retrouves_dans_rendu')
        self.assertFalse(result['automatic_numeric_fact'])

    def test_covered_grouping_and_null_not_zero(self):
        page = self.page()
        page['tables'][0]['rows'] = [["Autorisations d'engagement", 'Total Actions', '153\u202f345\u202f027', None]]
        result = audit.inspect_page(page)
        self.assertEqual(result['missing_numbers'], {})
        self.assertEqual(result['missing_header_words'], {})
        self.assertNotIn('Colonne 4', '\n'.join(audit.table_lines(page['tables'][0])))

    def test_unresolved_table_keeps_raw_but_does_not_certify(self):
        page = self.page()
        page['tables'] = []
        page['issues'] = [audit.ALERT]
        result = audit.inspect_page(page)
        self.assertEqual(result['missing_numbers'], {})
        self.assertEqual(result['severity'], 'structure_non_resolue')

    def test_duplicate_cell_geometry(self):
        page = self.page()
        page['tables'][0]['cells'] = [[0, 0, 5, 5], [0, 0, 5, 5]]
        self.assertEqual(audit.inspect_page(page)['duplicate_cell_boxes'], 1)

    def test_merged_ae_cp_numbers_are_ambiguous_not_absent(self):
        page = self.page()
        page['blocks'][0]['text'] = 'AE\nCP\n269 978 688\n281 325 241'
        page['tables'][0]['rows'] = [['AE CP', '269 978 688 281 325 241']]
        result = audit.inspect_page(page)
        self.assertEqual(result['unlocated_numbers'], {})
        self.assertEqual(set(result['ambiguous_numbers']), {'269978688', '281325241'})
        self.assertEqual(result['severity'], 'chiffres_presents_structure_ambigue')

    def test_snapshot_resume_and_source_hash_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            sha = 'ab' * 32
            shard = base / 'extracted' / sha[:2] / (sha + '.jsonl.gz')
            shard.parent.mkdir(parents=True)
            with gzip.open(shard, 'wt', encoding='utf8') as stream:
                stream.write(json.dumps(self.page()) + '\n')
            digest = hashlib.sha256(shard.read_bytes()).hexdigest()
            snap = base / 'snapshot.sqlite'
            c = sqlite3.connect(snap)
            c.executescript('CREATE TABLE assets(sha256 TEXT,path TEXT); CREATE TABLE extraction(asset_sha256 TEXT,status TEXT,shard_sha256 TEXT,receipt_json TEXT);')
            c.execute('INSERT INTO assets VALUES(?,?)', (sha, 'source.pdf'))
            c.execute('INSERT INTO extraction VALUES(?,?,?,?)', (sha, 'complete', digest, json.dumps({'counts': {'pages': 1}, 'issues': {}})))
            c.commit()
            c.close()
            snapshot_hash = hashlib.sha256(snap.read_bytes()).hexdigest()
            first = audit.audit(snap, base, base / 'output')
            second = audit.audit(snap, base, base / 'output')
            self.assertTrue(first['complete'])
            self.assertEqual(second['pages_inventoried'], 1)
            self.assertEqual(hashlib.sha256(snap.read_bytes()).hexdigest(), snapshot_hash)
            with shard.open('ab') as stream:
                stream.write(b'changed')
            bad = audit.audit(snap, base, base / 'different-output')
            self.assertFalse(bad['complete'])
            self.assertEqual(bad['pages_inventoried'], 0)
            self.assertIn('différent', bad['errors'][0]['error'])


if __name__ == '__main__':
    unittest.main()
