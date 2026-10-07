from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from budget_service import document_search
from tools.export_document_search import create_search_db


class DocumentSearchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.vector = root / 'vector.sqlite'
        self.budget = root / 'budget.sqlite'
        self.output = root / 'document-search.sqlite'
        self._create_budget()
        self._create_vector()

    def tearDown(self):
        self.temporary.cleanup()

    def _create_budget(self):
        db = sqlite3.connect(self.budget)
        db.execute('CREATE TABLE sources(id TEXT PRIMARY KEY,data TEXT NOT NULL)')
        db.execute(
            'INSERT INTO sources VALUES(?,?)',
            ('a' * 20, json.dumps({
                'sha256': '1' * 64,
                'title': 'RAP Écologie 2024',
                'url': 'https://budget.gouv.fr/rap-ecologie',
                'format': 'pdf',
            })),
        )
        db.commit()
        db.close()

    def _create_vector(self):
        db = sqlite3.connect(self.vector)
        db.executescript('''
            CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE assets(sha256 TEXT PRIMARY KEY,path TEXT,bytes INTEGER,kind TEXT,policy TEXT);
            CREATE TABLE refs(id TEXT PRIMARY KEY,asset_sha256 TEXT,partition TEXT,metadata_json TEXT);
            CREATE TABLE extraction(asset_sha256 TEXT PRIMARY KEY,status TEXT,shard_sha256 TEXT,receipt_json TEXT);
            CREATE TABLE indexed(asset_sha256 TEXT PRIMARY KEY,shard_sha256 TEXT NOT NULL);
            CREATE TABLE passages(id TEXT PRIMARY KEY,partition TEXT,body_sha256 TEXT,text TEXT,tokens INTEGER,embedding_route TEXT);
            CREATE TABLE occurrences(id TEXT PRIMARY KEY,passage_id TEXT,asset_sha256 TEXT,locator TEXT,section TEXT,kind TEXT);
            CREATE TABLE asset_quality(asset_sha256 TEXT PRIMARY KEY,source_kind TEXT,table_layout TEXT,numeric_status TEXT,allow_automatic_numeric_fact INTEGER,origin TEXT);
            CREATE TABLE source_precedence(old_sha256 TEXT PRIMARY KEY,preferred_sha256 TEXT,reason TEXT);
            CREATE VIRTUAL TABLE passages_fts USING fts5(passage_id UNINDEXED,text);
        ''')
        metadata = {
            'id': 'a' * 20,
            'title': 'RAP Écologie 2024',
            'url': 'https://budget.gouv.fr/rap-ecologie',
            'format': 'pdf',
            'years': ['2024'],
            'stage_documentaire': 'RAP',
            'local_path': r'C:\Users\Secret\private.pdf',
            'source_metadata': {'api_key': 'NE_JAMAIS_EXPORTER'},
        }
        db.execute("INSERT INTO metadata VALUES('inventory_sha256',?)", ('f' * 64,))
        db.execute("INSERT INTO assets VALUES(?,?,?,?,?)", ('1' * 64, r'C:\Users\Secret\private.pdf', 10, 'pdf', 'extract'))
        db.execute("INSERT INTO refs VALUES(?,?,?,?)", ('ref-public', '1' * 64, 'public', json.dumps(metadata)))
        db.execute("INSERT INTO extraction VALUES(?,?,?,?)", ('1' * 64, 'complete', '2' * 64, '{}'))
        db.execute("INSERT INTO indexed VALUES(?,?)", ('1' * 64, '2' * 64))
        db.execute("INSERT INTO passages VALUES(?,?,?,?,?,?)", (
            'p1', 'public', '3' * 64,
            'La réserve de précaution de la mission Écologie a été dégelée en 2024.', 14, 'new_bge',
        ))
        db.execute("INSERT INTO occurrences VALUES(?,?,?,?,?,?)", ('o1', 'p1', '1' * 64, 'page:42', '', 'page_text'))
        db.execute("INSERT INTO asset_quality VALUES(?,?,?,?,?,?)", (
            '1' * 64, 'source_pdf', 'not_certified', 'raw_not_validated_facts', 0, 'test',
        ))
        db.commit()
        db.close()

    def test_export_is_sanitized_and_searches_without_accents(self):
        result = create_search_db(self.vector, self.budget, self.output)
        self.assertEqual(result['documents'], 1)
        payload = self.output.read_bytes()
        self.assertNotIn(b'Users\\Secret', payload)
        self.assertNotIn(b'NE_JAMAIS_EXPORTER', payload)
        found = document_search.search({'q': ['reserve ecologie'], 'year': ['2024'], 'format': ['pdf']}, self.output)
        self.assertTrue(found['available'])
        self.assertEqual(found['count'], 1)
        self.assertEqual(found['items'][0]['citations'][0]['source_id'], 'a' * 20)
        self.assertEqual(found['items'][0]['citations'][0]['locator'], 'page:42')

    def test_filters_and_fts_syntax_are_bounded(self):
        create_search_db(self.vector, self.budget, self.output)
        self.assertEqual(document_search.search({'q': ['réserve'], 'year': ['2023']}, self.output)['count'], 0)
        self.assertEqual(document_search.search({'q': ['réserve" OR *']}, self.output)['count'], 0)
        with self.assertRaises(ValueError):
            document_search.search({'q': ['x' * 201]}, self.output)
        with self.assertRaises(ValueError):
            document_search.search({'q': ['écologie'], 'format': ['exe']}, self.output)

    def test_missing_index_reports_preparation_without_failure(self):
        info = document_search.search({'q': ['écologie']}, Path(self.temporary.name) / 'missing.sqlite')
        self.assertFalse(info['available'])
        self.assertEqual(info['state'], 'preparing')

    def test_incomplete_source_is_refused(self):
        db = sqlite3.connect(self.vector)
        db.execute("UPDATE extraction SET status='error'")
        db.commit()
        db.close()
        with self.assertRaisesRegex(ValueError, '1 extraction'):
            create_search_db(self.vector, self.budget, self.output)

    def test_unattempted_document_is_refused(self):
        with closing(sqlite3.connect(self.vector)) as db, db:
            db.execute("INSERT INTO assets VALUES(?,?,?,?,?)", ('4' * 64, 'pending.pdf', 10, 'pdf', 'extract'))
        with self.assertRaisesRegex(ValueError, '1 extraction'):
            create_search_db(self.vector, self.budget, self.output)
        self.assertFalse(self.output.exists())

    def test_indexing_must_be_complete_and_match_extraction(self):
        for statement in ("DELETE FROM indexed", "UPDATE indexed SET shard_sha256='obsolete'"):
            with self.subTest(statement=statement):
                with closing(sqlite3.connect(self.vector)) as db, db:
                    db.execute("INSERT OR REPLACE INTO indexed VALUES(?,?)", ('1' * 64, '2' * 64))
                    db.execute(statement)
                with self.assertRaisesRegex(ValueError, 'non indexé'):
                    create_search_db(self.vector, self.budget, self.output)

    def test_missing_quality_cannot_silently_drop_a_public_document(self):
        with closing(sqlite3.connect(self.vector)) as db, db:
            db.execute('DELETE FROM asset_quality')
        with self.assertRaisesRegex(ValueError, 'qualification de source'):
            create_search_db(self.vector, self.budget, self.output)

    def test_partial_export_is_unavailable_for_public_search(self):
        with closing(sqlite3.connect(self.vector)) as db, db:
            db.execute('DELETE FROM indexed')
        result = create_search_db(self.vector, self.budget, self.output, allow_partial=True)
        self.assertEqual(result['source_remaining_documents'], 1)
        self.assertEqual(document_search.status(self.output)['state'], 'partial')
        self.assertFalse(document_search.search({'q': ['réserve']}, self.output)['available'])


if __name__ == '__main__':
    unittest.main()
