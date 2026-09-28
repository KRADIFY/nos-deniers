import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('cour_contract', ROOT / 'tools/vectorisation_cour_contract.py')
cour = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cour)


class CourContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'cour.sqlite'
        c = sqlite3.connect(self.db)
        c.executescript('CREATE TABLE docs(doc TEXT PRIMARY KEY,title TEXT,meta TEXT); CREATE TABLE chunks(id TEXT PRIMARY KEY,doc TEXT,ord INTEGER,text TEXT,page_start INTEGER,page_end INTEGER,token_count INTEGER); CREATE VIRTUAL TABLE chunks_fts USING fts5(doc,ord,text,content=chunks,content_rowid=rowid);')
        for doc, chunk, text in [('a' * 40, '1' * 40, 'MaPrimeRénov AE 100'), ('b' * 40, '2' * 40, 'MaPrimeRénov CP 200')]:
            c.execute('INSERT INTO docs VALUES(?,?,?)', (doc, 'Test', json.dumps({'document_sha256': 'c' * 64})))
            c.execute('INSERT INTO chunks VALUES(?,?,?,?,?,?,?)', (chunk, doc, 1, text, 4, 4, 8))
        c.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")
        c.commit()
        c.close()
        self.sha = hashlib.sha256(self.db.read_bytes()).hexdigest()

    def tearDown(self):
        self.assertEqual(self.sha, hashlib.sha256(self.db.read_bytes()).hexdigest())
        self.tmp.cleanup()

    def test_resolve_exact_untruncated(self):
        r = cour.resolve('a' * 40, ['1' * 40], self.db)
        self.assertEqual(r['status'], 'resolved')
        self.assertEqual(r['hits'][0]['text'], 'MaPrimeRénov AE 100')
        self.assertFalse(r['hits'][0]['content_truncated'])

    def test_wrong_parent_blocks_every_hit(self):
        r = cour.resolve('a' * 40, ['1' * 40, '2' * 40], self.db)
        self.assertEqual(r['status'], 'parent_identity_conflict')
        self.assertEqual(r['hits'], [])

    def test_wrong_source_hash_blocks_text(self):
        r = cour.resolve('a' * 40, ['1' * 40], self.db, expected_source_sha256='d' * 64)
        self.assertEqual(r['status'], 'source_identity_conflict')
        self.assertEqual(r['hits'], [])

    def test_fts_confined_to_parent(self):
        r = cour.search_document('a' * 40, 'MaPrimeRénov', self.db)
        self.assertEqual([hit['passage_id'] for hit in r['hits']], ['1' * 40])

    def test_identity_and_output_confinement(self):
        with self.assertRaises(ValueError):
            cour.resolve("a' OR 1=1", ['1' * 40], self.db)
        with self.assertRaises(ValueError):
            cour.safe_output(Path(self.tmp.name))

    def test_held_cour_never_enters_main_generation(self):
        self.assertFalse(cour.main_export_eligible('public', cour.HELD_ROUTE))
        self.assertFalse(cour.main_export_eligible('internal', 'new_bge'))
        self.assertTrue(cour.main_export_eligible('public', 'new_bge'))
        self.assertFalse(cour.generation_contract()['paid_compute_authorized'])

    def test_optional_export_preserves_route_and_full_provenance(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'reports') as temp:
            directory = Path(temp)
            catalog = directory / 'catalog.sqlite'
            c = sqlite3.connect(catalog)
            c.executescript('CREATE TABLE passages(id TEXT,partition TEXT,body_sha256 TEXT,text TEXT,tokens INTEGER,embedding_route TEXT); CREATE TABLE occurrences(id TEXT,passage_id TEXT,asset_sha256 TEXT,locator TEXT,section TEXT,kind TEXT); CREATE TABLE refs(id TEXT,asset_sha256 TEXT,partition TEXT,metadata_json TEXT); CREATE TABLE asset_quality(asset_sha256 TEXT,table_layout TEXT); CREATE TABLE external_links(ref_id TEXT,document_id TEXT,verification TEXT);')
            c.execute('INSERT INTO passages VALUES(?,?,?,?,?,?)', ('held', 'public', 'body', 'Texte Cour', 12, cour.HELD_ROUTE))
            c.execute('INSERT INTO passages VALUES(?,?,?,?,?,?)', ('normal', 'public', 'body2', 'Autre texte', 15, 'new_bge'))
            c.execute('INSERT INTO occurrences VALUES(?,?,?,?,?,?)', ('o', 'held', 'asset', 'page:4', '', 'page_text'))
            c.execute('INSERT INTO refs VALUES(?,?,?,?)', ('r', 'asset', 'public', json.dumps({'title': 'Cour', 'years': [2025]})))
            c.execute('INSERT INTO external_links VALUES(?,?,?)', ('r', 'a' * 40, 'not_live_verified'))
            c.commit()
            c.close()
            before = hashlib.sha256(catalog.read_bytes()).hexdigest()
            result = cour.export_optional(catalog, directory / 'output')
            self.assertEqual(result['passages'], 1)
            self.assertEqual(result['recorded_tokens'], 12)
            row = json.loads((directory / 'output' / result['jsonl_file']).read_text(encoding='utf8'))
            self.assertEqual(row['embedding_route'], cour.HELD_ROUTE)
            self.assertEqual(row['provenance'][0]['locator'], 'page:4')
            self.assertEqual(row['provenance'][0]['references'][0]['cour_document_id'], 'a' * 40)
            self.assertFalse(row['included_in_main_export'])
            self.assertEqual(before, hashlib.sha256(catalog.read_bytes()).hexdigest())
            self.assertEqual(cour.export_optional(catalog, directory / 'output')['jsonl_sha256'], result['jsonl_sha256'])


if __name__ == '__main__':
    unittest.main()
