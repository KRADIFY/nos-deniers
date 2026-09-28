import copy
import gzip
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest

from tools.integrate_vectorisation_tables import (
    IntegrationError, REVIEW_SCHEMA, canonical, digest, file_hash, integrate_stage, verify_payload,
)
from tools.vectorisation_page_replacement import ReplacementConflict, fingerprint_page
from tools.vectorisation_table_text import serialize_table
from tools.vectorisation_release_contract import ContractError,audit_page_reviews


class FakeTokenizer:
    truncation=None
    def encode(self,text,add_special_tokens=True):
        return SimpleNamespace(ids=list(range(len(text.split())+2)))


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.generation=self.root/"generation"
        self.generation.mkdir()
        self.stage=self.root/"stage"
        self.stage.mkdir()
        self.extracted=self.root/"extracted"
        self.source=self.root/"source.pdf"
        self.source.write_bytes(b"tiny PDF fixture whose bytes remain untouched")
        self.sha=file_hash(self.source)
        self.baseline=self.root/"baseline.sqlite"
        self.catalogue=self.generation/"catalogue.sqlite"
        self.tokenizer=FakeTokenizer()
        tokenizer_path=self.root/"tokenizer.json"
        tokenizer_path.write_text('{}')
        tools=Path(__file__).resolve().parents[1]/"tools"
        code={name:file_hash(tools/name) for name in ("prepare_vectorisation_tables.py","vectorisation_table_geometry.py","vectorisation_table_text.py")}
        self.config={"output_root":str(self.root/"active"),"tokenizer":str(tokenizer_path),
                     "tokenizer_sha256":file_hash(tokenizer_path),"max_tokens_including_context":800}
        self.contract={"version":"test-staging","code":code,"snapshot":str(self.baseline),"config":self.config}
        self.contract["contract"]=digest(canonical({"version":self.contract["version"],"code":code,"tokenizer":self.config["tokenizer_sha256"]}))
        self.records=[{"kind":"page","page":1,"words":[[0,0,1,1,"Budget",0,0,0],[1,0,2,1,"123",0,0,1],[2,0,3,1,"euros",0,0,2]],
                      "blocks":[{"text":"Budget 123 euros","bbox":[0,0,3,1]}],"tables":[],"issues":["grid_candidate_not_resolved"]},
                     {"kind":"page","page":2,"words":[[0,0,1,1,"Texte",0,0,0]],"blocks":[{"text":"Texte conservé","bbox":[0,0,1,1]}],"tables":[],"issues":[]}]
        self.shard=self.extracted/self.sha[:2]/(self.sha+".jsonl.gz")
        self.shard.parent.mkdir(parents=True)
        with gzip.open(self.shard,"wt",encoding="utf-8") as stream:
            for record in self.records:
                stream.write(canonical(record)+"\n")
        self.shard_sha=file_hash(self.shard)
        con=sqlite3.connect(self.baseline)
        con.executescript("""
            CREATE TABLE assets(sha256 TEXT PRIMARY KEY,path TEXT,bytes INTEGER,kind TEXT,policy TEXT);
            CREATE TABLE refs(id TEXT PRIMARY KEY,asset_sha256 TEXT,partition TEXT,metadata_json TEXT);
            CREATE TABLE passages(id TEXT PRIMARY KEY,partition TEXT,body_sha256 TEXT,text TEXT,tokens INTEGER,embedding_route TEXT);
            CREATE TABLE occurrences(id TEXT PRIMARY KEY,passage_id TEXT REFERENCES passages(id),asset_sha256 TEXT,locator TEXT,section TEXT,kind TEXT);
            CREATE TABLE evidence(id TEXT PRIMARY KEY,asset_sha256 TEXT,record_no INTEGER,locator TEXT,kind TEXT,table_no INTEGER,summary_json TEXT);
            CREATE TABLE extraction(asset_sha256 TEXT PRIMARY KEY,status TEXT,shard_sha256 TEXT,receipt_json TEXT);
            CREATE TABLE indexed(asset_sha256 TEXT PRIMARY KEY,shard_sha256 TEXT);
            CREATE VIRTUAL TABLE passages_fts USING fts5(passage_id UNINDEXED,text);
        """)
        con.execute("INSERT INTO assets VALUES(?,?,?,?,?)",(self.sha,str(self.source),self.source.stat().st_size,"pdf","extract"))
        con.execute("INSERT INTO extraction VALUES(?,?,?,?)",(self.sha,"complete",self.shard_sha,canonical({"counts":{"pages":2}})))
        con.execute("INSERT INTO indexed VALUES(?,?)",(self.sha,self.shard_sha))
        self.old_ids=[]
        for part,route in (("public","new_bge"),("internal","internal_hold")):
            con.execute("INSERT INTO refs VALUES(?,?,?,?)",(part,self.sha,part,"{}"))
            text="Budget 123 euros. Texte conservé."
            pid=digest(part+"\n"+route+"\n"+text)
            self.old_ids.append(pid)
            con.execute("INSERT INTO passages VALUES(?,?,?,?,?,?)",(pid,part,digest(text),text,10,route))
            con.execute("INSERT INTO passages_fts VALUES(?,?)",(pid,text))
            for page in (1,2,10):
                con.execute("INSERT INTO occurrences VALUES(?,?,?,?,?,?)",
                            (digest(part+str(page)),pid,self.sha,f"page:{page}","","page_text"))
        con.execute("INSERT INTO evidence VALUES(?,?,?,?,?,?,?)",(digest("old evidence"),self.sha,1,"page:1","page",None,"{}"))
        con.commit()
        target=sqlite3.connect(self.catalogue)
        con.backup(target)
        target.close();con.close()
        body="Budget 123 euros"
        rawtext="Source originale\n\n"+body
        raw={"text":rawtext,"body":body,"tokens":len(self.tokenizer.encode(rawtext).ids),"locator":"page:1/raw/part:1","kind":"page_source_text",
             "segments":[{"block":0,"char_start":0,"char_end":len(body),"text":body}]}
        table=serialize_table({"rows":[["2024","123"]]}, {"source_sha256":self.sha,"page":1,"table_id":"recovered-1"}, self.tokenizer)
        table_chunks=[chunk|{"kind":"table_candidate"} for chunk in table["chunks"]]
        self.payloads=[{"page":1,"raw_record_sha256":digest(canonical(self.records[0])),"grid_alert":1,"has_table":0,"review_required":True,
                        "record":self.records[0],"status":"positioned_source_retained_review_required","raw_segments":[body],
                        "chunks":[raw]+table_chunks,"tables":[table["raw_table"]],"numeric_fact_certified":False,"allow_automatic_numeric_fact":False},
                       {"page":2,"raw_record_sha256":digest(canonical(self.records[1])),"grid_alert":0,"has_table":0,"review_required":False}]
        self.staged=self.stage/"documents"/(self.sha+".jsonl.gz")
        self.staged.parent.mkdir()
        self.write_stage()
        (self.stage/"staging_contract.json").write_text(canonical(self.contract),encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def write_stage(self):
        with gzip.open(self.staged,"wt",encoding="utf-8") as stream:
            for payload in self.payloads:
                stream.write(canonical(payload)+"\n")
        self.receipt={"source_sha256":self.sha,"source_shard_sha256":self.shard_sha,"source_pdf":str(self.source),"file":str(self.staged),
                      "sha256":file_hash(self.staged),"bytes":self.staged.stat().st_size,"contract":self.contract["contract"],"pages":2}
        (self.stage/"receipts.json").write_text(canonical([self.receipt]),encoding="utf-8")

    def run_integration(self,**changes):
        args={"generation_root":self.generation,"catalogue":self.catalogue,"stage_root":self.stage,
              "source_extracted_root":self.extracted,"tokenizer":self.tokenizer}
        return integrate_stage(**(args|changes))

    def test_two_pages_shared_partitions_table_refs_and_exact_boundary(self):
        con=sqlite3.connect(self.catalogue)
        unchanged=fingerprint_page(con,self.sha,2)
        boundary=fingerprint_page(con,self.sha,10)
        con.close()
        source_before=file_hash(self.source)
        baseline_before=file_hash(self.baseline)
        result=self.run_integration()
        self.assertEqual(result["documents"][0]["replaced_pages"],1)
        self.assertFalse(result["gpu_launched"])
        con=sqlite3.connect(self.catalogue)
        self.assertEqual(fingerprint_page(con,self.sha,2),unchanged)
        self.assertEqual(fingerprint_page(con,self.sha,10),boundary)
        self.assertEqual(set(row[0] for row in con.execute("SELECT DISTINCT partition FROM passages")),{"public","internal"})
        self.assertEqual(con.execute("SELECT count(*) FROM evidence WHERE kind='table_candidate'").fetchone()[0],1)
        summary=json.loads(con.execute("SELECT summary_json FROM evidence WHERE kind='table_candidate'").fetchone()[0])
        self.assertEqual(summary["table_ref"],self.payloads[0]["tables"][0]["table_ref"])
        self.assertFalse(summary["numeric_fact_certified"])
        self.assertEqual(con.execute("SELECT dirty FROM vectorisation_index_state").fetchone()[0],0)
        self.assertEqual(con.execute("SELECT count(*) FROM passages_fts").fetchone()[0],con.execute("SELECT count(*) FROM passages").fetchone()[0])
        con.close()
        reviews=sqlite3.connect(self.generation/"page_reviews.sqlite")
        self.assertEqual(reviews.execute("SELECT count(*) FROM page_reviews").fetchone()[0],2)
        self.assertEqual(reviews.execute("SELECT retained_document_path FROM page_review_evidence WHERE page=2").fetchone()[0],str(self.shard))
        reviews.close()
        self.assertEqual(source_before,file_hash(self.source))
        self.assertEqual(baseline_before,file_hash(self.baseline))
        status=json.loads((self.generation/"integration_progress.json").read_text(encoding="utf-8"))
        self.assertEqual(status["phase"],"integration_complete_gate_pending")
        self.assertEqual(status["documents_completed"],1)
        self.assertEqual(status["pages_reviewed"],2)
        self.assertEqual(status["pages_replaced"],1)

    def test_completed_document_resume_does_not_change_catalogue(self):
        self.run_integration()
        before=file_hash(self.catalogue)
        second=self.run_integration()
        self.assertTrue(second["documents"][0]["already_integrated"])
        self.assertEqual(before,file_hash(self.catalogue))

    def test_stage_hash_change_rolls_back_before_page_change(self):
        self.staged.write_bytes(self.staged.read_bytes()+b"changed")
        before=file_hash(self.catalogue)
        with self.assertRaisesRegex(IntegrationError,"receipt/code contract"):
            self.run_integration()
        self.assertEqual(before,file_hash(self.catalogue))

    def test_hcpf_change_in_catalogue_is_preserved(self):
        con=sqlite3.connect(self.catalogue)
        con.execute("UPDATE evidence SET summary_json='new HCPF correction'")
        con.commit();con.close()
        before=file_hash(self.catalogue)
        with self.assertRaisesRegex(ReplacementConflict,"baseline changed"):
            self.run_integration()
        self.assertEqual(before,file_hash(self.catalogue))

    def test_resume_after_catalogue_commit_but_before_review_commit(self):
        reviews=sqlite3.connect(self.generation/"page_reviews.sqlite")
        reviews.executescript(REVIEW_SCHEMA)
        reviews.execute("CREATE TRIGGER fail_review BEFORE INSERT ON page_reviews BEGIN SELECT RAISE(ABORT,'simulated review interruption'); END")
        reviews.commit();reviews.close()
        with self.assertRaisesRegex(sqlite3.IntegrityError,"simulated review interruption"):
            self.run_integration()
        con=sqlite3.connect(self.catalogue)
        self.assertEqual(con.execute("SELECT count(*) FROM vectorisation_page_replacements").fetchone()[0],1)
        con.close()
        reviews=sqlite3.connect(self.generation/"page_reviews.sqlite")
        reviews.execute("DROP TRIGGER fail_review")
        reviews.commit();reviews.close()
        self.run_integration()
        con=sqlite3.connect(self.catalogue)
        self.assertEqual(con.execute("SELECT count(*) FROM vectorisation_page_replacements").fetchone()[0],1)
        con.close()

    def test_raw_character_loss_is_rejected_even_with_rehashed_stage(self):
        self.payloads[0]["chunks"][0]["segments"][0]["text"]="Budget 999 euros"
        self.write_stage()
        before=file_hash(self.catalogue)
        with self.assertRaisesRegex(IntegrationError,"Raw chunk body"):
            self.run_integration()
        self.assertEqual(before,file_hash(self.catalogue))

    def test_source_snapshot_cannot_be_used_as_target(self):
        with self.assertRaisesRegex(IntegrationError,"existing catalogue copy"):
            self.run_integration(generation_root=self.root,catalogue=self.baseline)

    def test_hardlinked_copy_is_rejected_before_any_mutation(self):
        alias=self.generation/"hardlinked-catalogue.sqlite"
        os.link(self.baseline,alias)
        before=file_hash(self.baseline)
        with self.assertRaisesRegex(IntegrationError,"hard link"):
            self.run_integration(catalogue=alias)
        self.assertEqual(before,file_hash(self.baseline))

    def install_manual_ocr_fixture(self):
        self.records[1].update(words=[[0,0,1,1,"2",0,0,0]],blocks=[{"text":"2","bbox":[0,0,1,1]}],issues=["image_page_without_recoverable_text"])
        self.payloads[1]["raw_record_sha256"]=digest(canonical(self.records[1]))
        with gzip.open(self.shard,"wt",encoding="utf-8") as stream:
            for record in self.records:
                stream.write(canonical(record)+"\n")
        self.shard_sha=file_hash(self.shard)
        text="Texte OCR contrôlé conservé à l’identique ; aucune coordonnée n’est supposée."
        pid=digest("public\nnew_bge\n"+text)
        oid=digest("manual OCR occurrence")
        proof=digest("manual OCR evidence")
        self.manual={"passage_id":pid,"text":text,"occurrence_id":oid,"evidence_id":proof}
        for path in (self.baseline,self.catalogue):
            con=sqlite3.connect(path)
            con.execute("DELETE FROM occurrences WHERE locator='page:2' AND passage_id IN (SELECT id FROM passages WHERE partition='public')")
            con.execute("INSERT INTO passages VALUES(?,?,?,?,?,?)",(pid,"public",digest(text),text,len(self.tokenizer.encode(text).ids),"new_bge"))
            con.execute("INSERT INTO occurrences VALUES(?,?,?,?,?,?)",(oid,pid,self.sha,"page:2","","page_text_ocr_recovered"))
            con.execute("INSERT INTO passages_fts VALUES(?,?)",(pid,text))
            con.execute("INSERT INTO evidence VALUES(?,?,?,?,?,?,?)",(proof,self.sha,2,"page:2","manual_ocr_recovery",None,
                canonical({"source_pdf_sha256":self.sha,"method":"ocr_fra_eng_sparse_region","raw_ocr_sha256":digest(text)})))
            con.execute("UPDATE extraction SET shard_sha256=?,receipt_json=?",(self.shard_sha,canonical({"counts":{"pages":2},"manual_quality_review":[{"page":2,"outcome":"text_recovered_by_sparse_region_ocr"}]})))
            con.execute("UPDATE indexed SET shard_sha256=?",(self.shard_sha,))
            con.commit();con.close()
        self.write_stage()

    def test_native_remainder_and_original_manual_ocr_are_both_retained(self):
        self.install_manual_ocr_fixture()
        before=sqlite3.connect(self.catalogue)
        original_proof=before.execute("SELECT * FROM evidence WHERE id=?",(self.manual["evidence_id"],)).fetchone()
        before.close()
        result=self.run_integration()
        con=sqlite3.connect(self.catalogue)
        self.assertEqual(con.execute("SELECT text FROM passages WHERE id=?",(self.manual["passage_id"],)).fetchone()[0],self.manual["text"])
        self.assertEqual(con.execute("SELECT * FROM evidence WHERE id=?",(self.manual["evidence_id"],)).fetchone(),original_proof)
        self.assertTrue(con.execute("SELECT 1 FROM occurrences WHERE locator LIKE 'page:2/raw/%'").fetchone())
        con.close()
        audit=audit_page_reviews(self.catalogue,result["page_review_db"],self.extracted,expected_pdf_pages=2,expected_grid_alert_pages=1)
        self.assertEqual(audit["manual_ocr_overlay_pages"],1)
        self.assertTrue(self.run_integration()["documents"][0]["already_integrated"])

    def test_gate_detects_lost_original_ocr_even_with_native_word_present(self):
        self.install_manual_ocr_fixture()
        result=self.run_integration()
        con=sqlite3.connect(self.catalogue)
        con.execute("UPDATE passages SET text='texte remplacé' WHERE id=?",(self.manual["passage_id"],))
        con.commit();con.close()
        with self.assertRaisesRegex(ContractError,"manual OCR text was changed"):
            audit_page_reviews(self.catalogue,result["page_review_db"],self.extracted,expected_pdf_pages=2,expected_grid_alert_pages=1)

    def test_gate_detects_missing_original_ocr_proof(self):
        self.install_manual_ocr_fixture()
        result=self.run_integration()
        con=sqlite3.connect(self.catalogue)
        con.execute("DELETE FROM evidence WHERE id=?",(self.manual["evidence_id"],))
        con.commit();con.close()
        with self.assertRaisesRegex(ContractError,"manual OCR proof was lost"):
            audit_page_reviews(self.catalogue,result["page_review_db"],self.extracted,expected_pdf_pages=2,expected_grid_alert_pages=1)


if __name__=="__main__":
    unittest.main()
