import copy
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from tools.vectorisation_release_contract import (
    ContractError, artifact, audit_input, audit_page_reviews, build_release_manifest, canonical, digest,
)


class ReleaseContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.catalogue = self.root / "catalogue.sqlite"
        self.reviews = self.root / "reviews.sqlite"
        self.source = digest("PDF source")
        self.other = digest("preferred alternative source")
        self.public = {"id": digest("public passage"), "text": "Programme 174 : montant consommé 123 euros 2024 456", "tokens": 17}
        self.private = {"id": digest("private passage"), "text": "Private note 123 euros 2024 456", "tokens": 9}
        self.superseded = {"id": digest("superseded passage"), "text": "Superseded source", "tokens": 4}
        con = sqlite3.connect(self.catalogue)
        con.executescript("""
            CREATE TABLE assets(sha256 TEXT PRIMARY KEY,kind TEXT);
            CREATE TABLE passages(id TEXT PRIMARY KEY,partition TEXT,embedding_route TEXT,text TEXT,tokens INTEGER);
            CREATE TABLE occurrences(id TEXT PRIMARY KEY,passage_id TEXT REFERENCES passages(id),asset_sha256 TEXT,locator TEXT);
            CREATE TABLE source_precedence(old_sha256 TEXT PRIMARY KEY,preferred_sha256 TEXT);
            CREATE TABLE extraction(asset_sha256 TEXT PRIMARY KEY,status TEXT,shard_sha256 TEXT,receipt_json TEXT);
            CREATE TABLE evidence(id TEXT PRIMARY KEY,asset_sha256 TEXT,record_no INTEGER,locator TEXT,kind TEXT,table_no INTEGER,summary_json TEXT);
        """)
        for index, (row, part, route, source) in enumerate(((self.public,"public","new_bge",self.source),
                (self.private,"internal","internal_hold",self.source), (self.superseded,"public","new_bge",self.other))):
            con.execute("INSERT INTO passages VALUES(?,?,?,?,?)", (row["id"],part,route,row["text"],row["tokens"]))
            con.execute("INSERT INTO occurrences VALUES(?,?,?,?)", (str(index),row["id"],source,"page:1"))
            con.execute("INSERT INTO occurrences VALUES(?,?,?,?)", (str(index)+"-2",row["id"],source,"page:2"))
        con.execute("INSERT INTO source_precedence VALUES(?,?)", (self.other,self.source))
        con.execute("INSERT INTO assets VALUES(?,?)", (self.source,"pdf"))
        self.records = [
            {"kind":"page","page":1,"words":[[1,2,3,4,"123",0,0,0]],"blocks":[{"text":"123 euros","bbox":[1,2,3,4]}],
             "tables":[],"issues":["grid_candidate_not_resolved"]},
            {"kind":"page","page":2,"words":[[1,2,3,4,"2024",0,0,0]],"blocks":[],
             "tables":[{"rows":[["2024"],["456"]],"bbox":[1,2,3,4]}],"issues":[]},
            {"kind":"page","page":3,"words":[],"blocks":[],"tables":[],"issues":[]},
        ]
        self.extracted = self.root / "extracted"
        shard = self.extracted / self.source[:2] / (self.source + ".jsonl.gz")
        shard.parent.mkdir(parents=True)
        with gzip.open(shard,"wt",encoding="utf-8") as stream:
            for record in self.records:
                stream.write(canonical(record)+"\n")
        self.shard_sha = artifact(shard)["sha256"]
        con.execute("INSERT INTO extraction VALUES(?,?,?,?)", (self.source,"complete",self.shard_sha,json.dumps({"counts":{"pages":3}})))
        con.commit()
        con.close()
        con = sqlite3.connect(self.reviews)
        con.executescript("""
            CREATE TABLE page_inventory(source_sha256 TEXT,page INTEGER,grid_alert INTEGER,has_table INTEGER,PRIMARY KEY(source_sha256,page));
            CREATE TABLE page_reviews(source_sha256 TEXT,page INTEGER,status TEXT,raw_words_preserved INTEGER,raw_numbers_preserved INTEGER,header_context_preserved INTEGER,numeric_fact_certified INTEGER,provenance_json TEXT,PRIMARY KEY(source_sha256,page));
            CREATE TABLE page_review_evidence(source_sha256 TEXT,page INTEGER,shard_sha256 TEXT,raw_record_sha256 TEXT,retained_record_json TEXT,PRIMARY KEY(source_sha256,page));
        """)
        for record in self.records:
            page=record["page"]
            con.execute("INSERT INTO page_inventory VALUES(?,?,?,?)", (self.source,page,int(bool(record["issues"])),int(bool(record["tables"]))))
            if page<=3:
                status="positioned_source_retained_review_required" if page==1 else ("structured_verified" if page==2 else "source_text_verified")
                con.execute("INSERT INTO page_reviews VALUES(?,?,?,?,?,?,?,?)", (self.source,page,status,1,1,1,0,
                            json.dumps({"source_sha256":self.source,"page":page,"source_locator":f"page:{page}"})))
                con.execute("INSERT INTO page_review_evidence VALUES(?,?,?,?,?)", (self.source,page,self.shard_sha,digest(canonical(record)),canonical(record)))
        con.commit()
        con.close()
        self.input=self.root/"input.jsonl"
        self.write_input([self.public])
        tokenizer=self.root/"tokenizer.json"
        tokenizer.write_text('{}',encoding="utf-8")
        baseline={"model":"BAAI/bge-m3","model_revision":"fixed-test-revision","dense_dimension":1024,
                  "max_tokens_including_context":800,"dense_normalized":True,"dense_dtype":"float16",
                  "sparse_dtype":"float32","colbert":False,"tokenizer":str(tokenizer),"tokenizer_sha256":artifact(tokenizer)["sha256"]}
        contract={"model":baseline["model"],"revision":baseline["model_revision"],"dimension":1024,"max_tokens":800,
                  "dense_normalized":True,"dense_dtype":"float16","sparse_dtype":"float32","colbert":False,"truncate":False}
        self.base_config=self.root/"config.json"
        self.base_config.write_text(json.dumps(baseline),encoding="utf-8")
        self.base_contract=self.root/"contract.json"
        self.base_contract.write_text(json.dumps(contract),encoding="utf-8")
        self.registries={}
        for i in range(9):
            path=self.root/f"registry-{i}.json"
            path.write_text(json.dumps({"registry":i}),encoding="utf-8")
            self.registries[str(i)]=str(path)
        self.config={"catalogue":str(self.catalogue),"input":str(self.input),"baseline_config":str(self.base_config),
                     "baseline_contract":str(self.base_contract),"page_review_db":str(self.reviews),"extracted_root":str(self.extracted),
                     "expected_pdf_pages":3,"expected_grid_alert_pages":1,"active_stores":{"facts":str(self.catalogue)},
                     "registries":self.registries,"artifact_groups":{"sources":[str(shard)],"provenance":[str(self.reviews)],"corrections":[str(self.reviews)]}}

    def tearDown(self):
        self.temp.cleanup()

    def write_input(self, rows):
        self.input.write_text(''.join(json.dumps(row,ensure_ascii=False)+"\n" for row in rows),encoding="utf-8")

    def edit_review(self, sql, args=()):
        con=sqlite3.connect(self.reviews)
        con.execute(sql,args)
        con.commit()
        con.close()

    def audit_reviews(self):
        return audit_page_reviews(self.catalogue,self.reviews,self.extracted,expected_pdf_pages=3,expected_grid_alert_pages=1)

    def test_full_manifest_preserves_ambiguity_and_never_authorizes_gpu(self):
        result=build_release_manifest(self.config,self.root/"generation")
        self.assertTrue(result["semantic_encoding_ready"])
        self.assertFalse(result["numeric_automation_ready"])
        self.assertFalse(result["paid_compute_authorized"])
        self.assertEqual(result["page_audit"]["all_pdf_pages"],3)
        self.assertEqual(result["page_audit"]["required_review_pages"],2)
        self.assertEqual(result["page_audit"]["needs_review_pages"],1)
        self.assertEqual(len(result["registries"]),9)
        self.assertEqual(result["input_audit"]["count"],1)
        self.assertFalse(list((self.root/"generation").glob('export-id-audit-*')))

    def test_duplicate_or_missing_export_ids_are_rejected(self):
        self.write_input([self.public,self.public])
        with self.assertRaisesRegex(ContractError,"Duplicate"):
            audit_input(self.input,self.catalogue,self.root,800)
        self.write_input([])
        with self.assertRaisesRegex(ContractError,"omission"):
            audit_input(self.input,self.catalogue,self.root,800)

    def test_orphan_id_and_uncited_passage_are_rejected(self):
        self.write_input([{**self.public,"id":"missing"}])
        with self.assertRaisesRegex(ContractError,"absent catalogue"):
            audit_input(self.input,self.catalogue,self.root,800)
        con=sqlite3.connect(self.catalogue)
        con.execute("DELETE FROM occurrences WHERE passage_id=?",(self.public["id"],))
        con.commit();con.close()
        self.write_input([self.public])
        with self.assertRaisesRegex(ContractError,"uncited"):
            audit_input(self.input,self.catalogue,self.root,800)

    def test_private_superseded_altered_and_overlong_records_are_rejected(self):
        for row, message in ((self.private,"internal"),(self.superseded,"superseded"),
                             ({**self.public,"text":"altered amount"},"differ"),({**self.public,"tokens":801},"token")):
            with self.subTest(message=message):
                self.write_input([row])
                with self.assertRaisesRegex(ContractError,message):
                    audit_input(self.input,self.catalogue,self.root,800)

    def test_known_table_outside_grid_alerts_must_also_be_reviewed(self):
        self.edit_review("DELETE FROM page_reviews WHERE page=2")
        with self.assertRaisesRegex(ContractError,"lacks review evidence"):
            self.audit_reviews()

    def test_manual_blanket_flags_cannot_hide_missing_number_or_position(self):
        retained=copy.deepcopy(self.records[0])
        retained["words"][0][4]="999"
        self.edit_review("UPDATE page_review_evidence SET retained_record_json=? WHERE page=1",(canonical(retained),))
        with self.assertRaisesRegex(ContractError,"were lost"):
            self.audit_reviews()

    def test_unlinked_raw_record_or_unavailable_source_metadata_fails(self):
        self.edit_review("UPDATE page_review_evidence SET raw_record_sha256='invented' WHERE page=1")
        with self.assertRaisesRegex(ContractError,"actual source record"):
            self.audit_reviews()

    def test_all_physical_pages_and_alert_flags_are_checked(self):
        self.edit_review("DELETE FROM page_inventory WHERE page=3")
        with self.assertRaisesRegex(ContractError,"absent from audit inventory"):
            self.audit_reviews()

    def test_live_wal_catalogue_is_rejected(self):
        Path(str(self.catalogue)+'-wal').write_bytes(b'live')
        with self.assertRaisesRegex(ContractError,"closed checkpointed"):
            build_release_manifest(self.config,self.root/"generation")

    def test_unrebuilt_search_index_blocks_the_final_generation(self):
        con=sqlite3.connect(self.catalogue)
        con.execute("CREATE TABLE vectorisation_index_state(name TEXT PRIMARY KEY,dirty INTEGER)")
        con.execute("INSERT INTO vectorisation_index_state VALUES('passages_fts',1)")
        con.commit();con.close()
        with self.assertRaisesRegex(ContractError,"final rebuild"):
            audit_input(self.input,self.catalogue,self.root,800)

    def test_compressed_retained_records_are_checked_once_per_document(self):
        corrected=self.root/"corrected.jsonl.gz"
        with gzip.open(corrected,"wt",encoding="utf-8") as stream:
            for record in self.records:
                stream.write(canonical({"record":record,"raw_segments":[block["text"] for block in record["blocks"]]})+"\n")
        con=sqlite3.connect(self.reviews)
        con.execute("ALTER TABLE page_review_evidence ADD COLUMN retained_document_path TEXT")
        con.execute("ALTER TABLE page_review_evidence ADD COLUMN retained_record_no INTEGER")
        con.execute("UPDATE page_review_evidence SET retained_record_json=NULL,retained_document_path=?,retained_record_no=page",(str(corrected),))
        con.commit();con.close()
        report=self.audit_reviews()
        self.assertEqual(len(report["retained_documents"]),1)
        self.assertEqual(report["reviewed_pages"],3)

    def test_unchanged_page_can_reference_its_original_immutable_shard(self):
        original=self.extracted/self.source[:2]/(self.source+".jsonl.gz")
        con=sqlite3.connect(self.reviews)
        con.execute("ALTER TABLE page_review_evidence ADD COLUMN retained_document_path TEXT")
        con.execute("ALTER TABLE page_review_evidence ADD COLUMN retained_record_no INTEGER")
        con.execute("UPDATE page_review_evidence SET retained_record_json=NULL,retained_document_path=?,retained_record_no=page",(str(original),))
        con.commit();con.close()
        report=self.audit_reviews()
        self.assertEqual(report["reviewed_pages"],3)
        self.assertEqual(len(report["source_shards"]),1)

    def test_retained_sidecar_does_not_excuse_a_lost_indexed_number(self):
        con=sqlite3.connect(self.catalogue)
        con.execute("UPDATE passages SET text=replace(text,'123','999') WHERE id=?",(self.public["id"],))
        con.commit();con.close()
        with self.assertRaisesRegex(ContractError,"Indexed page lost source tokens"):
            self.audit_reviews()

    def test_changed_model_or_missing_registry_is_rejected(self):
        value=json.loads(self.base_contract.read_text())
        value["max_tokens"]=1000
        self.base_contract.write_text(json.dumps(value))
        with self.assertRaisesRegex(ContractError,"baseline differs"):
            build_release_manifest(self.config,self.root/"generation")
        value["max_tokens"]=800
        self.base_contract.write_text(json.dumps(value))
        config=copy.deepcopy(self.config)
        config["registries"].pop('8')
        with self.assertRaisesRegex(ContractError,"Nine distinct"):
            build_release_manifest(config,self.root/"generation")

    def test_preexisting_manifest_is_never_overwritten(self):
        folder=self.root/"generation"
        folder.mkdir()
        (folder/"manifest.json").write_text('keep')
        with self.assertRaisesRegex(ContractError,"already exists"):
            build_release_manifest(self.config,folder)
        self.assertEqual((folder/"manifest.json").read_text(),'keep')

    def test_interrupted_partial_manifest_is_regenerated_only_after_audit(self):
        folder=self.root/"generation"
        folder.mkdir()
        (folder/"manifest.json.partial").write_text('interrupted partial output')
        result=build_release_manifest(self.config,folder)
        self.assertTrue(result["semantic_encoding_ready"])
        self.assertFalse((folder/"manifest.json.partial").exists())
        self.assertEqual(json.loads((folder/"manifest.json").read_text(encoding="utf-8"))["input_audit"]["count"],1)


if __name__=='__main__':
    unittest.main()
