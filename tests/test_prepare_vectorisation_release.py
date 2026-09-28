import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import prepare_vectorisation_release as release


class ReleaseControllerTests(unittest.TestCase):
    def test_copy_hash_failure_never_publishes_catalogue(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root/'source.sqlite'; destination=root/'generation'
            destination.mkdir(); source.write_bytes(b'baseline')
            with patch.object(release,'check_space'), self.assertRaisesRegex(ValueError,'differs'):
                release.copy_catalogue(source,destination,'0'*64)
            self.assertEqual(source.read_bytes(),b'baseline')
            self.assertFalse((destination/'catalogue.sqlite').exists())
            self.assertFalse((destination/'catalogue_copy_receipt.json').exists())

    def test_copy_resumption_preserves_modified_private_catalogue(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root/'source.sqlite'; destination=root/'generation'
            destination.mkdir(); source.write_bytes(b'baseline')
            sha=release.file_hash(source)
            with patch.object(release,'check_space'):
                catalogue=release.copy_catalogue(source,destination,sha)
                catalogue.write_bytes(b'corrected in private generation')
                self.assertEqual(release.copy_catalogue(source,destination,sha).read_bytes(),b'corrected in private generation')
            self.assertEqual(source.read_bytes(),b'baseline')

    def test_ocr_wait_does_not_claim_readiness(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with patch.object(release,'REMEDIATION',root/'missing.json'), self.assertRaisesRegex(ValueError,'not yet frozen'):
                release.await_ocr(root,False)
            self.assertEqual(json.loads((root/'controller_status.json').read_text())['phase'],'waiting_for_other_task_ocr_receipt')

    def test_already_built_search_is_not_rebuilt(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); db=root/'catalogue.sqlite'
            with sqlite3.connect(db) as con:
                con.executescript("CREATE TABLE passages(id TEXT,text TEXT); CREATE TABLE vectorisation_index_state(name TEXT,dirty INTEGER); INSERT INTO vectorisation_index_state VALUES('passages_fts',0); INSERT INTO passages VALUES('id','Ecologie'); CREATE VIRTUAL TABLE passages_fts USING fts5(passage_id UNINDEXED,text); INSERT INTO passages_fts VALUES('id','Ecologie');")
            con.close()
            statements=[]; connect=sqlite3.connect
            def tracked(*a,**k):
                con=connect(*a,**k); con.set_trace_callback(statements.append); return con
            with patch.object(release.sqlite3,'connect',tracked):
                release.rebuild_search(db,root)
            self.assertFalse(any('DROP TABLE' in sql for sql in statements))
            self.assertTrue(json.loads((root/'search_index_receipt.json').read_text())['passed'])

    def test_notifier_failure_is_not_reported_as_delivered(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with patch.object(release.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout='')):
                release.notify_result(root,'Fin','test')
            self.assertFalse(json.loads((root/'notification_error.json').read_text())['delivered'])
            self.assertEqual(list(root.glob('notification-*.json')),[])


if __name__=='__main__':
    unittest.main()
