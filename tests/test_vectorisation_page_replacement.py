import copy
import hashlib
import json
import sqlite3
import unittest

from tools.vectorisation_page_replacement import (
    COLUMNS, ReplacementConflict, export_passage_ids, fingerprint_page, replace_page,
)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


ASSET = digest("source PDF")
OTHER = digest("other PDF")


def passage(text, partition="public", route="new_bge"):
    return {"id": digest(partition + "\n" + route + "\n" + text), "partition": partition,
            "body_sha256": digest(text), "text": text, "tokens": 20, "embedding_route": route}


def occurrence(p, page, index=0, asset=ASSET, kind="page_text"):
    locator = f"page:{page}"
    return {"id": digest(asset + p["partition"] + locator + kind + str(index) + p["id"]),
            "passage_id": p["id"], "asset_sha256": asset, "locator": locator,
            "section": "", "kind": kind}


def evidence(page, name="old"):
    return {"id": digest(f"{ASSET}:{page}:{name}"), "asset_sha256": ASSET, "record_no": page,
            "locator": f"page:{page}/table:1", "kind": "table", "table_no": 0,
            "summary_json": json.dumps({"revision": name})}


class PageReplacementTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.execute("PRAGMA foreign_keys=ON")
        self.con.executescript("""
            CREATE TABLE assets(sha256 TEXT PRIMARY KEY,path TEXT,bytes INTEGER,kind TEXT,policy TEXT);
            CREATE TABLE refs(id TEXT PRIMARY KEY,asset_sha256 TEXT,partition TEXT,metadata_json TEXT);
            CREATE TABLE passages(id TEXT PRIMARY KEY,partition TEXT,body_sha256 TEXT,text TEXT,tokens INTEGER,embedding_route TEXT);
            CREATE TABLE occurrences(id TEXT PRIMARY KEY,passage_id TEXT REFERENCES passages(id),asset_sha256 TEXT,locator TEXT,section TEXT,kind TEXT);
            CREATE INDEX occurrences_passage ON occurrences(passage_id);
            CREATE TABLE evidence(id TEXT PRIMARY KEY,asset_sha256 TEXT,record_no INTEGER,locator TEXT,kind TEXT,table_no INTEGER,summary_json TEXT);
            CREATE TABLE source_precedence(old_sha256 TEXT PRIMARY KEY,preferred_sha256 TEXT,reason TEXT);
            CREATE VIRTUAL TABLE passages_fts USING fts5(passage_id UNINDEXED,text);
        """)
        for asset in (ASSET, OTHER):
            self.con.execute("INSERT INTO assets VALUES(?,?,?,?,?)", (asset, "untouched.pdf", 123, "pdf", "extract"))
        for partition in ("public", "internal"):
            self.con.execute("INSERT INTO refs VALUES(?,?,?,?)", (partition, ASSET, partition, "{}"))
        self.shared = passage("Shared old public text")
        self.orphan = passage("Old text exclusive to page 3")
        self.internal = passage("Private old text", "internal", "internal_hold")
        for row in (self.shared, self.orphan, self.internal):
            self.insert("passages", row)
            self.con.execute("INSERT INTO passages_fts VALUES(?,?)", (row["id"], row["text"]))
        for row in (occurrence(self.shared, 3), occurrence(self.shared, 30),
                    occurrence(self.orphan, 3, 1), occurrence(self.internal, 3), occurrence(self.internal, 30)):
            self.insert("occurrences", row)
        self.insert("evidence", evidence(3))
        self.insert("evidence", evidence(30))
        self.con.commit()
        self.new_public = passage("RAP 2024 | Programme 174 | Consommé CP | 2024 : 123 euros")
        self.new_internal = passage("Private reconstructed table", "internal", "internal_hold")
        self.args = {"replacement_id": "test-tables-v1", "asset_sha256": ASSET, "page": 3,
                     "verified_source_sha256": ASSET,
                     "expected_page_fingerprint": fingerprint_page(self.con, ASSET, 3),
                     "passages": [self.new_public, self.new_internal],
                     "occurrences": [occurrence(self.new_public, 3, kind="table_reconstructed"),
                                     occurrence(self.new_internal, 3, kind="table_reconstructed")],
                     "evidence": [evidence(3, "reconstructed")],
                     "provenance": {"method": "verified table", "source_pdf_sha256": ASSET}}

    def tearDown(self):
        self.con.close()

    def insert(self, table, row):
        self.con.execute(f"INSERT INTO {table} VALUES ({','.join('?' for _ in COLUMNS[table])})",
                         tuple(row[key] for key in COLUMNS[table]))

    def logical_dump(self):
        return list(self.con.iterdump())

    def test_shared_citations_page_30_and_internal_are_preserved(self):
        untouched = fingerprint_page(self.con, ASSET, 30)
        result = replace_page(self.con, **self.args)
        self.assertFalse(result["already_applied"])
        self.assertEqual(untouched, fingerprint_page(self.con, ASSET, 30))
        self.assertEqual(result["removed_orphan_passage_ids"], [self.orphan["id"]])
        self.assertEqual(set(result["retained_shared_or_unchanged_passage_ids"]), {self.shared["id"], self.internal["id"]})
        self.assertEqual(set(export_passage_ids(self.con)), {self.shared["id"], self.new_public["id"]})
        self.assertFalse(self.con.execute("SELECT 1 FROM passages_fts WHERE passage_id=?", (self.orphan["id"],)).fetchone())
        self.assertEqual(self.con.execute("SELECT count(*) FROM passages_fts WHERE passage_id=?", (self.shared["id"],)).fetchone()[0], 1)
        self.assertEqual(self.con.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_second_application_is_noop(self):
        replace_page(self.con, **self.args)
        before = self.logical_dump()
        self.assertTrue(replace_page(self.con, **self.args)["already_applied"])
        self.assertEqual(before, self.logical_dump())

    def test_hcpf_concurrent_correction_fails_without_writes(self):
        self.con.execute("UPDATE evidence SET summary_json=? WHERE locator='page:3/table:1'", ('{"method":"new HCPF repair"}',))
        self.con.commit()
        before = self.logical_dump()
        with self.assertRaisesRegex(ReplacementConflict, "baseline changed"):
            replace_page(self.con, **self.args)
        self.assertEqual(before, self.logical_dump())

    def test_changed_payload_cannot_reuse_replacement_id(self):
        replace_page(self.con, **self.args)
        args = copy.deepcopy(self.args)
        args["provenance"]["method"] = "other method"
        before = self.logical_dump()
        with self.assertRaisesRegex(ReplacementConflict, "different correction"):
            replace_page(self.con, **args)
        self.assertEqual(before, self.logical_dump())

    def test_idempotent_retry_does_not_override_later_page_change(self):
        replace_page(self.con, **self.args)
        self.con.execute("UPDATE evidence SET summary_json='{}' WHERE locator='page:3/table:1'")
        self.con.commit()
        with self.assertRaisesRegex(ReplacementConflict, "subsequently changed"):
            replace_page(self.con, **self.args)

    def test_late_failure_rolls_back_deletions_insertions_and_fts(self):
        self.con.execute("CREATE TRIGGER fail_new_evidence BEFORE INSERT ON evidence "
                         "WHEN NEW.locator='page:3/table:1' BEGIN SELECT RAISE(ABORT,'simulated crash'); END")
        self.con.commit()
        before = self.logical_dump()
        with self.assertRaisesRegex(sqlite3.IntegrityError, "simulated crash"):
            replace_page(self.con, **self.args)
        self.assertEqual(before, self.logical_dump())
        self.assertFalse(self.con.in_transaction)

    def test_conflicting_id_does_not_delete_existing(self):
        self.insert("passages", dict(self.new_public, tokens=21))
        self.con.commit()
        before = self.logical_dump()
        with self.assertRaisesRegex(ReplacementConflict, "Conflicting passages"):
            replace_page(self.con, **self.args)
        self.assertEqual(before, self.logical_dump())

    def test_failure_after_fts_update_rolls_back_entire_second_revision(self):
        replace_page(self.con, **self.args)
        self.con.execute("CREATE TRIGGER fail_ledger BEFORE INSERT ON vectorisation_page_replacements "
                         "BEGIN SELECT RAISE(ABORT,'crash after FTS'); END")
        self.con.commit()
        public = passage("Third revision of the reconstructed public table")
        args = copy.deepcopy(self.args)
        args.update(replacement_id="revision-2", expected_page_fingerprint=fingerprint_page(self.con, ASSET, 3),
                    passages=[public, self.new_internal],
                    occurrences=[occurrence(public, 3), occurrence(self.new_internal, 3)],
                    evidence=[evidence(3, "revision-2")])
        before = self.logical_dump()
        with self.assertRaisesRegex(sqlite3.IntegrityError, "crash after FTS"):
            replace_page(self.con, **args)
        self.assertEqual(before, self.logical_dump())

    def test_source_fingerprint_and_page_boundary_guards(self):
        args = copy.deepcopy(self.args)
        args["verified_source_sha256"] = OTHER
        with self.assertRaisesRegex(ReplacementConflict, "Source PDF"):
            replace_page(self.con, **args)
        args = copy.deepcopy(self.args)
        args["occurrences"][0]["locator"] = "page:30/table:1"
        with self.assertRaisesRegex(ValueError, "outside"):
            replace_page(self.con, **args)

    def test_internal_route_is_not_silently_dropped(self):
        args = copy.deepcopy(self.args)
        args["passages"] = [self.new_public]
        args["occurrences"] = [occurrence(self.new_public, 3)]
        with self.assertRaisesRegex(ReplacementConflict, "drops an existing"):
            replace_page(self.con, **args)

    def test_export_precedence_preserves_shared_public_passage(self):
        self.con.execute("INSERT INTO source_precedence VALUES(?,?,?)", (ASSET, OTHER, "structured preferred"))
        self.insert("occurrences", occurrence(self.shared, 1, asset=OTHER))
        self.insert("passages", passage("orphan must not be exported"))
        self.con.commit()
        self.assertEqual(list(export_passage_ids(self.con)), [self.shared["id"]])

    def test_same_text_keeps_embedding_id(self):
        args = copy.deepcopy(self.args)
        args["passages"] = [self.shared, self.internal]
        args["occurrences"] = [occurrence(self.shared, 3, kind="table_reconstructed"),
                               occurrence(self.internal, 3, kind="table_reconstructed")]
        result = replace_page(self.con, **args)
        self.assertEqual(set(result["new_passage_ids"]), {self.shared["id"], self.internal["id"]})
        self.assertEqual(set(export_passage_ids(self.con)), {self.shared["id"]})

    def test_tokens_identity_and_callers_transaction_are_guarded(self):
        for key, value in (("tokens", 801), ("id", digest("invented id"))):
            args = copy.deepcopy(self.args)
            args["passages"][0][key] = value
            with self.assertRaises(ValueError):
                replace_page(self.con, **args)
        self.con.execute("UPDATE assets SET bytes=124 WHERE sha256=?", (ASSET,))
        with self.assertRaisesRegex(ValueError, "Caller transaction"):
            replace_page(self.con, **self.args)
        self.assertTrue(self.con.in_transaction)

    def test_bulk_mode_defers_fts_and_records_only_compact_archive_references(self):
        args=copy.deepcopy(self.args)
        args.update(update_fts=False,compact_ledger=True,archive_references={
            "baseline_snapshot":"closed-baseline.sqlite","baseline_sha256":digest("baseline"),
            "staged_document":"verified-document.jsonl.gz","staged_sha256":digest("stage")})
        before_fts=self.con.execute("SELECT passage_id,text FROM passages_fts ORDER BY passage_id").fetchall()
        replace_page(self.con,**args)
        self.assertEqual(before_fts,self.con.execute("SELECT passage_id,text FROM passages_fts ORDER BY passage_id").fetchall())
        self.assertEqual(self.con.execute("SELECT dirty FROM vectorisation_index_state WHERE name='passages_fts'").fetchone()[0],1)
        before,after=self.con.execute("SELECT before_json,after_json FROM vectorisation_page_replacements").fetchone()
        self.assertNotIn(self.shared["text"],before)
        self.assertNotIn(self.new_public["text"],after)
        self.assertIn("closed-baseline.sqlite",before)
        self.assertTrue(replace_page(self.con,**args)["already_applied"])


if __name__ == "__main__":
    unittest.main()
