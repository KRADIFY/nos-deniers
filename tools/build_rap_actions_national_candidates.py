"""Extract and reconcile national RAP action tables without mutating the app.

Only groups whose published RAP total and action sum agree with the canonical
programme facts are emitted as candidates.  Every other group is reported as a
gap.  The generated file is therefore review material, never an automatic
numeric import.
"""
from __future__ import annotations

import hashlib
import argparse
import json
import re
import sqlite3
import subprocess
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from rap_action_labels import canonical_labels, clean_pdf_label, document_action_labels
from rap_program_context import programme_context


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from budget_service.reconciliation import assess_difference, difference_note, capped_rounding_bound
REPORT = ROOT / "reports" / "rap-actions-national-20260920"
SEARCH_DB = Path(r"D:\LexMachine\NosDeniers\search_20260919\search.sqlite")
CATALOGUE_DB = Path(r"F:\LexMachine\NosDeniers\generation_tables_20260911\catalogue.sqlite")
PDFTOTEXT = Path(r"C:\Users\Jean-Christophe\AppData\Local\Microsoft\WinGet\Packages\oschwartz10612.Poppler_Microsoft.Winget.Source_8wekyb3d8bbwe\poppler-25.07.0\Library\bin\pdftotext.exe")
YEARS = (2023, 2024, 2025)
MANUAL_SOURCE_IDS = {(2023, "AD"): "9099e2f12825d8806e5c", (2024, "SE"): "bc6228aeef56c32b08b0",
                    (2025, "AV"): "bb8c326ed634e8041996", (2025, "DA"): "03868e9a518ffbf12c28",
                     (2025, "PR"): "54b16abaa62ea5fed2ba", (2025, "TA"): "06557292eccf98885e32"}


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalise(value: str) -> str:
    value = value.replace("’", "" ).replace("'", "" )
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore" ).decode().lower()
    return " ".join(re.findall(r"[a-z0-9]+", value))


def canonical_parents() -> list[dict]:
    query = r'''import json,sqlite3
c=sqlite3.connect('file:/data/derived/budget.sqlite?mode=ro',uri=True); c.row_factory=sqlite3.Row
r=c.execute("select * from facts where budget='BG' and year between 2023 and 2025 and stage in ('LFI','EXEC') and action='' and subaction='' order by year,mission,program,measure,stage,title").fetchall()
print(json.dumps([dict(x) for x in r],ensure_ascii=False))'''
    output = subprocess.check_output(
        ["docker", "exec", "lexmachine-budget-web-1", "python", "-c", query],
        text=True, encoding="utf-8")
    return json.loads(output)


def existing_keys() -> set[tuple]:
    from budget_service import action_details
    return {action_details.key(group) for group in action_details.registry()[0]["groups"]}


def source_inventory(missions: dict[tuple[int, str], str]) -> tuple[dict[tuple[int, str], dict], list[dict]]:
    search = sqlite3.connect(SEARCH_DB)
    catalogue = sqlite3.connect(CATALOGUE_DB)
    documents = search.execute(
        "select source_sha256,source_id,title,years_key,stage,format from documents where format='pdf'"
    ).fetchall()
    by_year = defaultdict(dict)
    for sha, source, title, years_key, stage, fmt in documents:
        for year in YEARS:
            if str(year) in years_key:
                paths = [Path(x[0]) for x in catalogue.execute("select path from assets where sha256=?", (sha,))]
                if paths and paths[0].exists():
                    by_year[year][sha] = dict(sha256=sha, source=source, title=title, stage=stage,
                                              path=str(paths[0]))
    selected, gaps = {}, []
    aliases = {
        normalise("Administration générale et territoriale de l'État"): normalise("Administration générale territoriale de l'État"),
        normalise("Outre-Mer"): normalise("Outre-mer"),
        normalise("Travail, emploi et administration des ministères sociaux"): normalise("Travail et emploi"),
    }
    for key, label in missions.items():
        year, mission = key
        wanted = aliases.get(normalise(label), normalise(label))
        override = MANUAL_SOURCE_IDS.get(key)
        if override:
            exact = [d for d in by_year[year].values() if d["source"] == override]
        else:
            exact = [d for d in by_year[year].values() if normalise(d["title"]) == wanted and d["stage"] == "rap-plrg"]
        if len(exact) == 1:
            selected[key] = exact[0]
        else:
            gaps.append(dict(year=year, mission=mission, mission_label=label,
                             reason="source_document_not_uniquely_matched", candidates=len(exact)))
    return selected, gaps


def extract_text(source: dict) -> str:
    cached = ROOT / 'reports/rap-actions-national-20260920/text' / (source['sha256'] + '.txt')
    if cached.exists():
        return cached.read_text(encoding='utf-8', errors='replace')
    target = REPORT / "text" / (source["sha256"] + ".txt")
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        subprocess.run([str(PDFTOTEXT), "-layout", "-enc", "UTF-8", source["path"], str(target)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return target.read_text(encoding="utf-8", errors="replace")


def numbers(line: str) -> list[int]:
    return [int(value.replace(" ", "")) for value in re.split(r"\s{2,}", line.strip())
            if re.fullmatch(r"[+-]?\d[\d ]*", value)]


def label_prefix(line: str) -> str:
    line = re.sub(r"^\s*\d{2}(?:\.\d{2})?\s*[–-]\s*", "", line).strip()
    return re.split(r"\s{2,}(?=[+-]?\d)", line, maxsplit=1)[0].strip()


def table_sections(text: str, year: int) -> list[dict]:
    pages = text.split("\f")
    context = programme_context(text)
    programme = None
    flat = []
    for page_no, page in enumerate(pages, 1):
        programme = context[page_no]['program']
        for line in page.splitlines():
            flat.append((page_no, programme, line.rstrip()))
    marker = re.compile(rf"^{year}\s*/\s*PR[ÉE]SENTATION PAR ACTION", re.I)
    starts = [i for i, (_, _, line) in enumerate(flat) if marker.search(line.strip())]
    sections = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(flat)
        programme = flat[start][1]
        if not programme:
            continue
        chunk = flat[start:end]
        measures = {}
        for measure, heading in (("AE", "AUTORISATIONS D'ENGAGEMENT"), ("CP", "CREDITS DE PAIEMENT")):
            h = next((i for i, (_, _, line) in enumerate(chunk)
                      if re.search(rf"^{year}\s*/\s*{heading}", normalise(line).upper().replace("'", "'"))), None)
            if h is None:
                # Accent/punctuation tolerant fallback.
                words = "AUTORISATIONS" if measure == "AE" else "PAIEMENT"
                h = next((i for i, (_, _, line) in enumerate(chunk)
                          if str(year) in line and words in normalise(line).upper()), None)
            if h is None:
                continue
            stop = next((i for i in range(h + 1, len(chunk))
                         if re.match(rf"^Total des {measure} consomm", chunk[i][2].strip(), re.I)), None)
            if stop is None:
                continue
            measures[measure] = chunk[h + 1:stop + 1]
        if measures:
            sections.append(dict(programme=programme, marker_page=flat[start][0], measures=measures))
    return sections


def parse_measure(lines: list[tuple[int, str, str]], measure: str) -> dict:
    action_pattern = re.compile(r"^\s*(\d{2}(?:\.\d{2})?)\s*[–-]\s+")
    positions = [i for i, (_, _, line) in enumerate(lines) if action_pattern.match(line)]
    actions, errors = [], []
    for pos_index, pos in enumerate(positions):
        page, _, line = lines[pos]
        code = action_pattern.match(line).group(1)
        end = positions[pos_index + 1] if pos_index + 1 < len(positions) else len(lines) - 1
        block = lines[pos:end]
        numeric = [(i, p, text, numbers(text)) for i, (p, _, text) in enumerate(block) if numbers(text)]
        forecast = next((item for item in numeric if len(item[3]) >= 2), None)
        actual = next((item for item in numeric if forecast and item[0] > forecast[0] and len(item[3]) >= 1), None)
        if not forecast or not actual:
            errors.append(dict(code=code, page=page, reason="forecast_or_consumption_row_not_decoded"))
            continue
        label_parts = []
        for _, _, text in block:
            prefix = label_prefix(text)
            if (prefix and not re.fullmatch(r"[+-]?\d[\d ]*", prefix)
                    and not prefix.startswith(("Total des", "Ouvertures", "PLRG", "Numéro et intitulé", "Prévision LFI", "Consommation"))
                    and not re.match(r"^\d{4}\s*/", prefix)):
                label_parts.append(prefix)
        label = " ".join(label_parts)
        label = re.sub(r"\s+", " ", label).strip()
        actions.append(dict(code=code, label=label, lfi_euros=forecast[3][-2], lfi_page=forecast[1],
                            exec_euros=actual[3][-1], exec_page=actual[1]))
    total_line = lines[-1]
    totals = numbers(total_line[2])
    if len(totals) < 1:
        raise ValueError(("total_not_decoded", measure, total_line))
    # Published LFI total is the penultimate amount (before Total y.c. FdC/AdP).
    # A few tables expose only one total; those groups remain gaps rather than guessing.
    lfi_line = next((item for i,item in enumerate(lines) if item[2].strip().startswith("Total des " + measure)
                    and 'LFI' in ' '.join(v[2] for v in lines[i:i+2])
                    and 'consomm' not in item[2].lower()), None)
    lfi_numbers = numbers(lfi_line[2]) if lfi_line else []
    lfi_total = lfi_numbers[-2] if len(lfi_numbers) >= 2 else None
    return dict(actions=actions, errors=errors, lfi_total_euros=lfi_total,
                exec_total_euros=totals[-1], total_page=total_line[0])


def main() -> None:
    global REPORT
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', type=Path, default=REPORT)
    args = ap.parse_args()
    REPORT = args.output
    REPORT.mkdir(parents=True, exist_ok=True)
    parents = canonical_parents()
    official_action_labels, official_subaction_labels = canonical_labels()
    missions = {(row["year"], row["mission"]): row["mission_label"] for row in parents}
    sources, gaps = source_inventory(missions)
    parent_groups = defaultdict(list)
    for row in parents:
        parent_groups[(row["year"], row["mission"], row["program"], row["measure"], row["stage"])].append(row)
    existing = existing_keys()
    candidates, parsed_tables = [], []
    for (year, mission), source in sorted(sources.items()):
        actual_sha = hashlib.sha256(Path(source["path"]).read_bytes()).hexdigest()
        if actual_sha != source["sha256"]:
            gaps.append(dict(year=year, mission=mission, reason="physical_sha256_mismatch"))
            continue
        text = extract_text(source)
        cache = ROOT / 'reports/rap-actions-national-20260920/text' / (source['sha256'] + '.txt')
        source['text_path'] = str(cache if cache.exists() else REPORT / 'text' / (source['sha256'] + '.txt'))
        toc_labels = document_action_labels(text)
        sections = table_sections(text, year)
        seen = set()
        for section in sections:
            program = section["programme"]
            if program in seen:
                gaps.append(dict(year=year, mission=mission, program=program,
                                 reason="duplicate_current_year_table"))
                continue
            seen.add(program)
            decoded = {}
            try:
                for measure in ("AE", "CP"):
                    if measure not in section["measures"]:
                        raise ValueError(("missing_measure", measure))
                    decoded[measure] = parse_measure(section["measures"][measure], measure)
            except Exception as exc:
                gaps.append(dict(year=year, mission=mission, program=program,
                                 marker_page=section["marker_page"], reason="table_decode_failed", detail=repr(exc)))
                continue
            parsed_tables.append(dict(year=year, mission=mission, program=program,
                                      marker_page=section["marker_page"], source=source["source"], decoded=decoded))
            for measure in ("AE", "CP"):
                detail = decoded[measure]
                main_actions = [a for a in detail["actions"] if "." not in a["code"]]
                subactions = [a for a in detail["actions"] if "." in a["code"]]
                for stage, total_field, amount_field, page_field in (
                    ("LFI", "lfi_total_euros", "lfi_euros", "lfi_page"),
                    ("EXEC", "exec_total_euros", "exec_euros", "exec_page"),
                ):
                    key = (year, mission, program, measure, stage)
                    canonical = parent_groups.get(key, [])
                    if not canonical:
                        gaps.append(dict(year=year, mission=mission, program=program, measure=measure, stage=stage,
                                         reason="canonical_program_group_missing"))
                        continue
                    published = detail[total_field]
                    if published is None:
                        gaps.append(dict(year=year, mission=mission, program=program, measure=measure, stage=stage,
                                         reason="published_lfi_total_ambiguous"))
                        continue
                    canonical_cents = sum(row["cents"] for row in canonical)
                    tolerance = len(main_actions) * 50 if stage == "EXEC" else 0
                    total_delta = published * 100 - canonical_cents
                    action_delta = sum(a[amount_field] * 100 for a in main_actions) - canonical_cents
                    group_key = (year, stage, measure, "BG", mission, program)
                    reconciliation = assess_difference(published * 100, canonical_cents)
                    action_reconciliation = assess_difference(sum(a[amount_field] * 100 for a in main_actions), canonical_cents, len(main_actions))
                    arithmetic_delta = sum(a[amount_field] * 100 for a in main_actions) - published * 100
                    status = "already_reviewed" if group_key in existing else "candidate"
                    if (detail["errors"] or not main_actions or not reconciliation['accepted']
                        or not action_reconciliation['accepted'] or abs(arithmetic_delta) > capped_rounding_bound(len(main_actions))):
                        gaps.append(dict(year=year, mission=mission, program=program, measure=measure, stage=stage,
                                         marker_page=section["marker_page"], reason="reconciliation_failed",
                                         action_count=len(main_actions), parse_errors=detail["errors"],
                                         published_total_minus_parent_cents=total_delta,
                                         action_sum_minus_parent_cents=action_delta))
                        continue
                    actions = []
                    for action in main_actions:
                        label_key = (year, mission, program, action["code"])
                        label = official_action_labels.get(label_key) or toc_labels.get((program, action["code"])) or clean_pdf_label(action["label"])
                        label_source = "PLF" if label_key in official_action_labels else "RAP contents" if (program, action["code"]) in toc_labels else "RAP table"
                        item = dict(code=action["code"], label=label, label_source=label_source, euros=action[amount_field], page=action[page_field])
                        children = [s for s in subactions if s["code"].startswith(action["code"] + ".")]
                        child_sum = sum(s[amount_field] for s in children)
                        if children and child_sum == item["euros"]:
                            child_items = []
                            for child in children:
                                child_code = child["code"].split(".", 1)[1]
                                child_key = label_key + (child_code,)
                                child_label = official_subaction_labels.get(child_key) or clean_pdf_label(child["label"])
                                child_source = "PLF" if child_key in official_subaction_labels else "RAP table"
                                child_items.append(dict(code=child_code, label=child_label, label_source=child_source, euros=child[amount_field], page=child[page_field]))
                            item["subactions"] = child_items
                        actions.append(item)
                    candidates.append(dict(year=year, stage=stage, measure=measure, budget="BG", mission=mission,
                                           program=program, source=source["source"], sha256=source["sha256"],
                                           page=section["marker_page"], total_page=detail["total_page"],
                                           parents=canonical, published_total_euros=published,
                                           action_sum_minus_parent_cents=action_delta,
                                           published_total_minus_parent_cents=total_delta,
                                           reconciliation=reconciliation, action_reconciliation=action_reconciliation,
                                           reconciliation_note=difference_note(reconciliation),
                                           actions=actions, status=status))
    write_json(REPORT / "sources.json", [dict(year=y, mission=m, **s) for (y, m), s in sorted(sources.items())])
    write_json(REPORT / "parsed-tables.json", parsed_tables)
    write_json(REPORT / "candidates.json", {"groups": candidates})
    write_json(REPORT / "gaps.json", gaps)
    summary = dict(sources=len(sources), mission_years=len(missions), tables=len(parsed_tables),
                   groups=len(candidates), new_groups=sum(g["status"] == "candidate" for g in candidates),
                   already_reviewed=sum(g["status"] == "already_reviewed" for g in candidates), gaps=len(gaps),
                   action_observations=sum(len(g["actions"]) for g in candidates))
    write_json(REPORT / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
