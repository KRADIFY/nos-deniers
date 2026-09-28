"""Promote only fully reconciled, previously unregistered RAP action groups."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SOURCE = ROOT / "reports" / "rap-actions-national-20260920" / "candidates.json"
TARGET = ROOT / "budget_service" / "data" / "actions-national.json"


def key(group: dict) -> tuple:
    return tuple(group[name] for name in ("year", "stage", "measure", "budget", "mission", "program"))


def clean_item(item: dict) -> dict:
    result = {name: item[name] for name in ("code", "label", "euros", "page")}
    if item.get("subactions"):
        result["subactions"] = [clean_item(child) for child in item["subactions"]]
    return result


def main() -> None:
    from budget_service import action_details

    candidates = json.loads(SOURCE.read_text(encoding="utf-8"))["groups"]
    existing = {action_details.key(group) for group in action_details.registry()[0]["groups"]}
    selected = []
    for candidate in candidates:
        if candidate["status"] != "candidate":
            continue
        group_key = key(candidate)
        assert group_key not in existing
        actions = [clean_item(item) for item in candidate["actions"]]
        assert actions and len({item["code"] for item in actions}) == len(actions)
        assert all(item["label"] for item in actions)
        canonical = sum(row["cents"] for row in candidate["parents"])
        tolerance = min(1000, len(actions) * 50 if candidate["stage"] == "EXEC" else 0)
        assert abs(candidate["published_total_euros"] * 100 - canonical) <= (50 if candidate["stage"] == "EXEC" else 0)
        assert abs(sum(item["euros"] * 100 for item in actions) - canonical) <= tolerance
        for item in actions:
            children = item.get("subactions", [])
            assert len({child["code"] for child in children}) == len(children)
            assert all(child["label"] for child in children)
            assert not children or sum(child["euros"] for child in children) == item["euros"]
        selected.append({name: candidate[name] for name in (
            "year", "stage", "measure", "budget", "mission", "program", "source", "sha256",
            "page", "total_page", "parents", "published_total_euros",
            "action_sum_minus_parent_cents", "published_total_minus_parent_cents"
        )} | {"actions": actions})
    assert len(selected) == 1231
    assert len({key(group) for group in selected}) == len(selected)
    data = {
        "updated_at": "2026-09-20",
        "coverage": ("Détail RAP national rapproché des totaux canoniques : 1 231 groupes "
                     "LFI/consommé, AE/CP, 2023–2025, sur 318 programmes-années et 91 missions-années."),
        "note": ("Chaque groupe est rattaché au PDF RAP et à sa page. Les groupes dont le total publié "
                 "ou la somme des actions ne concorde pas restent absents."),
        "groups": selected,
    }
    TARGET.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "groups": len(selected),
        "program_years": len({(g["year"], g["mission"], g["program"]) for g in selected}),
        "mission_years": len({(g["year"], g["mission"]) for g in selected}),
        "actions": sum(len(g["actions"]) for g in selected),
        "subactions": sum(len(a.get("subactions", [])) for g in selected for a in g["actions"]),
        "sha256": hashlib.sha256(TARGET.read_bytes()).hexdigest(),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
