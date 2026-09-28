"""Build an offline, evidence-checked vectorisation generation contract.

This module never launches an encoder. It audits CLOSED snapshot files only and
uses a disposable SQLite index in output_dir to validate an arbitrarily large
JSONL without keeping all passage IDs in RAM. Calling it scans the supplied files;
importing it does not inspect any preparation database.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import unicodedata


class ContractError(ValueError):
    pass


def _replace_file_safely(source, target):
    # Share the staging writer's bounded retry for transient Windows read locks.
    tools_path = str(Path(__file__).resolve().parent)
    inserted = tools_path not in sys.path
    if inserted:
        sys.path.insert(0, tools_path)
    try:
        from prepare_vectorisation_tables import replace_file_safely
        replace_file_safely(source, target)
    finally:
        if inserted:
            sys.path.remove(tools_path)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def artifact(path):
    path = Path(path).resolve(strict=True)
    if not path.is_file():
        raise ContractError(f"Not a file: {path}")
    before = path.stat()
    with path.open("rb") as stream:
        sha = hashlib.file_digest(stream, "sha256").hexdigest()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ContractError(f"File changed during audit: {path}")
    return {"path": str(path), "sha256": sha, "bytes": after.st_size}


def closed_snapshot(path):
    path = Path(path).resolve(strict=True)
    # Never hash just the main file of a live WAL database.
    if any(Path(str(path) + suffix).exists() for suffix in ("-wal", "-journal")):
        raise ContractError(f"Database must be a closed checkpointed snapshot: {path}")
    with path.open("rb") as stream:
        if stream.read(16) != b"SQLite format 3\x00":
            raise ContractError(f"Not a SQLite snapshot: {path}")
    con = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    return con


def _exists(con, table):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def _eligible(alias="p", precedence=True, catalogue=""):
    prefix = catalogue + "." if catalogue else ""
    query = f"{alias}.embedding_route='new_bge' AND {alias}.partition<>'internal' "
    query += f"AND EXISTS(SELECT 1 FROM {prefix}occurrences o WHERE o.passage_id={alias}.id"
    if precedence:
        query += f" AND NOT EXISTS(SELECT 1 FROM {prefix}source_precedence s WHERE s.old_sha256=o.asset_sha256)"
    return query + ")"


def audit_input(input_path, catalogue_path, work_dir, max_tokens):
    """Reject duplicate/orphan/ineligible/omitted IDs and altered text or tokens."""
    catalogue_path = Path(catalogue_path).resolve(strict=True)
    check = closed_snapshot(catalogue_path)
    try:
        if _exists(check,"vectorisation_index_state") and check.execute("SELECT 1 FROM vectorisation_index_state WHERE dirty<>0 LIMIT 1").fetchone():
            raise ContractError("Generation search index still requires its final rebuild")
        if check.execute("PRAGMA quick_check").fetchone()[0] != "ok" or check.execute("PRAGMA foreign_key_check").fetchone():
            raise ContractError("Catalogue integrity check failed")
        if check.execute("SELECT 1 FROM occurrences o LEFT JOIN passages p ON p.id=o.passage_id WHERE p.id IS NULL LIMIT 1").fetchone():
            raise ContractError("Catalogue contains an orphan citation")
        precedence = _exists(check, "source_precedence")
        routes = [dict(row) for row in check.execute("SELECT partition,embedding_route,count(*) AS count FROM passages GROUP BY partition,embedding_route ORDER BY partition,embedding_route")]
    finally:
        check.close()
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    fd = tempfile.NamedTemporaryFile(prefix="export-id-audit-", suffix=".sqlite", dir=work_dir, delete=False)
    temporary = Path(fd.name)
    fd.close()
    con = sqlite3.connect(temporary, uri=True)
    count = tokens = 0
    input_hash = hashlib.sha256()
    try:
        con.execute("CREATE TABLE submitted(id TEXT PRIMARY KEY,text_sha256 TEXT NOT NULL,tokens INTEGER NOT NULL)")
        con.execute("ATTACH DATABASE ? AS catalogue", (catalogue_path.as_uri() + "?mode=ro&immutable=1",))
        con.create_function("text_sha256", 1, digest, deterministic=True)
        with Path(input_path).open("rb") as stream:
            for number, binary in enumerate(stream, 1):
                input_hash.update(binary)
                if not binary.strip():
                    raise ContractError(f"Empty JSONL record at line {number}")
                row = json.loads(binary)
                if not isinstance(row.get("id"), str) or not isinstance(row.get("text"), str) or not row["text"].strip():
                    raise ContractError(f"Invalid input record at line {number}")
                if type(row.get("tokens")) is not int or not 0 < row["tokens"] <= max_tokens:
                    raise ContractError(f"Invalid token count at line {number}")
                if row.get("quality", {}).get("allow_automatic_numeric_fact", False) is not False:
                    raise ContractError("An extracted passage was promoted to an automatic numeric fact")
                try:
                    con.execute("INSERT INTO submitted VALUES(?,?,?)", (row["id"], digest(row["text"]), row["tokens"]))
                except sqlite3.IntegrityError as exc:
                    raise ContractError(f"Duplicate exported passage ID at line {number}") from exc
                count += 1
                tokens += row["tokens"]
                if count % 4096 == 0:
                    con.commit()
        con.commit()
        if con.execute("SELECT 1 FROM submitted s LEFT JOIN catalogue.passages p ON p.id=s.id WHERE p.id IS NULL LIMIT 1").fetchone():
            raise ContractError("Export references an absent catalogue passage")
        if con.execute("SELECT 1 FROM submitted s JOIN catalogue.passages p ON p.id=s.id WHERE s.tokens<>p.tokens OR s.text_sha256<>text_sha256(p.text) LIMIT 1").fetchone():
            raise ContractError("Exported text/tokens differ from the catalogue")
        predicate = _eligible(precedence=precedence, catalogue="catalogue")
        if con.execute("SELECT 1 FROM submitted s JOIN catalogue.passages p ON p.id=s.id WHERE NOT (" + predicate + ") LIMIT 1").fetchone():
            raise ContractError("Export contains internal, superseded or uncited content")
        expected = con.execute("SELECT count(*) FROM catalogue.passages p WHERE " + predicate).fetchone()[0]
        if expected != count:
            raise ContractError(f"Public export omission: expected {expected}, found {count}")
        return {"count": count, "tokens": tokens, "sha256": input_hash.hexdigest(),
                "expected_eligible_count": expected, "duplicate_ids": 0, "orphan_ids": 0,
                "omitted_eligible_ids": 0, "ineligible_ids": 0, "catalogue_routes": routes}
    finally:
        con.close()
        temporary.unlink(missing_ok=True)


REVIEW_STATUSES = {"structured_verified", "no_table_confirmed", "positioned_source_retained_review_required", "source_text_verified"}


def _normalize(text):
    return " ".join(unicodedata.normalize("NFC", text).split())


def _tokens(text):
    return Counter(re.findall(r"\w+(?:[.,]\w+)*|[^\w\s]", _normalize(text)))


def _verify_indexed_words(catalogue, sha, page, record):
    source_words = " ".join(str(word[4]) for word in record.get("words", []))
    if not source_words:
        source_words = " ".join(block["text"] for block in record.get("blocks", []))
    expected = _tokens(source_words)
    if not expected:
        return
    locator = f"page:{page}"
    routes = {}
    for row in catalogue.execute("SELECT p.partition,p.embedding_route,p.text FROM occurrences o JOIN passages p ON p.id=o.passage_id "
                                 "WHERE o.asset_sha256=? AND (o.locator=? OR o.locator LIKE ?)", (sha,locator,locator+"/%")):
        routes.setdefault((row["partition"],row["embedding_route"]),Counter()).update(_tokens(row["text"]))
    if not routes:
        raise ContractError("Source text is retained outside the indexed passages only")
    for route, actual in routes.items():
        if expected - actual:
            raise ContractError(f"Indexed page lost source tokens: {sha}/{page}/{route}")


def _verify_manual_ocr_overlay(catalogue,sha,page,provenance,required=False):
    locator=f"page:{page}"
    actual=[dict(row) for row in catalogue.execute("SELECT * FROM evidence WHERE asset_sha256=? AND (locator=? OR locator LIKE ?) AND kind='manual_ocr_recovery'",(sha,locator,locator+"/%"))]
    overlay=provenance.get("manual_ocr_overlay")
    if not (required or actual or overlay):
        return False
    if not isinstance(overlay,dict) or not overlay.get("passages") or not overlay.get("evidence"):
        raise ContractError("Manual OCR overlay is absent from the page provenance")
    expected={item["id"]:item["sha256"] for item in overlay["evidence"]}
    if set(expected)!={row["id"] for row in actual} or any(digest(canonical(row))!=expected[row["id"]] for row in actual):
        raise ContractError("An original manual OCR proof was lost or changed")
    expected_occurrences=set()
    for item in overlay["passages"]:
        row=catalogue.execute("SELECT o.*,p.text FROM occurrences o JOIN passages p ON p.id=o.passage_id WHERE o.id=?",(item["occurrence_id"],)).fetchone()
        if row is None or row["asset_sha256"]!=sha or row["passage_id"]!=item["passage_id"] or row["kind"]!="page_text_ocr_recovered" or row["locator"]!=item["locator"] or not (row["locator"]==locator or row["locator"].startswith(locator+"/")):
            raise ContractError("An original manual OCR citation was lost or changed")
        if digest(row["text"])!=item["text_sha256"]:
            raise ContractError("An original manual OCR text was changed")
        expected_occurrences.add(row["id"])
    actual_occurrences={row[0] for row in catalogue.execute("SELECT id FROM occurrences WHERE asset_sha256=? AND (locator=? OR locator LIKE ?) AND kind='page_text_ocr_recovered'",(sha,locator,locator+"/%"))}
    if expected_occurrences!=actual_occurrences:
        raise ContractError("Manual OCR citations are incompletely documented")
    return True


class _RetainedReader:
    """Forward-only access: each corrected gzip is opened once per source PDF."""
    def __init__(self):
        self.streams = {}
        self.artifacts = {}

    def get(self, path, number):
        path = Path(path).resolve(strict=True)
        if type(number) is not int or number < 1:
            raise ContractError("Invalid retained record number")
        if path not in self.streams:
            self.artifacts[str(path)] = artifact(path)
            self.streams[path] = [gzip.open(path,"rt",encoding="utf-8"),0,None]
        state = self.streams[path]
        if number < state[1]:
            raise ContractError("Retained records must be requested in source order")
        while state[1] < number:
            line = state[0].readline()
            if not line:
                raise ContractError("Retained document ends before the cited record")
            state[1] += 1
            state[2] = json.loads(line)
        return state[2]

    def close(self):
        for state in self.streams.values():
            state[0].close()


def audit_page_reviews(catalogue_path, review_path, extracted_root, *, expected_pdf_pages, expected_grid_alert_pages):
    """Validate complete inventory against real extraction records and their hashes.

Review snapshot tables:
  page_inventory(source_sha256,page,grid_alert,has_table), unique per source/page;
  page_reviews(source_sha256,page,status,raw_words_preserved,raw_numbers_preserved,
               header_context_preserved,numeric_fact_certified,provenance_json);
  page_review_evidence(source_sha256,page,shard_sha256,raw_record_sha256,
                       retained_record_json NULL,retained_document_path NULL,retained_record_no NULL).

The retained record is the unmodified source representation available to the
reader alongside any reconstructed tables. Comparing the whole source record
retains words, coordinates, original cells, headers and context without trusting
an aggregate 'all reviewed' flag. Financial certification remains independent.
"""
    catalogue = closed_snapshot(catalogue_path)
    reviews = closed_snapshot(review_path)
    pages = alerts = required = reviewed = needs_review = manual_ocr_pages = 0
    status_counts = {}
    shards = []
    corrected_documents = {}
    retained_reader = None
    try:
        for table in ("page_inventory", "page_reviews", "page_review_evidence"):
            if reviews.execute(f"SELECT 1 FROM {table} GROUP BY source_sha256,page HAVING count(*)<>1 LIMIT 1").fetchone():
                raise ContractError(f"Duplicate page key in {table}")
        sources = catalogue.execute("SELECT a.sha256,e.shard_sha256,e.receipt_json FROM assets a JOIN extraction e ON e.asset_sha256=a.sha256 WHERE a.kind='pdf' AND e.status='complete' ORDER BY a.sha256")
        for source in sources:
            if retained_reader is not None:
                corrected_documents.update(retained_reader.artifacts)
                retained_reader.close()
            retained_reader = _RetainedReader()
            sha = source["sha256"]
            source_receipt=json.loads(source["receipt_json"])
            known_manual_pages={item.get("page") for item in source_receipt.get("manual_quality_review",[])
                                if "recovered" in str(item.get("outcome",""))}
            shard = Path(extracted_root) / sha[:2] / (sha + ".jsonl.gz")
            proof = artifact(shard)
            if proof["sha256"] != source["shard_sha256"]:
                raise ContractError("Source extraction shard changed")
            shards.append(proof)
            source_pages = 0
            with gzip.open(shard, "rt", encoding="utf-8") as stream:
                for record_no, line in enumerate(stream,1):
                    record = json.loads(line)
                    if record.get("kind") != "page":
                        continue
                    source_pages += 1
                    page = record["page"]
                    if page != source_pages:
                        raise ContractError("Missing, repeated or unordered physical PDF page")
                    item = reviews.execute("SELECT * FROM page_inventory WHERE source_sha256=? AND page=?", (sha, page)).fetchone()
                    if item is None:
                        raise ContractError(f"Page absent from audit inventory: {sha}/{page}")
                    grid = "grid_candidate_not_resolved" in record.get("issues", [])
                    has_table = bool(record.get("tables"))
                    if item["grid_alert"] != int(grid) or item["has_table"] != int(has_table):
                        raise ContractError("Inventory flags differ from the actual source record")
                    pages += 1
                    alerts += int(grid)
                    required += int(grid or has_table)
                    review = reviews.execute("SELECT * FROM page_reviews WHERE source_sha256=? AND page=?", (sha, page)).fetchone()
                    evidence = reviews.execute("SELECT * FROM page_review_evidence WHERE source_sha256=? AND page=?", (sha, page)).fetchone()
                    if review is None or evidence is None:
                        raise ContractError(f"Required page lacks review evidence: {sha}/{page}")
                    status = review["status"]
                    if status not in REVIEW_STATUSES or review["numeric_fact_certified"] != 0:
                        raise ContractError("Unaccepted review status or automatic numeric certification")
                    if (grid or has_table) and status == "source_text_verified":
                        raise ContractError("A detected table/alert cannot be cleared as plain text")
                    if any(review[key] != 1 for key in ("raw_words_preserved", "raw_numbers_preserved", "header_context_preserved")):
                        raise ContractError("Preservation checks are incomplete")
                    provenance = json.loads(review["provenance_json"])
                    if provenance.get("source_sha256") != sha or provenance.get("page") != page or provenance.get("source_locator") != f"page:{page}":
                        raise ContractError("Source metadata is unavailable for a reviewed page")
                    manual_ocr_pages+=int(_verify_manual_ocr_overlay(catalogue,sha,page,provenance,page in known_manual_pages))
                    raw_hash = digest(canonical(record))
                    if evidence["shard_sha256"] != proof["sha256"] or evidence["raw_record_sha256"] != raw_hash:
                        raise ContractError("Page evidence does not refer to its actual source record")
                    evidence = dict(evidence)
                    if evidence.get("retained_record_json"):
                        payload = json.loads(evidence["retained_record_json"])
                    elif evidence.get("retained_document_path"):
                        retained_path = Path(evidence["retained_document_path"]).resolve(strict=True)
                        if retained_path == shard.resolve() and evidence.get("retained_record_no") == record_no:
                            payload = record
                        else:
                            payload = retained_reader.get(retained_path,evidence.get("retained_record_no"))
                    else:
                        raise ContractError("Retained source representation is unavailable")
                    retained = payload.get("record",payload)
                    if digest(canonical(retained)) != raw_hash:
                        raise ContractError("Original words, numbers, positions or headers were lost")
                    if "record" in payload:
                        segments = payload.get("raw_segments")
                        if not isinstance(segments,list) or any(not isinstance(segment,str) for segment in segments):
                            raise ContractError("Corrected record lacks actual raw text segments")
                        joined = _normalize(" ".join(segments))
                        for block in record.get("blocks",[]):
                            if _normalize(block["text"]) not in joined:
                                raise ContractError("A source block is absent from the retained raw segments")
                    _verify_indexed_words(catalogue,sha,page,record)
                    reviewed += 1
                    needs_review += int(status == "positioned_source_retained_review_required")
                    status_counts[status] = status_counts.get(status, 0) + 1
            declared = json.loads(source["receipt_json"])["counts"]["pages"]
            if source_pages != declared:
                raise ContractError("Extracted page count differs from the source receipt")
        if pages != expected_pdf_pages or alerts != expected_grid_alert_pages:
            raise ContractError("Corpus/alert page counts differ from the agreed inventory")
        if reviews.execute("SELECT count(*) FROM page_inventory").fetchone()[0] != pages:
            raise ContractError("Audit inventory contains extra pages")
        for table in ("page_reviews", "page_review_evidence"):
            if reviews.execute(f"SELECT count(*) FROM {table}").fetchone()[0] != pages:
                raise ContractError(f"Missing or surplus required reviews in {table}")
        if retained_reader is not None:
            corrected_documents.update(retained_reader.artifacts)
        return {"all_pdf_pages": pages, "grid_alert_pages": alerts, "required_review_pages": required,
                "reviewed_pages": reviewed, "omitted_pages": 0, "needs_review_pages": needs_review,
                "status_counts": status_counts, "source_shards": shards,
                "manual_ocr_overlay_pages":manual_ocr_pages,
                "retained_documents": list(corrected_documents.values()),
                "semantic_encoding_ready": True, "numeric_automation_ready": False,
                "automatically_certified_budget_facts": 0}
    finally:
        if retained_reader is not None:
            retained_reader.close()
        catalogue.close()
        reviews.close()


def build_release_manifest(config, output_dir):
    """Audit a candidate generation and write manifest.json in a new output folder.

Required config keys: catalogue, input, baseline_config, baseline_contract,
page_review_db, extracted_root, expected_pdf_pages, expected_grid_alert_pages,
active_stores (name->file), registries (9 name->file), artifact_groups with
nonempty sources/provenance/corrections file lists. No readiness override exists.
"""
    output = Path(output_dir)
    if (output / "manifest.json").exists():
        raise ContractError("Generation manifest already exists; preserve the frozen release")
    baseline = json.loads(Path(config["baseline_config"]).read_text(encoding="utf-8"))
    contract = json.loads(Path(config["baseline_contract"]).read_text(encoding="utf-8"))
    mapping = {"model": "model", "revision": "model_revision", "dimension": "dense_dimension",
               "max_tokens": "max_tokens_including_context", "dense_normalized": "dense_normalized",
               "dense_dtype": "dense_dtype", "sparse_dtype": "sparse_dtype", "colbert": "colbert"}
    for key, source_key in mapping.items():
        if contract.get(key) != baseline.get(source_key):
            raise ContractError(f"Encoding baseline differs: {key}")
    if contract.get("truncate") is not False:
        raise ContractError("Silent truncation is forbidden")
    tokenizer = artifact(baseline["tokenizer"])
    if tokenizer["sha256"] != baseline["tokenizer_sha256"]:
        raise ContractError("Tokenizer fingerprint differs")
    registries = config["registries"]
    if not isinstance(registries, dict) or len(registries) != 9 or len(set(map(str, registries.values()))) != 9:
        raise ContractError("Nine distinct registries are required")
    if not config["active_stores"]:
        raise ContractError("Active numerical stores must be identified")
    for key in ("sources", "provenance", "corrections"):
        if not config["artifact_groups"].get(key):
            raise ContractError(f"Required evidence artifacts missing: {key}")
    for database in (config["catalogue"], config["page_review_db"], *config["active_stores"].values()):
        closed_snapshot(database).close()
    file_paths = {"catalogue": config["catalogue"], "input": config["input"],
                  "baseline_config": config["baseline_config"], "baseline_contract": config["baseline_contract"],
                  "page_review_db": config["page_review_db"]}
    files = {key: artifact(path) for key, path in file_paths.items()}
    output.mkdir(parents=True, exist_ok=True)
    input_audit = audit_input(config["input"], config["catalogue"], output, contract["max_tokens"])
    if input_audit["sha256"] != files["input"]["sha256"]:
        raise ContractError("Input file changed during validation")
    page_audit = audit_page_reviews(config["catalogue"], config["page_review_db"], config["extracted_root"],
                                   expected_pdf_pages=config["expected_pdf_pages"],
                                   expected_grid_alert_pages=config["expected_grid_alert_pages"])
    for key, path in file_paths.items():
        # Hash after all readers close. A concurrent change invalidates the run.
        if key in {"catalogue","page_review_db"}:
            closed_snapshot(path).close()
        after = artifact(path)
        if after != files[key]:
            raise ContractError(f"Generation changed while auditing: {key}")
    manifest = {"version": "nos-deniers-vectorisation-generation-1", "files": files, "tokenizer": tokenizer,
                "encoding": {key: contract[key] for key in (*mapping, "truncate")},
                "active_stores": {key: artifact(path) for key, path in config["active_stores"].items()},
                "registries": {key: artifact(path) for key, path in registries.items()},
                "evidence_artifacts": {key: [artifact(path) for path in config["artifact_groups"][key]]
                                       for key in ("sources", "provenance", "corrections")},
                "input_audit": input_audit, "page_audit": page_audit,
                "semantic_encoding_ready": True, "numeric_automation_ready": False,
                "paid_compute_authorized": False, "gpu_started": False,
                "limitation": "Encoding readiness does not certify amounts or unresolved row/column relationships."}
    temporary = output / "manifest.json.partial"
    if temporary.is_symlink() or temporary.resolve().parent!=output.resolve():
        raise ContractError("Partial manifest must remain in the generation output folder")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(canonical(manifest) + "\n")
    _replace_file_safely(temporary, output / "manifest.json")
    return manifest
