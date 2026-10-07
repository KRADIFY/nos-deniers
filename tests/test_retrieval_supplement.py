"""Contracts for the isolated supplement and the unchanged base index."""
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import unittest
from unittest.mock import patch

from budget_service import retrieval_service as r
from tests import test_retrieval as base_tests


class SupplementTests(unittest.TestCase):
    def setUp(self):
        self.fixture = base_tests.RetrievalTests()
        self.fixture.setUp()
        self.root = self.fixture.root
        self.supplement = self.root / 'supplement'
        self.supplement.mkdir()
        for name in ['search.sqlite', 'dense.faiss', 'manifest.json']:
            shutil.copy2(self.root / name, self.supplement / name)
        base = json.loads((self.root / 'manifest.json').read_text())
        base['input_sha256'] = 'e' * 64
        (self.root / 'manifest.json').write_text(json.dumps(base))
        with sqlite3.connect(self.supplement / 'search.sqlite') as db:
            # seq=1 collides with the base sequence but identifies a new source.
            db.execute("UPDATE passages SET id=? WHERE seq=1", ('4' * 64,))
            db.execute("UPDATE documents SET source_sha256=?,source_id=? WHERE id=1", ('c' * 64, 'd' * 20))
            # seq=3 is the same source/page as the base and must be deduplicated.
            db.execute("UPDATE passages SET id=? WHERE seq=3", ('5' * 64,))
        db.close()
        self.refresh_manifest()
        self.supplement_patch = patch.object(r, 'SUPPLEMENT', self.supplement)
        self.supplement_patch.start()
        r.manifest.cache_clear()

    def refresh_manifest(self):
        manifest = json.loads((self.supplement / 'manifest.json').read_text())
        manifest['base_input_sha256'] = 'e' * 64
        for item in manifest['files']:
            data = (self.supplement / item['path']).read_bytes()
            item.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        (self.supplement / 'manifest.json').write_text(json.dumps(manifest))
        r.manifest.cache_clear()

    def tearDown(self):
        self.supplement_patch.stop()
        self.fixture.tearDown()

    def test_text_search_filters_both_indexes_and_deduplicates_source_pages(self):
        result = r.search(dict(q=['réserve écologie'], year=['2024'], format=['pdf'], mode=['text']))
        self.assertEqual(result['count'], 2)
        self.assertEqual({item['id'] for item in result['items']}, {'1' * 64, '4' * 64})
        self.assertTrue(all(cite['years'] == [2024] and cite['format'] == 'pdf'
                            for item in result['items'] for cite in item['citations']))
        self.assertEqual(r.search(dict(q=['réserve'], year=['1900'], mode=['text']))['count'], 0)
        self.assertEqual(r.search(dict(q=['réserve'], format=['csv'], mode=['text']))['count'], 0)

    def test_dense_ranks_merge_by_similarity_before_filters_and_deduplication(self):
        class Index:
            def __init__(self, scores):
                self.scores = scores
            def search(self, *args):
                return [self.scores], [[2, 1, 3]]
        def index(root=None):
            return Index([.99, .95, .7] if root else [.98, .8, .75])
        with patch.object(r, 'encode', return_value=([[0]], {})), patch.object(r, 'dense_index', side_effect=index):
            result = r.search(dict(q=['autre'], year=['2024'], mode=['hybrid']))
        self.assertEqual(result['count'], 2)
        self.assertEqual(result['items'][0]['id'], '4' * 64)
        self.assertTrue(all('dense' in item['retrieval_methods'] for item in result['items']))
        self.assertTrue(all(cite['years'] == [2024] for item in result['items'] for cite in item['citations']))

    def test_unrelated_dense_supplement_cannot_exhaust_mpr_candidate_quota(self):
        # The base target is beyond the 240 lexical results. It must still be
        # discovered through dense search behind 400 unrelated supplement hits.
        for root, count, text in [(self.root, 241, 'MPR sujet financier'),
                                  (self.supplement, 400, 'Autre sujet financier')]:
            with sqlite3.connect(root / 'search.sqlite') as db:
                db.execute('DELETE FROM passages_fts')
                for table in ['citations', 'documents', 'passages']:
                    db.execute('DELETE FROM ' + table)
                for seq in range(1, count + 1):
                    ident = hashlib.sha256((root.name + ':' + str(seq)).encode()).hexdigest()
                    digest = hashlib.sha256(text.encode()).hexdigest()
                    db.execute('INSERT INTO passages VALUES(?,?,?,?,?,?,?)',
                               (seq, ident, text, 5, digest, b'', b''))
                    db.execute('INSERT INTO passages_fts(rowid,text) VALUES(?,?)', (seq, text))
                    db.execute('INSERT INTO documents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                               (seq, 'ref' + str(seq), ident, ident[:20], 'Rapport',
                                'https://example.test/rapport', 'pdf', '|2024|', 'RAP',
                                'source_pdf', 'not_certified', 'raw', 1))
                    db.execute('INSERT INTO citations VALUES(?,?,?)', (seq, seq, 'page:1/raw/part:1'))
            db.close()
            manifest = json.loads((root / 'manifest.json').read_text(encoding='utf8'))
            manifest.update(documents=count, passages=count)
            for item in manifest['files']:
                item['bytes'] = (root / item['path']).stat().st_size
            (root / 'manifest.json').write_text(json.dumps(manifest), encoding='utf8')
        self.refresh_manifest()
        target = hashlib.sha256((self.root.name + ':241').encode()).hexdigest()
        class Index:
            def __init__(self, supplement):
                self.supplement = supplement
            def search(self, *args):
                return ([[.99] * 400], [list(range(1, 401))]) if self.supplement else ([[.8]], [[241]])
        query = dict(q=['MPR sujet précis'], year=['2024'], mode=['hybrid'], limit=['50'])
        with patch.object(r, 'encode', return_value=([[0]], {})), \
                patch.object(r, 'dense_index', side_effect=lambda root=None: Index(root is not None)):
            with patch.object(r, 'SUPPLEMENT', None):
                baseline = r.search(query)
            combined = r.search(query)
        for result in [baseline, combined]:
            found = next(item for item in result['items'] if item['id'] == target)
            self.assertIn('dense', found['retrieval_methods'])
        self.assertEqual([item['id'] for item in combined['items']],
                         [item['id'] for item in baseline['items']])

    def test_supplement_passage_preserves_text_hash_and_exact_source(self):
        passage = r.passage('4' * 64)
        self.assertEqual(hashlib.sha256(passage['text'].encode()).hexdigest(), passage['text_sha256'])
        self.assertEqual(passage['citations'][0]['source_sha256'], 'c' * 64)
        self.assertEqual(passage['citations'][0]['page'], 42)

    def test_html_citation_uses_real_anchor_without_inventing_a_page(self):
        from urllib.parse import quote
        title = 'Note 76 — réserve de précaution'
        locator = 'html:#_ftn76/section:' + quote(title, safe='') + '/chars:120-450/part:3'
        with sqlite3.connect(self.supplement / 'search.sqlite') as db:
            db.execute("UPDATE documents SET format='html',years_key='|2023|' WHERE id=1")
            db.execute('UPDATE citations SET locator=? WHERE seq=1', (locator,))
        db.close()
        self.refresh_manifest()
        citation = r.passage('4' * 64)['citations'][0]
        self.assertIsNone(citation['page'])
        self.assertEqual(citation['years'], [2023])
        self.assertEqual(citation['html_anchor'], '_ftn76')
        self.assertEqual(citation['url'], 'https://budget.gouv.fr/rap#_ftn76')
        self.assertEqual(citation['locator'], title + ' · extrait 3')
        self.assertEqual(citation['source_locator'], locator)
        result = r.search(dict(q=['réserve écologie'], year=['2023'], format=['html'], mode=['text']))
        self.assertEqual([item['id'] for item in result['items']], ['4' * 64])

    def test_second_supplement_is_searchable_without_losing_existing_sources(self):
        second = self.root / 'supplement2'
        second.mkdir()
        for name in ['search.sqlite', 'dense.faiss', 'manifest.json']:
            shutil.copy2(self.supplement / name, second / name)
        with sqlite3.connect(second / 'search.sqlite') as db:
            db.execute("UPDATE passages SET id=? WHERE seq=1", ('6' * 64,))
            db.execute("UPDATE documents SET source_sha256=?,source_id=? WHERE id=1", ('f' * 64, 'a' * 20))
        db.close()
        m = json.loads((second / 'manifest.json').read_text())
        for item in m['files']:
            data = (second / item['path']).read_bytes()
            item.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        (second / 'manifest.json').write_text(json.dumps(m))
        r.manifest.cache_clear()
        with patch.object(r, 'SUPPLEMENT2', second):
            info = r.status()
            self.assertTrue(info['available'])
            self.assertEqual(info['passages'], 9)
            self.assertEqual(info['supplement_passages'], 6)
            result = r.search(dict(q=['réserve écologie'], year=['2024'], mode=['text']))
            self.assertEqual({item['id'] for item in result['items']}, {'1' * 64, '4' * 64, '6' * 64})
            self.assertEqual(next(item for item in result['items'] if item['id'] == '6' * 64)['citations'][0]['source_sha256'], 'f' * 64)

    def test_wrong_base_generation_is_refused(self):
        path = self.supplement / 'manifest.json'
        manifest = json.loads(path.read_text())
        manifest['base_input_sha256'] = 'f' * 64
        path.write_text(json.dumps(manifest))
        r.manifest.cache_clear()
        self.assertFalse(r.status()['available'])

    def test_changed_supplement_bytes_are_refused_even_when_size_matches(self):
        (self.supplement / 'dense.faiss').write_bytes(b'FIXTURE')
        self.assertFalse(r.status()['available'])

    def test_disabling_supplement_restores_base_behavior(self):
        with patch.object(r, 'SUPPLEMENT', None):
            result = r.search(dict(q=['réserve écologie'], year=['2024'], mode=['text']))
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['items'][0]['id'], '1' * 64)


if __name__ == '__main__':
    unittest.main()
