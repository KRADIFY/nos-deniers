"""Pagination, provenance and safe read-only queries on synthetic SQLite snapshots."""
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from tools.query_vectorisation_generation import query_facts, resolve_evidence


class GenerationQueryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root/'structured').mkdir()
        budget = self.root/'structured/budget.sqlite'
        con = sqlite3.connect(budget)
        con.execute('CREATE TABLE facts(year INTEGER,stage TEXT,measure TEXT,budget TEXT,mission TEXT,program TEXT,action TEXT,cents INTEGER,source TEXT,line INTEGER,field TEXT)')
        con.executemany('INSERT INTO facts VALUES(?,?,?,?,?,?,?,?,?,?,?)',
            ((2024,'EXEC','AE' if i%2 else 'CP','BG','TA','174','02',None if i==0 else 0 if i==1 else i,'sourceA' if i%2 else 'sourceB',i,'execution') for i in range(205)))
        con.commit();con.close()
        digest = hashlib.sha256(budget.read_bytes()).hexdigest()
        (self.root/'structured/active_stores.json').write_text(json.dumps({'budget':{'path':'structured/budget.sqlite','sha256':digest,'records':205}}),'utf-8')
        self.passage = 'a'*64
        con = sqlite3.connect(self.root/'catalogue.sqlite')
        con.executescript('''CREATE TABLE numeric_source_map(store TEXT,source_id TEXT,asset_sha256 TEXT,metadata_json TEXT,PRIMARY KEY(store,source_id));
            CREATE TABLE passages(id TEXT PRIMARY KEY,text TEXT,tokens INTEGER,partition TEXT,embedding_route TEXT);
            CREATE TABLE occurrences(id TEXT PRIMARY KEY,passage_id TEXT,asset_sha256 TEXT,locator TEXT,section TEXT,kind TEXT,table_ref TEXT,page_proof_json TEXT);
            CREATE TABLE refs(id TEXT PRIMARY KEY,asset_sha256 TEXT,partition TEXT,metadata_json TEXT);
            CREATE TABLE evidence(id TEXT PRIMARY KEY,asset_sha256 TEXT,locator TEXT,summary_json TEXT);''')
        for name,digest in [('sourceA','1'*64),('sourceB','2'*64)]:
            con.execute('INSERT INTO numeric_source_map VALUES(?,?,?,?)',('budget',name,digest,json.dumps({'id':name,'sha256':digest,'title':name+' title','url':'https://example.org/'+name})))
        con.execute('INSERT INTO passages VALUES(?,?,?,?,?)',(self.passage,'Montant documentaire, non certifié',10,'public','new_bge'))
        for i,digest in [(1,'1'*64),(2,'2'*64)]:
            con.execute('INSERT INTO occurrences VALUES(?,?,?,?,?,?,?,?)',(f'o{i}',self.passage,digest,f'page:{i}/table:1','section','table',f'table-{i}',json.dumps({'page':i,'source_sha256':digest})))
            con.execute('INSERT INTO refs VALUES(?,?,?,?)',(f'ref{i}',digest,'public',json.dumps({'id':'sourceA' if i==1 else 'sourceB','title':f'document{i}','years':[str(2020+i)],'stage_documentaire':'RAP'})))
            con.execute('INSERT INTO evidence VALUES(?,?,?,?)',(f'proof{i}',digest,f'page:{i}/table:1',json.dumps({'table_ref':f'table-{i}','source_shard':'example.jsonl.gz'})))
        con.commit();con.close()

    def tearDown(self):
        self.temp.cleanup()

    def test_more_than_100_facts_are_explicitly_paginated(self):
        first = query_facts(self.root,{},100,0)
        second = query_facts(self.root,{},100,100)
        last = query_facts(self.root,{},100,200)
        self.assertEqual((first['total'],first['returned'],first['next_offset']),(205,100,100))
        self.assertEqual((second['returned'],second['next_offset']),(100,200))
        self.assertEqual((last['returned'],last['next_offset'],last['has_more']),(5,None,False))
        self.assertTrue(first['truncated'])
        self.assertEqual(len({row['_observation_rowid'] for result in (first,second,last) for row in result['rows']}),205)
        self.assertFalse(first['aggregation_performed'])

    def test_null_zero_and_row_specific_sources_remain_distinct(self):
        result = query_facts(self.root,{},1000)
        by_line = {row['line']:row for row in result['rows']}
        self.assertIsNone(by_line[0]['cents'])
        self.assertEqual(by_line[1]['cents'],0)
        self.assertEqual(by_line[0]['citation']['source_sha256'],'2'*64)
        self.assertEqual(by_line[1]['citation']['source_sha256'],'1'*64)
        self.assertEqual(result['unit'],'cents')
        self.assertFalse(result['truncated'])

    def test_filter_identifiers_values_and_pagination_are_validated(self):
        for filters in ({'year OR 1=1':2024},{'measure':"AE' OR 1=1 --"},{'program':"174'; DROP TABLE facts;--"},{'year':True}):
            with self.assertRaises(ValueError):
                query_facts(self.root,filters)
        with self.assertRaises(ValueError):
            query_facts(self.root,{},offset=-1)
        result = query_facts(self.root,{'year':2024,'measure':'AE','program':'174','action':'02'})
        self.assertEqual(result['total'],102)

    def test_exact_evidence_keeps_occurrence_source_year_and_proof_separate(self):
        result = resolve_evidence(self.root,self.passage)
        self.assertEqual(result['citation_count'],2)
        one,two = result['citations']
        self.assertEqual((one['source_sha256'],one['locator'],one['documentary_years']),('1'*64,'page:1/table:1',['2021']))
        self.assertEqual((two['source_sha256'],two['locator'],two['documentary_years']),('2'*64,'page:2/table:1',['2022']))
        self.assertEqual(one['proof_ids'],['proof1'])
        self.assertEqual(two['proof_ids'],['proof2'])
        self.assertEqual(result['table_refs'],['table-1','table-2'])
        self.assertFalse(result['quality']['allow_automatic_numeric_fact'])
        self.assertFalse(result['financial_dimensions_inferred'])

    def test_readers_do_not_modify_databases_and_refuse_changed_numeric_snapshot(self):
        paths = [self.root/'catalogue.sqlite',self.root/'structured/budget.sqlite']
        before = {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        query_facts(self.root,{'mission':'TA'})
        resolve_evidence(self.root,self.passage)
        self.assertEqual(before,{p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
        self.assertFalse(list(self.root.rglob('*-wal')))
        con = sqlite3.connect(paths[1]);con.execute('UPDATE facts SET cents=999 WHERE rowid=1');con.commit();con.close()
        with self.assertRaisesRegex(ValueError,'hash mismatch'):
            query_facts(self.root,{})

    def test_missing_passage_and_invalid_identity(self):
        self.assertIsNone(resolve_evidence(self.root,'f'*64))
        with self.assertRaises(ValueError):
            resolve_evidence(self.root,"' OR 1=1 --")

    def test_parent_proofs_and_overlay_review_never_match_another_page_or_source(self):
        con = sqlite3.connect(self.root/'catalogue.sqlite')
        con.execute("UPDATE occurrences SET locator='page:3/table:recovered-1/part:1',table_ref=NULL WHERE id='o1'")
        con.execute("DELETE FROM evidence")
        refs = [{'passage_id':self.passage,'occurrence_id':'o1','table_ref':'parent-table','staged_chunk_index':2},
                {'passage_id':'f'*64,'occurrence_id':'other','table_ref':'unrelated-table'}]
        for ident,source,locator,summary in [
            ('exact','1'*64,'page:3/table:recovered-1/part:1',{}),
            ('table','1'*64,'page:3/table:recovered-1',{'table_ref':'parent-table'}),
            ('page','1'*64,'page:3',{'chunk_references':refs,'staged_document':'retained.jsonl.gz'}),
            ('wrong-page','1'*64,'page:30',{'table_ref':'bad-page'}),
            ('wrong-source','2'*64,'page:3',{'table_ref':'bad-source'})]:
            con.execute('INSERT INTO evidence VALUES(?,?,?,?)',(ident,source,locator,json.dumps(summary)))
        con.commit();con.close()
        reviews = sqlite3.connect(self.root/'page_reviews.sqlite')
        reviews.execute('CREATE TABLE page_reviews(source_sha256 TEXT,page INTEGER,status TEXT,provenance_json TEXT,PRIMARY KEY(source_sha256,page))')
        reviews.execute('CREATE TABLE page_review_evidence(source_sha256 TEXT,page INTEGER,retained_document_path TEXT,retained_record_no INTEGER,PRIMARY KEY(source_sha256,page))')
        for source,page in [('1'*64,3),('1'*64,30),('2'*64,3)]:
            reviews.execute('INSERT INTO page_reviews VALUES(?,?,?,?)',(source,page,'review_required',json.dumps({'overlay_ocr':{'source_sha256':source,'page':page,'sha256':'overlay'}})))
            reviews.execute('INSERT INTO page_review_evidence VALUES(?,?,?,?)',(source,page,'retained.jsonl.gz',page))
        reviews.commit();reviews.close()
        result = resolve_evidence(self.root,self.passage)
        proofs = [proof for proof in result['proofs'] if proof['occurrence_id']=='o1']
        self.assertEqual({p['relationship'] for p in proofs},{'exact','table','page'})
        self.assertEqual({p['id'] for p in proofs},{'exact','table','page'})
        self.assertIn('parent-table',result['table_refs'])
        self.assertNotIn('unrelated-table',result['table_refs'])
        self.assertNotIn('bad-source',result['table_refs'])
        self.assertEqual(len(result['direct_chunk_references']),1)
        review = next(c for c in result['citations'] if c['occurrence_id']=='o1')['page_review']
        self.assertEqual(review['page'],3)
        self.assertEqual(review['source_sha256'],'1'*64)
        self.assertEqual(review['provenance']['overlay_ocr']['page'],3)

    def test_raw_chunk_resolves_page_but_not_sibling_tables(self):
        con = sqlite3.connect(self.root/'catalogue.sqlite')
        con.execute("UPDATE occurrences SET locator='page:3/raw/part:2',table_ref=NULL WHERE id='o1'")
        con.execute("DELETE FROM evidence")
        con.execute('INSERT INTO evidence VALUES(?,?,?,?)',('page','1'*64,'page:3','{}'))
        con.execute('INSERT INTO evidence VALUES(?,?,?,?)',('sibling-table','1'*64,'page:3/table:recovered-1',json.dumps({'table_ref':'sibling'})))
        con.commit();con.close()
        result = resolve_evidence(self.root,self.passage)
        proof = [p for p in result['proofs'] if p['occurrence_id']=='o1']
        self.assertEqual([(p['id'],p['relationship']) for p in proof],[('page','page')])
        self.assertNotIn('sibling',result['table_refs'])


class RealMiniGenerationEvidenceTests(unittest.TestCase):
    def test_real_table_and_raw_passages_resolve_their_parent_proofs(self):
        root = Path(__file__).resolve().parents[1]/'reports/audit-vectorisation-20260911/integration-real-smoke/generation'
        if not (root/'catalogue.sqlite').exists():
            self.skipTest('Local 55-page integrated generation unavailable')
        source = 'd10eb83270533eda1014c91abe7c8d83b243ef84a51b69e614dcd4e4028b1e16'
        con = sqlite3.connect((root/'catalogue.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True)
        try:
            for kind in ('table_candidate','page_source_text'):
                row = con.execute('SELECT passage_id,locator FROM occurrences WHERE asset_sha256=? AND kind=? AND locator LIKE ? LIMIT 1',
                                  (source,kind,'page:8/%/part:%')).fetchone()
                self.assertIsNotNone(row)
                result = resolve_evidence(root,row[0])
                self.assertTrue(result['direct_chunk_references'])
                self.assertTrue(any(p['relationship']=='page' for p in result['proofs']))
                self.assertTrue(result['page_reviews'])
                self.assertTrue(all(c['source_sha256']==source for c in result['citations']))
                self.assertTrue(all(p['asset_sha256']==source for p in result['proofs']))
                if kind=='table_candidate':
                    self.assertEqual(len(result['table_refs']),1)
                    self.assertTrue(any(p['relationship']=='table' for p in result['proofs']))
        finally:
            con.close()


if __name__ == '__main__':
    unittest.main()
