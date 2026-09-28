from contextlib import closing
import hashlib,json,os,sqlite3,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
from budget_service import retrieval_service as r, retrieval_client as client
from budget_service.retrieval_contract import VERSION,MODEL,REVISION,DIMENSION,query_terms

class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        db=sqlite3.connect(self.root/'search.sqlite')
        db.executescript('''CREATE TABLE passages(seq INTEGER PRIMARY KEY,id TEXT,text TEXT,tokens INTEGER,text_sha256 TEXT,sparse_ids BLOB,sparse_weights BLOB);
        CREATE VIRTUAL TABLE passages_fts USING fts5(text,content=passages,content_rowid=seq);
        CREATE TABLE documents(id INTEGER PRIMARY KEY,reference_id TEXT,source_sha256 TEXT,source_id TEXT,title TEXT,url TEXT,format TEXT,years_key TEXT,stage TEXT,source_kind TEXT,table_layout TEXT,numeric_status TEXT,local_available INTEGER);
        CREATE TABLE citations(seq INTEGER,document_id INTEGER,locator TEXT);''')
        for i,(year,text,page) in enumerate([(2024,'Réserve de précaution écologie',42),(2023,'Réserve de précaution écologie',51),(2024,'Réserve de précaution écologie complément',42)],1):
            sha=hashlib.sha256(text.encode()).hexdigest()
            db.execute('INSERT INTO passages VALUES(?,?,?,?,?,?,?)',(i,str(i)*64,text,10,sha,b'',b''))
            db.execute('INSERT INTO passages_fts(rowid,text) VALUES(?,?)',(i,text))
            db.execute('INSERT INTO documents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(i,'ref'+str(i),'a'*64,'b'*20,'RAP Ecologie','https://budget.gouv.fr/rap','pdf',f'|{year}|','RAP','source_pdf','not_certified','raw',1))
            db.execute('INSERT INTO citations VALUES(?,?,?)',(i,i,f'page:{page}/raw/part:1'))
        db.commit();db.close()
        (self.root/'dense.faiss').write_bytes(b'fixture')
        m=dict(version=VERSION,state='ready',model=MODEL,revision=REVISION,dimension=DIMENSION,documents=3,passages=3,generated_at='2026-09-19',files=[dict(path=n,bytes=(self.root/n).stat().st_size) for n in ['search.sqlite','dense.faiss']])
        (self.root/'manifest.json').write_text(json.dumps(m),encoding='utf8')
        self.root_patch=patch.object(r,'ROOT',self.root);self.root_patch.start();r.manifest.cache_clear()
    def tearDown(self):
        r.manifest.cache_clear();self.root_patch.stop();self.temp.cleanup()
    def test_text_synonyms_filter_dedup_and_page_locator(self):
        found=r.search(dict(q=['gel écologie'],year=['2024'],mode=['text']))
        self.assertEqual(found['count'],1)
        self.assertEqual(found['items'][0]['citations'][0]['page'],42)
        self.assertEqual(found['items'][0]['citations'][0]['years'],[2024])
        self.assertFalse(found['numeric_facts_certified'])
        self.assertFalse(found['missing_result_is_absence_proof'])
    def test_named_scheme_remains_an_anchor_in_long_questions(self):
        from budget_service.retrieval_contract import lexical_query, mentions_mpr
        for name in ("MaPrimeRénov’", "ma prime renov", "prime de transition énergétique", "MPR"):
            self.assertTrue(mentions_mpr(name))
            self.assertIn('MaPrimeRenov', lexical_query(name + ' crédits consommés écologie 2025', hybrid=True))
        self.assertFalse(mentions_mpr('rénovation des bâtiments scolaires'))
        class Index:
            def search(self,*args):return [[1,1,1]],[[2,1,3]]
        with patch.object(r,'encode',return_value=([[0]],{})),patch.object(r,'dense_index',return_value=Index()):
            d=r.search(dict(q=['MaPrimeRénov crédits consommés'],year=['2024'],mode=['hybrid']))
        self.assertEqual(d['count'],0)  # The fixtures mention reserves, not the named scheme.

    def test_full_passage_hash_and_missing(self):
        p=r.passage('1'*64);self.assertEqual(hashlib.sha256(p['text'].encode()).hexdigest(),p['text_sha256'])
        with self.assertRaises(LookupError):r.passage('9'*64)
        with self.assertRaises(ValueError):r.passage('../manifest.json')
    def test_invalid_filters_and_fts_syntax(self):
        for q in [dict(q=['x'*201]),dict(year=['2024 OR 1=1']),dict(mode=['remote']),dict(limit=['51']),dict(format=['exe'])]:
            with self.assertRaises(ValueError):r.parameters(q)
        self.assertNotIn('*',query_terms('" OR *'))
    def test_incompatible_or_changed_index_refused(self):
        (self.root/'dense.faiss').write_bytes(b'changed-size')
        self.assertFalse(r.status()['available'])
    def test_hybrid_filters_dense_candidates_by_year(self):
        class Index:
            def search(self,*args):return [[1,1,1]],[[2,1,3]]
        with patch.object(r,'encode',return_value=([[0]],{})),patch.object(r,'dense_index',return_value=Index()):
            d=r.search(dict(q=['inconnu'],year=['2024'],mode=['hybrid']))
        self.assertEqual(d['count'],1)
        self.assertEqual(d['items'][0]['citations'][0]['years'],[2024])
        self.assertIn('dense',d['items'][0]['retrieval_methods'])
    def test_client_preserves_blank_format_and_encodes_text(self):
        with patch.object(client,'request',side_effect=lambda path:path):
            result=client.search(dict(q=['gel & réserve'],format=[''],mode=['text']))
        self.assertIn('format=&',result);self.assertIn('mode=text',result);self.assertIn('%26',result)
    def test_no_endpoint_and_upstream_busy_are_explicit(self):
        with patch.dict(os.environ,{'BUDGET_RETRIEVAL_URL':''}):self.assertFalse(client.status()['available'])
        with patch.dict(os.environ,{'BUDGET_RETRIEVAL_URL':'http://retrieval:8090'}),patch.object(client,'urlopen',side_effect=HTTPError('',503,'busy',{},None)):
            self.assertEqual(client.status()['state'],'busy')
    def test_download_requires_matching_hash_and_existing_file(self):
        (self.root/'ok.pdf').write_bytes(b'%PDF')
        source=dict(id='b'*20,sha256='a'*64,path='ok.pdf')
        from budget_service import api,topics
        with patch.object(api,'DATA',self.root),patch.object(topics,'sources',return_value=[source]):
            d={'citations':[dict(source_sha256='a'*64,source_id='',local_available=False)]}
            self.assertTrue(client.resolve_sources(d,None)['citations'][0]['local_available'])
            (self.root/'ok.pdf').unlink()
            self.assertFalse(client.resolve_sources(d,None)['citations'][0]['local_available'])
    def test_internal_lookup_errors_are_not_false_missing_documents(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),r.Handler)
        t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
        try:
            with patch.object(r,'search',side_effect=KeyError('model')),patch.object(r.logging,'exception'):
                with self.assertRaises(HTTPError) as error:urlopen(f'http://127.0.0.1:{server.server_port}/search?q=test')
                self.assertEqual(error.exception.code,503)
        finally:server.shutdown();server.server_close();t.join()

if __name__=='__main__':unittest.main()