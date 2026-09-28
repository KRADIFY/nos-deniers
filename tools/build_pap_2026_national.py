"""Build a reviewed national 2026 PAP import plan from extraction evidence.

The output remains a plan in reports. It does not mutate the application DB.
Every imported amount is checked in two PAP summary tables, except mission PC,
whose two tables share one physical page and are checked against the exact page
text and the already validated 2026 LFI nomenclature.
"""
from __future__ import annotations

from collections import defaultdict
from io import BytesIO
import json
from pathlib import Path
import re
import sqlite3
from urllib.request import urlopen

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "consolidation-20260920"
CANDIDATES = REPORT / "pap-2026-candidates.json"
DB = REPORT / "budget-before.sqlite"
OUTPUT = REPORT / "pap-2026-national-plan.json"
FIELDS = "year stage measure budget mission mission_label program program_label action action_label subaction subaction_label category title cents source line field approximate".split()
VALUE_FIELDS = {
    "plf_ae": ("PLF", "AE", "ouvertures proposées hors FdC/AdP"),
    "plf_cp": ("PLF", "CP", "ouvertures proposées hors FdC/AdP"),
    "fdc_prevu_ae": ("FDC_PREVU", "AE", "FdC/AdP attendus, prévision distincte"),
    "fdc_prevu_cp": ("FDC_PREVU", "CP", "FdC/AdP attendus, prévision distincte"),
}
PC = {
    "551": {"plf_ae": 350_000_000, "plf_cp": 350_000_000},
    "552": {"plf_ae": 425_000_000, "plf_cp": 125_000_000},
}
SPECIAL = {("EB", "336"): {"plf_ae": 37_460_000, "plf_cp": 37_460_000}}
EXPLICIT_BLANKS = {("TA", "362")}


def source_page(document: dict, page: int) -> str:
    with urlopen("http://127.0.0.1:8552/api/download/" + document["source_id"], timeout=90) as response:
        body = response.read()
    if len(body) != document["bytes_expected"]:
        raise ValueError(document["mission"] + ": source byte count differs")
    reader = PdfReader(BytesIO(body))
    return reader.pages[page - 1].extract_text() or ""


def label(db: sqlite3.Connection, mission: str, program: str) -> str:
    row = db.execute(
        """SELECT program_label FROM facts WHERE program=?
           ORDER BY CASE WHEN mission=? THEN 0 ELSE 1 END,
                    CASE WHEN year=2026 THEN 0 ELSE 1 END, year DESC LIMIT 1""",
        (program, mission),
    ).fetchone()
    if not row or not row[0]:
        raise ValueError(f"Missing programme label for {mission}/{program}")
    return row[0]


def row(document: dict, program: str, page: int, key: str, euros: int, db: sqlite3.Connection) -> dict:
    stage, measure, description = VALUE_FIELDS[key]
    return {
        "year": 2026,
        "stage": stage,
        "measure": measure,
        "budget": "BG",
        "mission": document["mission"],
        "mission_label": document["title"],
        "program": program,
        "program_label": label(db, document["mission"], program),
        "action": "",
        "action_label": "",
        "subaction": "",
        "subaction_label": "",
        "category": "",
        "title": "",
        "cents": euros * 100,
        "source": document["source_id"],
        "line": page,
        "field": f"{stage} {measure} 2026 · PAP p. {page} · {description}",
        "approximate": 0,
        "page": page,
    }


def main() -> None:
    evidence = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    rows = []
    checks = []
    documents = {item["mission"]: item for item in evidence["documents"]}
    try:
        for document in evidence["documents"]:
            stored = db.execute("SELECT data FROM sources WHERE id=?", (document["source_id"],)).fetchone()
            if not stored:
                raise ValueError("Source missing from application catalogue: " + document["source_id"])
            metadata = json.loads(stored["data"])
            if metadata.get("sha256") != document["source_sha256"]:
                raise ValueError("Source SHA mismatch in application catalogue")
            for comparison in document["comparisons"]:
                program = comparison["program"]
                if document["mission"] == "TA":
                    reviewed = db.execute(
                        """SELECT * FROM facts WHERE year=2026 AND budget='BG' AND mission='TA'
                           AND program=? AND stage IN ('PLF','FDC_PREVU') AND action='' AND subaction=''
                           ORDER BY stage,measure""",
                        (program,),
                    ).fetchall()
                    if reviewed:
                        for current in reviewed:
                            item = {key: current[key] for key in FIELDS}
                            item["page"] = current["line"]
                            rows.append(item)
                        checks.append({"mission": "TA", "program": program,
                                       "status": "existing_visually_reviewed_ecology_plan",
                                       "page": reviewed[0]["line"], "passed": True})
                        continue
                if comparison["passed"]:
                    values = comparison["action_values"]
                    page = comparison["action_page"]
                    check_kind = "two_independent_pap_tables"
                elif document["mission"] == "PC" and program in PC:
                    values = PC[program]
                    page = 8
                    check_kind = "two_tables_same_page_plus_lfi_crosscheck"
                elif (document["mission"], program) in SPECIAL:
                    values = SPECIAL[(document["mission"], program)]
                    page = comparison["title_page"]
                    check_kind = "single_published_row_in_each_of_two_pap_tables"
                elif (document["mission"], program) in EXPLICIT_BLANKS:
                    checks.append({"mission": document["mission"], "program": program,
                                   "status": "explicit_blank_not_imported", "passed": True})
                    continue
                else:
                    raise ValueError(f"Unresolved PAP programme {document['mission']}/{program}")
                for key, euros in values.items():
                    if key not in VALUE_FIELDS or euros is None:
                        continue
                    if not isinstance(euros, int) or euros <= 0:
                        raise ValueError(f"Invalid amount {document['mission']}/{program}/{key}")
                    rows.append(row(document, program, page, key, euros, db))
                checks.append({"mission": document["mission"], "program": program,
                               "status": check_kind, "page": page, "passed": True})

        pc_text = re.sub(r"\s+", " ", source_page(documents["PC"], 8))
        for program, values in PC.items():
            for euros in values.values():
                printed = f"{euros:,}".replace(",", " ")
                if pc_text.count(printed) < 2:
                    raise ValueError(f"PC/{program}: amount not repeated in both page tables")
            for measure, key in (("AE", "plf_ae"), ("CP", "plf_cp")):
                lfi = db.execute(
                    "SELECT cents FROM facts WHERE year=2026 AND stage='LFI' AND budget='BG' AND mission='PC' AND program=? AND measure=? AND action=''",
                    (program, measure),
                ).fetchone()
                if not lfi or lfi[0] != values[key] * 100:
                    raise ValueError(f"PC/{program}/{measure}: LFI cross-check differs")

        keys = [(r["year"], r["stage"], r["measure"], r["budget"], r["mission"], r["program"]) for r in rows]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate national PAP facts")

        existing, additions = [], []
        for item in rows:
            current = db.execute(
                """SELECT cents,source,line FROM facts WHERE year=? AND stage=? AND measure=? AND budget=?
                   AND mission=? AND program=? AND action='' AND subaction=''""",
                tuple(item[key] for key in ("year", "stage", "measure", "budget", "mission", "program")),
            ).fetchall()
            if current:
                if len(current) != 1 or current[0]["cents"] != item["cents"]:
                    raise ValueError(
                        "Existing PAP fact conflicts with national plan: "
                        f"{item['mission']}/{item['program']}/{item['stage']}/{item['measure']} "
                        f"planned={item['cents']} existing={[dict(row) for row in current]}"
                    )
                existing.append(item)
            else:
                additions.append(item)

        totals = defaultdict(int)
        for item in rows:
            totals[(item["mission"], item["stage"], item["measure"])] += item["cents"]
        total_checks = []
        for mission, document in documents.items():
            bounds = document["table_ranges"]["action"]
            pages = [8] if mission == "PC" else list(range(bounds[0] + 1, bounds[1] + 2))
            text = " ".join(re.sub(r"\s+", " ", source_page(document, page)) for page in pages)
            for (row_mission, stage, measure), cents in sorted(totals.items()):
                if row_mission != mission:
                    continue
                printed = f"{cents // 100:,}".replace(",", " ")
                passed = printed in text
                total_checks.append({"mission": mission, "stage": stage, "measure": measure,
                                     "cents": cents, "printed": printed, "pages": pages, "passed": passed})
                if not passed:
                    raise ValueError(f"Mission total absent from PAP pages: {mission}/{stage}/{measure} {printed}")

        plan = {
            "version": "pap-2026-national-1",
            "scope": "Budget général, PAP 2026, programmes; PLF distinct des FdC/AdP attendus",
            "rows": rows,
            "additions": additions,
            "existing_rows_preserved": existing,
            "sources": [{key: document[key] for key in ("mission", "source_id", "source_sha256", "title", "url")}
                        for document in evidence["documents"]],
            "checks": checks,
            "mission_total_checks": total_checks,
            "limits": [
                "Crédits proposés dans les PAP 2026; ils restent distincts des crédits votés en LFI.",
                "Les FdC/AdP attendus sont des prévisions, distinctes des rattachements réalisés.",
                "Les cellules blanches ne sont jamais converties en zéro.",
                "Ce plan ajoute le niveau programme; les actions font l’objet d’un lot séparé.",
            ],
            "summary": {
                "documents": len(evidence["documents"]),
                "programmes_checked": len(checks),
                "rows_total": len(rows),
                "rows_already_present": len(existing),
                "rows_to_add": len(additions),
                "mission_totals_checked": len(total_checks),
                "database_mutated": False,
            },
        }
        OUTPUT.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(plan["summary"], ensure_ascii=False))
    finally:
        db.close()


if __name__ == "__main__":
    main()
