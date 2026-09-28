"""Repair one proven mid-word tiling boundary, then refresh the final export.

The affected source characters are already present as ``Je`` + ``unesse`` in
two consecutive chunks.  This command moves the two characters to the second
chunk so that ``Jeunesse`` is indexed as one word.  All writes to the catalogue
use the transactional page-replacement contract.
"""

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

from tokenizers import Tokenizer

from prepare_vectorisation_release import export_input, progress
from prepare_vectorisation_tables import atomic_json
from vectorisation_page_replacement import fingerprint_page, replace_page


GENERATION = Path(r"F:\LexMachine\NosDeniers\generation_tables_20260911")
PREPARATION = Path(r"D:\LexMachine\NosDeniers\preparation_20260909")
SHA = "66ebb57757e470966aa9aee74b5432873c0c4a00306050a4f083b236c0268779"
PAGE = 3
REPLACEMENT_ID = "tiling-word-boundary-66ebb57757e4-p3-jeunesse-v1"


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def rows(connection, query, parameters=()):
    cursor = connection.execute(query, parameters)
    names = [item[0] for item in cursor.description]
    return [dict(zip(names, row)) for row in cursor]


def passage(text: str, partition: str, route: str, tokenizer: Tokenizer) -> dict:
    context, separator, body = text.partition("\n\n")
    if not separator:
        body = text
    return {
        "id": digest(partition + "\n" + route + "\n" + text),
        "partition": partition,
        "body_sha256": digest(" ".join(body.split())),
        "text": text,
        "tokens": len(tokenizer.encode(text, add_special_tokens=True).ids),
        "embedding_route": route,
    }


def repair_catalogue() -> dict:
    catalogue = GENERATION / "catalogue.sqlite"
    config = json.loads((GENERATION / "encoding_config.json").read_text(encoding="utf-8"))
    tokenizer = Tokenizer.from_file(config["tokenizer"])
    tokenizer.no_truncation()
    tokenizer.no_padding()
    connection = sqlite3.connect(catalogue)
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        if connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='vectorisation_page_replacements'"
        ).fetchone() and connection.execute(
            "SELECT 1 FROM vectorisation_page_replacements WHERE replacement_id=?", (REPLACEMENT_ID,)
        ).fetchone():
            return {"already_applied": True, "replacement_id": REPLACEMENT_ID}

        asset = connection.execute("SELECT path FROM assets WHERE sha256=?", (SHA,)).fetchone()
        if asset is None:
            raise ValueError("The affected PDF is absent from the generation")
        source_pdf = Path(asset[0])
        if file_hash(source_pdf) != SHA:
            raise ValueError("The physical source PDF fingerprint differs")

        old_occurrences = rows(
            connection,
            "SELECT o.rowid AS sequence,o.* FROM occurrences o WHERE o.asset_sha256=? "
            "AND (o.locator=? OR o.locator LIKE ?) ORDER BY o.rowid",
            (SHA, f"page:{PAGE}", f"page:{PAGE}/%"),
        )
        if len(old_occurrences) != 3:
            raise ValueError(f"Expected three ordered page chunks, found {len(old_occurrences)}")
        old_passages = []
        for occurrence in old_occurrences:
            item = rows(connection, "SELECT * FROM passages WHERE id=?", (occurrence["passage_id"],))
            if len(item) != 1:
                raise ValueError("A page passage is missing or ambiguous")
            old_passages.append(item[0])
        second_context, separator, second_body = old_passages[1]["text"].partition("\n\n")
        third_context, third_separator, third_body = old_passages[2]["text"].partition("\n\n")
        if not separator or not third_separator or not second_body.endswith("Je") or not third_body.startswith("unesse"):
            raise ValueError("The proven Je/unesse boundary is no longer present")

        corrected_texts = [
            old_passages[0]["text"],
            second_context + separator + second_body[:-2],
            third_context + third_separator + "Je" + third_body,
        ]
        new_passages = [
            passage(text, old["partition"], old["embedding_route"], tokenizer)
            for text, old in zip(corrected_texts, old_passages)
        ]
        if any(item["tokens"] > config["max_tokens_including_context"] for item in new_passages):
            raise ValueError("Corrected passage exceeds the 800-token contract")

        new_occurrences = []
        for index, (old, new) in enumerate(zip(old_occurrences, new_passages)):
            new_occurrences.append({
                "id": digest(SHA + new["partition"] + old["locator"] + old["kind"] + str(index) + new["id"]),
                "passage_id": new["id"], "asset_sha256": SHA, "locator": old["locator"],
                "section": old["section"], "kind": old["kind"],
            })
        evidence = rows(
            connection, "SELECT * FROM evidence WHERE asset_sha256=? "
            "AND (locator=? OR locator LIKE ?) ORDER BY id",
            (SHA, f"page:{PAGE}", f"page:{PAGE}/%"),
        )
        if not evidence:
            summary = {
                "kind": "tiling_boundary_correction",
                "source_sha256": SHA,
                "page": PAGE,
                "source_characters_added": 0,
                "source_characters_removed": 0,
                "boundary_before": ["Je", "unesse"],
                "boundary_after": ["", "Jeunesse"],
            }
            summary_json = json.dumps(summary, ensure_ascii=False, sort_keys=True,
                                      separators=(",", ":"))
            evidence = [{
                "id": digest(SHA + f"page:{PAGE}" + "tiling_boundary_correction" + summary_json),
                "asset_sha256": SHA, "record_no": PAGE, "locator": f"page:{PAGE}",
                "kind": "tiling_boundary_correction", "table_no": None,
                "summary_json": summary_json,
            }]
        result = replace_page(
            connection, replacement_id=REPLACEMENT_ID, asset_sha256=SHA, page=PAGE,
            verified_source_sha256=file_hash(source_pdf),
            expected_page_fingerprint=fingerprint_page(connection, SHA, PAGE),
            passages=new_passages, occurrences=new_occurrences, evidence=evidence,
            provenance={
                "reason": "Proven contiguous mid-word tiling boundary Je + unesse",
                "source_characters_added": 0, "source_characters_removed": 0,
                "affected_page": PAGE, "source_sha256": SHA,
            },
            max_tokens=config["max_tokens_including_context"], update_fts=True,
        )
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return result
    finally:
        connection.close()


def refresh_export(receipt: dict) -> dict:
    export_dir = GENERATION / "gpu_input"
    archive = GENERATION / "gpu_input_before_tiling_fix_20260912"
    archive.mkdir(exist_ok=True)
    target = export_dir / "public.bge-m3.jsonl"
    contract = export_dir / "contract.json"
    archived_target = archive / target.name
    archived_contract = archive / contract.name
    if target.exists() and contract.exists():
        current = json.loads(contract.read_text(encoding="utf-8"))
        if "tiling_correction" not in current:
            if archived_target.exists() or archived_contract.exists():
                raise ValueError("Incomplete pre-correction export archive")
            target.replace(archived_target)
            contract.replace(archived_contract)
    config = json.loads((GENERATION / "encoding_config.json").read_text(encoding="utf-8"))
    target, current = export_input(GENERATION / "catalogue.sqlite", GENERATION, config)
    current["tiling_correction"] = {
        "receipt": "tiling_correction_receipt.json",
        "replacement_id": REPLACEMENT_ID,
        "source_characters_added": 0,
        "source_characters_removed": 0,
    }
    atomic_json(contract, current)
    return {"input": str(target), "contract": str(contract), "input_count": current["input_count"],
            "input_sha256": current["input_sha256"], "pre_correction_export": str(archived_target),
            "page_replacement": receipt}


if __name__ == "__main__":
    progress(GENERATION, "repairing_proven_tiling_boundary", source_sha256=SHA, page=PAGE)
    replacement = repair_catalogue()
    receipt = refresh_export(replacement)
    atomic_json(GENERATION / "tiling_correction_receipt.json", receipt)
    progress(GENERATION, "tiling_boundary_repaired_export_refreshed",
             input_count=receipt["input_count"], input_sha256=receipt["input_sha256"])
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
