"""Extract review candidates from the 2026 budget-general PAP summaries.

This command is deliberately read-only with respect to the application database.
It downloads the already catalogued local PDFs through the Nos Deniers API,
checks their SHA-256, and writes candidates plus diagnostics for human review.
Blank cells remain ``None`` and no candidate is promoted to a budget fact here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import sqlite3
from urllib.request import urlopen

import pdfplumber
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "consolidation-20260920"
SEARCH_DB = Path(r"D:\LexMachine\NosDeniers\search_20260919\search.sqlite")
CATALOGUE_DB = Path(r"F:\LexMachine\NosDeniers\generation_tables_20260911\catalogue.sqlite")
API = "http://127.0.0.1:8552/api/download/"

PROGRAM_RE = re.compile(r"^\s*(\d{3})\s+[–-]\s+(.+?)\s*$")
NODE_RE = re.compile(r"^\s*(\d{2,3})\s+[–-]\s+")
AMOUNT_RE = re.compile(r"(?<![\d,])(?:\d{1,3}(?: \d{3})+|0)(?![\d,])")


@dataclass(frozen=True)
class Document:
    reference_id: str
    source_sha256: str
    source_id: str
    title: str
    url: str
    mission: str
    bytes_expected: int


def ro(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    return db


def documents() -> list[Document]:
    search = ro(SEARCH_DB)
    catalogue = ro(CATALOGUE_DB)
    try:
        rows = search.execute(
            """SELECT reference_id,source_sha256,source_id,title,url
               FROM documents
               WHERE years_key='|2026|' AND stage='plf-pap' AND format='pdf'
                 AND url LIKE '%PAP2026_BG_%'
               ORDER BY title"""
        ).fetchall()
        result = []
        for row in rows:
            ref = catalogue.execute(
                "SELECT metadata_json FROM refs WHERE id=?", (row["reference_id"],)
            ).fetchone()
            if not ref:
                raise RuntimeError("Missing sealed catalogue reference " + row["reference_id"])
            metadata = json.loads(ref["metadata_json"])
            match = re.search(r"_([A-Z]{2})\.pdf(?:\?.*)?$", row["url"], re.I)
            if not match:
                raise RuntimeError("Mission code absent from PAP URL: " + row["url"])
            result.append(
                Document(
                    reference_id=row["reference_id"],
                    source_sha256=row["source_sha256"],
                    source_id=row["source_id"],
                    title=row["title"],
                    url=row["url"],
                    mission=match.group(1).upper(),
                    bytes_expected=int(metadata["bytes"]),
                )
            )
        return result
    finally:
        search.close()
        catalogue.close()


def fetch(document: Document) -> bytes:
    with urlopen(API + document.source_id, timeout=90) as response:
        body = response.read()
    if len(body) != document.bytes_expected:
        raise RuntimeError(f"{document.mission}: source byte count differs")
    if sha256(body).hexdigest() != document.source_sha256:
        raise RuntimeError(f"{document.mission}: source SHA-256 differs")
    if not body.startswith(b"%PDF-"):
        raise RuntimeError(f"{document.mission}: source is not a PDF")
    return body


def plain(page) -> str:
    try:
        return page.extract_text() or ""
    except KeyError:
        return ""


def layout(page) -> str:
    try:
        return page.extract_text(extraction_mode="layout") or ""
    except KeyError:
        return ""


def table_ranges(reader: PdfReader) -> dict[str, tuple[int, int] | None]:
    starts: dict[str, int | None] = {"action": None, "title": None}
    texts = []
    for index, page in enumerate(reader.pages[:50]):
        text = plain(page)
        texts.append(text)
        upper = text.upper().replace("É", "E").replace("È", "E")
        if starts["action"] is None and "CREDITS PAR PROGRAMME ET ACTION" in upper:
            starts["action"] = index
        if starts["title"] is None and "CREDITS PAR PROGRAMME ET TITRE" in upper:
            starts["title"] = index
    result: dict[str, tuple[int, int] | None] = {"action": None, "title": None}
    if starts["action"] is not None:
        end = starts["title"] if starts["title"] is not None else starts["action"] + 1
        result["action"] = (starts["action"], end)
    if starts["title"] is not None:
        end = starts["title"] + 1
        for index in range(starts["title"] + 1, min(len(texts), starts["title"] + 12)):
            upper = texts[index].upper().replace("É", "E").replace("È", "E")
            if re.search(r"\bPROGRAMME\s+\d{3}\s*:", upper):
                end = index
                break
            end = index + 1
        result["title"] = (starts["title"], end)
    return result


def header_positions(lines: list[str]) -> dict[str, int] | None:
    for line in lines:
        if line.count("Ouvertures") >= 2 and line.count("FdC et AdP") >= 2:
            opens = [match.start() for match in re.finditer("Ouvertures", line)]
            fdcs = [match.start() for match in re.finditer("FdC et AdP", line)]
            variations = [match.start() for match in re.finditer("Variation", line)]
            if len(variations) < 2:
                continue
            return {
                "ae_open": opens[0],
                "ae_variation": variations[0],
                "ae_fdc": fdcs[0],
                "cp_open": opens[1],
                "cp_variation": variations[1],
                "cp_fdc": fdcs[1],
            }
    return None


def amounts_by_column(line: str, positions: dict[str, int]) -> dict[str, int]:
    amount_positions = {key: value for key, value in positions.items() if not key.endswith("variation")}
    values: dict[str, int] = {}
    for match in AMOUNT_RE.finditer(line):
        if match.start() < 45:
            continue
        value = int(match.group().replace(" ", ""))
        center = (match.start() + match.end()) / 2
        name = min(amount_positions, key=lambda key: abs(center - amount_positions[key]))
        if name in values:
            raise ValueError(f"Two amounts assigned to {name}: {line}")
        values[name] = value
    return values


def program_candidates(reader: PdfReader, bounds: tuple[int, int] | None, table: str):
    if bounds is None:
        return [], [f"{table}: table not found"]
    result = []
    diagnostics = []
    for page_index in range(*bounds):
        lines = layout(reader.pages[page_index]).splitlines()
        positions = header_positions(lines)
        if positions is None:
            # Continued table pages repeat the columns inconsistently. Reuse the
            # standard positions measured on the first page and flag the page.
            positions = {"ae_open": 64, "ae_variation": 89, "ae_fdc": 108,
                         "cp_open": 135, "cp_variation": 158, "cp_fdc": 181}
            diagnostics.append(f"{table} p.{page_index + 1}: fallback column positions")
        indices = [i for i, line in enumerate(lines) if NODE_RE.match(line)]
        for offset, start in enumerate(indices):
            match = PROGRAM_RE.match(lines[start])
            if not match:
                continue
            end = indices[offset + 1] if offset + 1 < len(indices) else len(lines)
            block = lines[start:end]
            amount_rows = []
            for line in block:
                try:
                    amounts = amounts_by_column(line, positions)
                except ValueError:
                    diagnostics.append(
                        f"{table} p.{page_index + 1} P{match.group(1)}: "
                        "ambiguous non-credit line excluded"
                    )
                    continue
                if amounts:
                    amount_rows.append({"line": line.rstrip(), "amounts": amounts})
            candidate = {
                "table": table,
                "page": page_index + 1,
                "program": match.group(1),
                "label": match.group(2).strip(),
                "amount_rows": amount_rows,
                "status": "candidate" if len(amount_rows) >= 2 else "ambiguous",
                "plf_ae": None,
                "plf_cp": None,
                "fdc_prevu_ae": None,
                "fdc_prevu_cp": None,
            }
            if len(amount_rows) >= 2:
                published = amount_rows[1]["amounts"]
                candidate.update(
                    plf_ae=published.get("ae_open"),
                    plf_cp=published.get("cp_open"),
                    fdc_prevu_ae=published.get("ae_fdc"),
                    fdc_prevu_cp=published.get("cp_fdc"),
                )
            else:
                diagnostics.append(
                    f"{table} p.{page_index + 1} P{candidate['program']}: "
                    f"{len(amount_rows)} amount row(s)"
                )
            result.append(candidate)
    return result, diagnostics


def coordinate_candidates(pdf, bounds: tuple[int, int] | None, table: str):
    """Read the two published amount baselines from physical PDF columns."""
    if bounds is None:
        return [], [f"{table}: table not found"]
    result = []
    diagnostics = []
    fallback = {"ae_open": 224, "ae_variation": 278, "ae_fdc": 347,
                "cp_open": 392, "cp_variation": 449, "cp_fdc": 516}
    for page_index in range(*bounds):
        words = pdf.pages[page_index].extract_words(x_tolerance=1, y_tolerance=2)
        anchors = {}
        for label, key in (("Ouvertures", "open"), ("Variation", "variation"), ("FdC", "fdc")):
            found = sorted(w["x0"] for w in words if w["text"] == label)
            if len(found) >= 2:
                anchors["ae_" + key], anchors["cp_" + key] = found[0], found[1]
        if len(anchors) != 6:
            anchors = fallback
            diagnostics.append(f"{table} p.{page_index + 1}: fallback physical columns")
        # The official PAP pages use stable physical columns. Fixed cell
        # boundaries preserve grouped thousands when a PDF splits one amount
        # into several words; header midpoints can otherwise truncate them.
        amount_ranges = {
            "ae_open": (205, 276),
            "ae_fdc": (315, 380),
            "cp_open": (380, 445),
            "cp_fdc": (480, 560),
        }

        nodes = []
        for word in words:
            if word["x0"] >= 80 or not re.fullmatch(r"\d{2,3}", word["text"]):
                continue
            same_line = [w for w in words if abs(w["top"] - word["top"]) < 1.2]
            if not any(w["text"] in {"–", "-"} and word["x1"] <= w["x0"] <= word["x1"] + 24 for w in same_line):
                continue
            nodes.append(word)
        nodes.sort(key=lambda word: (word["top"], word["x0"]))

        for index, node in enumerate(nodes):
            if len(node["text"]) != 3:
                continue
            end_top = nodes[index + 1]["top"] if index + 1 < len(nodes) else pdf.pages[page_index].height
            block = [w for w in words if node["top"] - 1 <= w["top"] < end_top - 1]
            tops = []
            for top in sorted({round(w["top"], 1) for w in block}):
                line = [w for w in block if abs(w["top"] - top) < 1.2]
                if any(w["x0"] >= amount_ranges["ae_open"][0] and (re.fullmatch(r"[+-]?\d+(?:,\d+)?", w["text"]) or w["text"] == "%") for w in line):
                    tops.append(top)
            amount_rows = []
            for top in tops[:2]:
                line = [w for w in block if abs(w["top"] - top) < 1.2]
                values = {}
                for name in ("ae_open", "ae_fdc", "cp_open", "cp_fdc"):
                    left, right = amount_ranges[name]
                    groups = [w["text"] for w in sorted(line, key=lambda word: word["x0"])
                              if left <= (w["x0"] + w["x1"]) / 2 < right and re.fullmatch(r"\d+", w["text"])]
                    if groups:
                        values[name] = int("".join(groups))
                amount_rows.append({"top": top, "amounts": values})
            second = amount_rows[1]["amounts"] if len(amount_rows) >= 2 else {}
            label_words = [w["text"] for w in block if w["x0"] < 205 and w["text"] not in {node["text"], "–", "-"}]
            result.append({
                "table": table,
                "page": page_index + 1,
                "program": node["text"],
                "label": " ".join(label_words[:30]),
                "amount_rows": amount_rows,
                "status": "candidate" if len(amount_rows) >= 2 else "ambiguous",
                "plf_ae": second.get("ae_open"),
                "plf_cp": second.get("cp_open"),
                "fdc_prevu_ae": second.get("ae_fdc"),
                "fdc_prevu_cp": second.get("cp_fdc"),
            })
            if len(amount_rows) < 2:
                diagnostics.append(f"{table} p.{page_index + 1} P{node['text']}: {len(amount_rows)} physical row(s)")
    return result, diagnostics

def compare_tables(action: list[dict], title: list[dict]):
    fields = ("plf_ae", "plf_cp", "fdc_prevu_ae", "fdc_prevu_cp")

    def first_candidates(rows):
        selected = {}
        for row in rows:
            if row["status"] == "candidate":
                selected.setdefault(row["program"], row)
        return selected

    by_action = first_candidates(action)
    by_title = first_candidates(title)
    comparisons = []
    for program in sorted(set(by_action) | set(by_title)):
        left = by_action.get(program)
        right = by_title.get(program)
        equal = bool(left and right) and all(left[field] == right[field] for field in fields)
        comparisons.append(
            {
                "program": program,
                "action_page": left and left["page"],
                "title_page": right and right["page"],
                "action_values": left and {field: left[field] for field in fields},
                "title_values": right and {field: right[field] for field in fields},
                "passed": equal,
            }
        )
    return comparisons


def merge_methods(layout_action, layout_title, physical_action, physical_title):
    fields = ("plf_ae", "plf_cp", "fdc_prevu_ae", "fdc_prevu_cp")

    def first(rows):
        selected = {}
        for row in rows:
            if row["status"] == "candidate":
                selected.setdefault(row["program"], row)
        return selected

    sources = {
        "layout": (first(layout_action), first(layout_title)),
        "physical": (first(physical_action), first(physical_title)),
    }
    merged_action, merged_title, decisions = [], [], []
    programs = sorted({program for pair in sources.values() for side in pair for program in side})
    for program in programs:
        chosen = None
        for method in ("physical", "layout"):
            action = sources[method][0].get(program)
            title = sources[method][1].get(program)
            if action and title and all(action[field] == title[field] for field in fields):
                chosen = (method, action, title)
                break
        if chosen is None:
            action = sources["layout"][0].get(program) or sources["physical"][0].get(program)
            title = sources["layout"][1].get(program) or sources["physical"][1].get(program)
            chosen = ("unresolved", action, title)
        method, action, title = chosen
        if action:
            merged_action.append({**action, "extraction_method": method})
        if title:
            merged_title.append({**title, "extraction_method": method})
        decisions.append({"program": program, "method": method})
    return merged_action, merged_title, decisions

def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report = {
        "version": "pap-2026-candidates-1",
        "scope": "Budget général, PAP 2026; candidates only, no database mutation",
        "documents": [],
    }
    for number, document in enumerate(documents(), 1):
        body = fetch(document)
        reader = PdfReader(BytesIO(body))
        pdf = pdfplumber.open(BytesIO(body))
        ranges = table_ranges(reader)
        layout_action, layout_action_diagnostics = program_candidates(reader, ranges["action"], "action")
        layout_title, layout_title_diagnostics = program_candidates(reader, ranges["title"], "title")
        physical_action, physical_action_diagnostics = coordinate_candidates(pdf, ranges["action"], "action")
        physical_title, physical_title_diagnostics = coordinate_candidates(pdf, ranges["title"], "title")
        action, title, decisions = merge_methods(
            layout_action, layout_title, physical_action, physical_title
        )
        action_diagnostics = layout_action_diagnostics + physical_action_diagnostics
        title_diagnostics = layout_title_diagnostics + physical_title_diagnostics
        comparisons = compare_tables(action, title)
        report["documents"].append(
            {
                **asdict(document),
                "pages": len(reader.pages),
                "table_ranges": ranges,
                "programs_action": action,
                "programs_title": title,
                "comparisons": comparisons,
                "extraction_decisions": decisions,
                "passed": bool(comparisons) and all(item["passed"] for item in comparisons),
                "diagnostics": action_diagnostics + title_diagnostics,
            }
        )
        print(
            f"[{number:02d}] {document.mission} {document.title}: "
            f"{len(action)} action-table programs, {len(title)} title-table programs, "
            f"{sum(item['passed'] for item in comparisons)}/{len(comparisons)} matched",
            flush=True,
        )
    report["summary"] = {
        "documents": len(report["documents"]),
        "documents_passed": sum(item["passed"] for item in report["documents"]),
        "program_comparisons": sum(len(item["comparisons"]) for item in report["documents"]),
        "program_comparisons_passed": sum(
            comparison["passed"]
            for item in report["documents"]
            for comparison in item["comparisons"]
        ),
        "database_mutated": False,
        "blank_cells_converted_to_zero": False,
    }
    path = OUT / "pap-2026-candidates.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
