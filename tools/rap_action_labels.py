"""Authoritative and documentary labels for national RAP action extraction."""
from __future__ import annotations

import json
import re
import subprocess


def clean_pdf_label(label: str) -> str:
    """Remove page headers accidentally captured after a wrapped label."""
    label = re.sub(r"\s+\d{1,3}\s+(?=PLR(?:G)?\s*[–-]\s*RAP)", " ", label)
    markers = (" PLR – RAP", " PLRG – RAP", " ou de la sous-action", " Dépenses de",
               " y.c. FdC", " hors FdC", " par FdC et AdP")
    positions = [label.find(marker) for marker in markers if label.find(marker) >= 0]
    if positions:
        label = label[:min(positions)]
    return re.sub(r"\s+", " ", label).strip()

def canonical_labels() -> tuple[dict, dict]:
    query = r'''import json,sqlite3
c=sqlite3.connect('file:/data/derived/budget.sqlite?mode=ro',uri=True); c.row_factory=sqlite3.Row
r=c.execute("select distinct year,mission,program,action,action_label,subaction,subaction_label from facts where budget='BG' and year between 2023 and 2025 and action!='' order by year,mission,program,action,subaction").fetchall()
print(json.dumps([dict(x) for x in r],ensure_ascii=False))'''
    output = subprocess.check_output(
        ["docker", "exec", "lexmachine-budget-web-1", "python", "-c", query],
        text=True, encoding="utf-8")
    rows = json.loads(output)
    actions, subactions = {}, {}
    for row in rows:
        action_key = (row["year"], row["mission"], row["program"], row["action"])
        previous = actions.setdefault(action_key, row["action_label"])
        assert previous == row["action_label"], ("action label conflict", action_key)
        if row["subaction"]:
            subaction_key = action_key + (row["subaction"],)
            previous = subactions.setdefault(subaction_key, row["subaction_label"])
            assert previous == row["subaction_label"], ("subaction label conflict", subaction_key)
    return actions, subactions


def document_action_labels(text: str) -> dict[tuple[str, str], str]:
    """Read programme tables of contents, which carry complete action labels."""
    programme = None
    result = {}
    for line in text.splitlines():
        found = re.match(r"^\s*PROGRAMME\s+(\d{3})\b", line, re.I)
        if found:
            programme = found.group(1)
        if not programme:
            continue
        action = re.match(r"^\s*(\d{2})\s*[–-]\s+(.+?)\s{2,}(\d{1,3})\s*$", line)
        if not action:
            continue
        label = action.group(2).strip()
        if re.search(r"\s{2,}[+-]?\d", label):
            continue
        key = (programme, action.group(1))
        if len(label) > len(result.get(key, "")):
            result[key] = label
    return result
