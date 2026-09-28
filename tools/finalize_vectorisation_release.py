"""Finish an interrupted Nos Deniers generation after its export is complete.

This recovery command audits the existing F: generation and writes only its
manifest and handoff receipt.  It deliberately never stages, re-integrates or
re-exports PDF content.
"""

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":")) + "\n", encoding="utf-8")
    temporary.replace(path)


def require(path: Path) -> Path:
    if not path.is_file():
        raise FileNotFoundError(f"Required generation artifact is missing: {path}")
    return path


def run(root: Path, preparation: Path) -> dict:
    root = root.resolve()
    preparation = preparation.resolve()
    frozen = root / "frozen" / "manifest.json"
    if frozen.exists():
        return {"status": "already_frozen", "manifest": str(frozen)}

    runtime_manifest = json.loads(require(root / "runtime_manifest.json").read_text(encoding="utf-8"))
    for name, item in runtime_manifest.items():
        artifact = require(Path(item["path"]))
        if sha256(artifact) != item["sha256"]:
            raise ValueError(f"Frozen runtime changed: {name}")

    runtime = root / "runtime"
    sys.path.insert(0, str(runtime))
    from vectorisation_release_contract import build_release_manifest

    catalogue = require(root / "catalogue.sqlite")
    input_path = require(root / "gpu_input" / "public.bge-m3.jsonl")
    final_contract = require(root / "gpu_input" / "contract.json")
    baseline = require(root / "encoding_config.json")
    receipt = json.loads(require(root / "table_integration_receipt.json").read_text(encoding="utf-8"))
    page_reviews = require(Path(receipt["page_review_db"]))
    stores = json.loads(require(root / "structured" / "active_stores.json").read_text(encoding="utf-8"))
    active_stores = {
        name: str(require(root / item["path"]))
        for name, item in stores.items()
        if isinstance(item, dict) and item.get("path", "").endswith(".sqlite")
    }
    if not active_stores:
        raise ValueError("No active structured stores were found")

    with sqlite3.connect(f"file:{catalogue.as_posix()}?mode=ro", uri=True) as connection:
        registries = {
            row[0]: str(require(root / row[1]))
            for row in connection.execute(
                "SELECT registry_key, relative_path FROM numeric_registry_versions"
            )
        }
    if len(registries) != 9:
        raise ValueError(f"Expected nine registries, found {len(registries)}")

    evidence = {
        "sources": [root / "source_ocr_receipt.json", root / "catalogue_copy_receipt.json"],
        "provenance": [root / "table_integration_receipt.json", root / "numeric_addendum_receipt.json"],
        "corrections": [
            preparation / "tables_revision_20260911" / "receipts.json",
            preparation / "tables_revision_20260911" / "staging_contract.json",
            root / "runtime_manifest.json",
            root / "search_index_receipt.json",
            root / "tiling_correction_receipt.json",
        ],
    }
    for paths in evidence.values():
        for path in paths:
            require(path)

    config = {
        "catalogue": str(catalogue), "input": str(input_path),
        "baseline_config": str(baseline), "baseline_contract": str(final_contract),
        "page_review_db": str(page_reviews), "extracted_root": str(preparation / "extracted"),
        "expected_pdf_pages": 322172, "expected_grid_alert_pages": 94764,
        "active_stores": active_stores, "registries": registries,
        "artifact_groups": {key: [str(path) for path in paths] for key, paths in evidence.items()},
    }
    atomic_json(root / "manifest_config.json", config)
    manifest = build_release_manifest(config, root / "frozen")
    handoff = {
        "generation_root": str(root), "manifest": str(frozen), "input": str(input_path),
        "catalogue": str(catalogue), "page_reviews": str(page_reviews),
        "replaces_for_next_encoding": str(preparation / "gpu_input" / "public.bge-m3.jsonl"),
        "original_export_deleted": False, "launch_authorized": False,
        "note": "Do not mix passage IDs from the old and corrected exports. Use this generation as one bound set.",
    }
    atomic_json(root / "HANDOFF.json", handoff)
    return {"status": "generation_verified", "manifest": str(frozen),
            "input": str(input_path), "input_count": manifest["input_audit"]["records"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--generation", type=Path, required=True)
    parser.add_argument("--preparation", type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(run(arguments.generation, arguments.preparation), ensure_ascii=False, sort_keys=True))
