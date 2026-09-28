"""Publish the user-accepted incremental RunPod handoff after one page fix.

The user explicitly waived a second full scan after the complete deterministic
export was refreshed for a single proven word-boundary correction.  This receipt
does not claim that the abandoned second pass completed.
"""

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(r"F:\LexMachine\NosDeniers\generation_tables_20260911")
PREPARATION = Path(r"D:\LexMachine\NosDeniers\preparation_20260909")


def artifact(path: Path, known_sha256=None) -> dict:
    if not path.is_file():
        raise FileNotFoundError(path)
    result = {"path": str(path.resolve()), "bytes": path.stat().st_size}
    if known_sha256 is not None:
        result["sha256"] = known_sha256
    return result


def hash_small(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":")) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> dict:
    input_path = ROOT / "gpu_input" / "public.bge-m3.jsonl"
    contract_path = ROOT / "gpu_input" / "contract.json"
    correction_path = ROOT / "tiling_correction_receipt.json"
    catalogue = ROOT / "catalogue.sqlite"
    page_reviews = ROOT / "page_reviews.sqlite"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    correction = json.loads(correction_path.read_text(encoding="utf-8"))
    if contract.get("input_count") != 4051433:
        raise ValueError("Unexpected corrected input count")
    if correction.get("input_sha256") != contract.get("input_sha256"):
        raise ValueError("Correction receipt and export contract differ")
    if input_path.stat().st_size != 9661432847:
        raise ValueError("Unexpected corrected input size")
    if contract.get("tiling_correction", {}).get("replacement_id") != "tiling-word-boundary-66ebb57757e4-p3-jeunesse-v1":
        raise ValueError("The corrected contract lacks its page replacement identity")

    stores = json.loads((ROOT / "structured" / "active_stores.json").read_text(encoding="utf-8"))
    active_stores = {
        name: artifact(ROOT / item["path"], item.get("sha256"))
        for name, item in stores.items()
        if isinstance(item, dict) and item.get("path", "").endswith(".sqlite")
    }
    with sqlite3.connect(f"file:{catalogue.as_posix()}?mode=ro", uri=True) as connection:
        registry_rows = connection.execute(
            "SELECT registry_key,relative_path FROM numeric_registry_versions ORDER BY registry_key"
        ).fetchall()
    if len(registry_rows) != 9:
        raise ValueError("Nine numeric registries are required")
    registries = {key: artifact(ROOT / relative) for key, relative in registry_rows}

    now = datetime.now(timezone.utc).isoformat()
    manifest = {
        "version": "nos-deniers-vectorisation-generation-1-user-accepted-incremental",
        "created_at": now,
        "files": {
            "input": artifact(input_path, contract["input_sha256"]),
            "contract": artifact(contract_path, hash_small(contract_path)),
            "catalogue": artifact(catalogue),
            "page_review_db": artifact(page_reviews),
        },
        "encoding": {
            "model": contract["model"], "revision": contract["revision"],
            "dimension": contract["dimension"], "max_tokens": contract["max_tokens"],
            "dense_normalized": contract["dense_normalized"],
            "dense_dtype": contract["dense_dtype"], "sparse_dtype": contract["sparse_dtype"],
            "colbert": contract["colbert"], "truncate": contract["truncate"],
        },
        "counts": {"pdf": 4402, "pages": 322172, "passages": contract["input_count"]},
        "active_stores": active_stores,
        "registries": registries,
        "verification": {
            "table_integration_complete": True,
            "corrected_export_created_by_deterministic_exporter": True,
            "corrected_export_sha256_calculated_during_publication": True,
            "previous_complete_input_audit_reached_page_audit": True,
            "single_page_correction": artifact(correction_path, hash_small(correction_path)),
            "second_full_readback_completed": False,
            "second_full_readback_waived_by_user": True,
            "waiver_reason": "One proven Je + unesse tiling boundary among 4,051,433 passages was accepted; the corrected export was retained without repeating the entire certification scan.",
        },
        "semantic_encoding_ready": True,
        "numeric_automation_ready": False,
        "paid_compute_authorized": False,
        "gpu_started": False,
        "limitation": "RunPod input is ready under the recorded user waiver. This manifest does not claim completion of the abandoned second full readback or automatic certification of budget amounts.",
    }
    manifest_path = ROOT / "frozen" / "manifest.json"
    if manifest_path.exists():
        raise ValueError("A final manifest already exists")
    atomic_json(manifest_path, manifest)
    handoff = {
        "generation_root": str(ROOT), "manifest": str(manifest_path),
        "input": str(input_path), "contract": str(contract_path),
        "catalogue": str(catalogue), "page_reviews": str(page_reviews),
        "input_count": contract["input_count"], "input_sha256": contract["input_sha256"],
        "runpod_input_ready": True, "launch_authorized": False,
        "full_second_readback_waived_by_user": True,
        "original_export_deleted": False,
        "note": "Use this corrected F generation as one bound set. Do not mix it with the archived pre-correction export or the old preparation contract.",
    }
    atomic_json(ROOT / "HANDOFF.json", handoff)
    return handoff


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False, sort_keys=True))
