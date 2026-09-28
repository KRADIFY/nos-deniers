"""Transactional page corrections for an isolated Nos Deniers preparation DB.

No files, exports or pipelines are opened here. The caller must hold the preparation
lock, hash the source PDF, and publish a fresh export/contract only after validation.
Rows supplied below are already chunked with the existing tokenizer and context.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone


class ReplacementConflict(ValueError):
    """The source, page or replacement identity no longer matches its baseline."""


COLUMNS = {
    "passages": ("id", "partition", "body_sha256", "text", "tokens", "embedding_route"),
    "occurrences": ("id", "passage_id", "asset_sha256", "locator", "section", "kind"),
    "evidence": ("id", "asset_sha256", "record_no", "locator", "kind", "table_no", "summary_json"),
}
LEDGER = "vectorisation_page_replacements"


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _page(page):
    if type(page) is not int or page < 1:
        raise ValueError("Physical page must be a positive integer")
    return f"page:{page}"


def _rows(con, sql, parameters=()):
    cursor = con.execute(sql, parameters)
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor]


def _has_table(con, name):
    return con.execute("SELECT 1 FROM sqlite_master WHERE name=? AND type='table'", (name,)).fetchone() is not None


def _page_rows(con, table, asset_sha256, page):
    locator = _page(page)
    # The slash boundary prevents page:3 from selecting page:30 or page:31.
    return _rows(con, f"SELECT * FROM {table} WHERE asset_sha256=? "
                 "AND (locator=? OR locator LIKE ?) ORDER BY id",
                 (asset_sha256, locator, locator + "/%"))


def _page_state(con, asset_sha256, page):
    occurrences = _page_rows(con, "occurrences", asset_sha256, page)
    passage_ids = sorted({row["passage_id"] for row in occurrences})
    passages = []
    for passage_id in passage_ids:
        matches = _rows(con, "SELECT * FROM passages WHERE id=?", (passage_id,))
        if len(matches) != 1:
            raise ReplacementConflict("Page has a missing passage")
        passages.extend(matches)
    return {"asset_sha256": asset_sha256, "page": page, "occurrences": occurrences,
            "passages": passages, "evidence": _page_rows(con, "evidence", asset_sha256, page)}


def fingerprint_page(con, asset_sha256, page):
    """Hash all current page citations, text and evidence, including prior OCR fixes."""
    return _digest(_json(_page_state(con, asset_sha256, page)))


def export_passage_ids(con):
    """Yield unique public embedding IDs using the existing precedence contract.

An orphan is never exported. A shared passage stays eligible when at least one
of its occurrences belongs to a source which has not been superseded.
"""
    query = "SELECT p.id FROM passages p WHERE p.embedding_route='new_bge' AND p.partition<>'internal' "
    query += "AND EXISTS(SELECT 1 FROM occurrences o WHERE o.passage_id=p.id"
    if _has_table(con, "source_precedence"):
        query += " AND NOT EXISTS(SELECT 1 FROM source_precedence s WHERE s.old_sha256=o.asset_sha256)"
    query += ") ORDER BY p.id"
    for row in con.execute(query):
        yield row[0]


def _validated_rows(table, rows):
    result = []
    seen = set()
    for row in rows:
        if set(row) != set(COLUMNS[table]):
            raise ValueError(f"Unexpected {table} row schema")
        row = dict(row)
        if not _hash(row["id"]) or row["id"] in seen:
            raise ValueError(f"Invalid or duplicate {table} ID")
        seen.add(row["id"])
        result.append(row)
    return sorted(result, key=lambda row: row["id"])


def _insert_exact(con, table, row):
    existing = _rows(con, f"SELECT * FROM {table} WHERE id=?", (row["id"],))
    if existing:
        if existing[0] != row:
            raise ReplacementConflict(f"Conflicting {table} ID: {row['id']}")
        return
    columns = COLUMNS[table]
    con.execute(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                tuple(row[column] for column in columns))


def replace_page(con, *, replacement_id, asset_sha256, page, verified_source_sha256,
                 expected_page_fingerprint, passages, occurrences, evidence, provenance,
                 max_tokens=800, update_fts=True, compact_ledger=False, archive_references=None):
    """Replace one page atomically; a repeated identical request is a checked no-op.

``verified_source_sha256`` is the caller's freshly calculated physical PDF hash.
``expected_page_fingerprint`` comes from the immutable baseline used to prepare
the correction. A changed page (e.g. parallel HCPF repair) fails without writes.
The connection must have no open transaction. This function never commits caller
work, never changes document-level shards, and never marks a corpus GPU-ready.
"""
    if con.in_transaction:
        raise ValueError("Caller transaction must finish before page replacement")
    if not con.execute("PRAGMA foreign_keys").fetchone()[0]:
        raise ValueError("Foreign key enforcement must be enabled by the caller")
    locator = _page(page)
    if not _hash(asset_sha256) or verified_source_sha256 != asset_sha256:
        raise ReplacementConflict("Source PDF fingerprint differs")
    if not _hash(expected_page_fingerprint) or not isinstance(replacement_id, str) or not replacement_id.strip():
        raise ValueError("Replacement ID and baseline fingerprint are required")
    if not isinstance(provenance, dict) or not provenance:
        raise ValueError("Correction provenance is required")
    if type(max_tokens) is not int or max_tokens < 1:
        raise ValueError("Invalid tokenizer contract")
    if compact_ledger and (not isinstance(archive_references,dict) or
            not archive_references.get("baseline_snapshot") or not _hash(archive_references.get("baseline_sha256")) or
            not archive_references.get("staged_document") or not _hash(archive_references.get("staged_sha256"))):
        raise ValueError("A compact ledger requires immutable baseline and staged archive references")
    payload = {table: _validated_rows(table, rows) for table, rows in
               (("passages", passages), ("occurrences", occurrences), ("evidence", evidence))}
    if not payload["occurrences"] or not payload["evidence"]:
        raise ValueError("A correction requires cited content and provenance evidence")
    passage_map = {row["id"]: row for row in payload["passages"]}
    used = {row["passage_id"] for row in payload["occurrences"]}
    if used != set(passage_map):
        raise ValueError("Every supplied passage must be cited and every citation supplied")
    for row in payload["passages"]:
        if not isinstance(row["text"], str) or not row["text"].strip() or not _hash(row["body_sha256"]):
            raise ValueError("Invalid passage text or body fingerprint")
        if type(row["tokens"]) is not int or not 0 < row["tokens"] <= max_tokens:
            raise ValueError("Passage violates token limit")
        if row["embedding_route"] not in {"new_bge", "internal_hold", "existing_cour_pending_connection"}:
            raise ValueError("Unknown embedding route")
        if row["partition"] == "internal" and row["embedding_route"] != "internal_hold":
            raise ValueError("Internal passages must remain internal")
        expected_id = _digest(row["partition"] + "\n" + row["embedding_route"] + "\n" + row["text"])
        if row["id"] != expected_id:
            raise ValueError("Passage ID differs from the existing content identity contract")
    for table in ("occurrences", "evidence"):
        for row in payload[table]:
            if row["asset_sha256"] != asset_sha256 or not isinstance(row["locator"], str) or not (
                    row["locator"] == locator or row["locator"].startswith(locator + "/")):
                raise ValueError("Correction row is outside the selected source/page")
            if table == "evidence":
                json.loads(row["summary_json"])
    payload.update({"replacement_id": replacement_id, "asset_sha256": asset_sha256, "page": page,
                    "verified_source_sha256": verified_source_sha256,
                    "expected_page_fingerprint": expected_page_fingerprint,
                    "provenance": provenance, "max_tokens": max_tokens,
                    "update_fts":update_fts,"compact_ledger":compact_ledger,"archive_references":archive_references})
    payload_sha = _digest(_json(payload))
    con.execute("BEGIN IMMEDIATE")
    try:
        con.execute(f"CREATE TABLE IF NOT EXISTS {LEDGER}(replacement_id TEXT PRIMARY KEY,"
                    "asset_sha256 TEXT NOT NULL,page INTEGER NOT NULL,payload_sha256 TEXT NOT NULL,"
                    "before_sha256 TEXT NOT NULL,after_sha256 TEXT NOT NULL,before_json TEXT NOT NULL,"
                    "after_json TEXT NOT NULL,provenance_json TEXT NOT NULL,receipt_json TEXT NOT NULL,"
                    "created_at TEXT NOT NULL)")
        if not con.execute("SELECT 1 FROM assets WHERE sha256=?", (asset_sha256,)).fetchone():
            raise ReplacementConflict("Source asset is not registered")
        previous = _rows(con, f"SELECT * FROM {LEDGER} WHERE replacement_id=?", (replacement_id,))
        if previous:
            row = previous[0]
            if row["payload_sha256"] != payload_sha:
                raise ReplacementConflict("Replacement ID already belongs to a different correction")
            if fingerprint_page(con, asset_sha256, page) != row["after_sha256"]:
                raise ReplacementConflict("Previously corrected page has subsequently changed")
            result = json.loads(row["receipt_json"])
            result["already_applied"] = True
            con.commit()
            return result
        before = _page_state(con, asset_sha256, page)
        before_sha = _digest(_json(before))
        if before_sha != expected_page_fingerprint:
            raise ReplacementConflict("Page baseline changed; preserve the newer correction")
        # Validate collisions before deleting. Same IDs may legitimately survive.
        for table in COLUMNS:
            for row in payload[table]:
                found = _rows(con, f"SELECT * FROM {table} WHERE id=?", (row["id"],))
                if found and found[0] != row:
                    raise ReplacementConflict(f"Conflicting {table} ID: {row['id']}")
        # Preserve routes and partitions registered for this document.
        partitions = {row[0] for row in con.execute("SELECT DISTINCT partition FROM refs WHERE asset_sha256=?", (asset_sha256,))}
        if not partitions or any(row["partition"] not in partitions for row in payload["passages"]):
            raise ReplacementConflict("Correction changes the source partitions")
        before_routes = {(row["partition"], row["embedding_route"]) for row in before["passages"]}
        new_routes = {(row["partition"], row["embedding_route"]) for row in payload["passages"]}
        if before_routes and new_routes != before_routes:
            raise ReplacementConflict("Correction changes or drops an existing partition/embedding route")
        if not update_fts:
            con.execute("CREATE TABLE IF NOT EXISTS vectorisation_index_state(name TEXT PRIMARY KEY,dirty INTEGER NOT NULL)")
            con.execute("INSERT OR REPLACE INTO vectorisation_index_state VALUES('passages_fts',1)")
        for table in ("occurrences", "evidence"):
            con.execute(f"DELETE FROM {table} WHERE asset_sha256=? AND (locator=? OR locator LIKE ?)",
                        (asset_sha256, locator, locator + "/%"))
        for table in ("passages", "occurrences", "evidence"):
            for row in payload[table]:
                _insert_exact(con, table, row)
        old_ids = {row["id"] for row in before["passages"]}
        removed_ids = []
        for passage_id in sorted(old_ids):
            if not con.execute("SELECT 1 FROM occurrences WHERE passage_id=? LIMIT 1", (passage_id,)).fetchone():
                con.execute("DELETE FROM passages WHERE id=?", (passage_id,))
                removed_ids.append(passage_id)
        if update_fts and _has_table(con, "passages_fts"):
            for passage_id in sorted(old_ids | used):
                con.execute("DELETE FROM passages_fts WHERE passage_id=?", (passage_id,))
                con.execute("INSERT INTO passages_fts(passage_id,text) SELECT id,text FROM passages WHERE id=?", (passage_id,))
        # Foreign keys are enforced on every write. Full quick_check/FK checks
        # belong at the batch boundary, not once per page on a multi-million-row DB.
        after = _page_state(con, asset_sha256, page)
        after_sha = _digest(_json(after))
        result = {"replacement_id": replacement_id, "asset_sha256": asset_sha256, "page": page,
                  "already_applied": False, "before_sha256": before_sha, "after_sha256": after_sha,
                  "old_occurrence_ids": [row["id"] for row in before["occurrences"]],
                  "new_occurrence_ids": [row["id"] for row in payload["occurrences"]],
                  "removed_orphan_passage_ids": removed_ids, "new_passage_ids": sorted(used),
                  "retained_shared_or_unchanged_passage_ids": sorted(old_ids - set(removed_ids))}
        def ledger_state(state):
            if not compact_ledger:
                return state
            return {"asset_sha256":asset_sha256,"page":page,"archives":archive_references,
                    "occurrences":[{key:row[key] for key in ("id","passage_id","locator","kind")} for row in state["occurrences"]],
                    "passages":[{key:row[key] for key in ("id","partition","body_sha256","tokens","embedding_route")} for row in state["passages"]],
                    "evidence":[{"id":row["id"],"locator":row["locator"],"summary_sha256":_digest(row["summary_json"])} for row in state["evidence"]]}
        con.execute(f"INSERT INTO {LEDGER} VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (replacement_id, asset_sha256, page, payload_sha, before_sha, after_sha,
                     _json(ledger_state(before)), _json(ledger_state(after)), _json(provenance), _json(result),
                     datetime.now(timezone.utc).isoformat()))
        con.commit()
        return result
    except BaseException:
        con.rollback()
        raise
