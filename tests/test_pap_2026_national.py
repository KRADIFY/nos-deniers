import copy
import json
from pathlib import Path
import sqlite3
import unittest

from budget_service import api
from budget_service.import_pap_2026_national import validate_plan


class NationalPap2026Tests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / "budget_service" / "data" / "pap-2026-national.json"
        self.plan = json.loads(path.read_text(encoding="utf8"))

    def test_reviewed_plan_is_complete_and_partitioned(self):
        validate_plan(self.plan)
        self.assertEqual(len(self.plan["sources"]), 32)
        self.assertEqual(len(self.plan["checks"]), 128)
        self.assertEqual(len(self.plan["mission_total_checks"]), 110)
        self.assertEqual(len(self.plan["rows"]), 372)
        self.assertEqual(len(self.plan["additions"]), 338)
        self.assertEqual(len(self.plan["existing_rows_preserved"]), 34)

    def test_blanks_are_not_turned_into_zero(self):
        self.assertFalse(any(item["cents"] <= 0 for item in self.plan["rows"]))
        self.assertFalse(any(item["mission"] == "TA" and item["program"] == "362" for item in self.plan["rows"]))

    def test_programme_sums_equal_every_published_mission_total(self):
        totals = {}
        for item in self.plan["rows"]:
            key = (item["mission"], item["stage"], item["measure"])
            totals[key] = totals.get(key, 0) + item["cents"]
        published = {
            (item["mission"], item["stage"], item["measure"]): item["cents"]
            for item in self.plan["mission_total_checks"]
        }
        self.assertEqual(totals, published)

    def test_non_ecology_pap_rows_keep_their_physical_source_page(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute(
            "CREATE TABLE facts(year,stage,measure,budget,mission,mission_label,program,program_label,action,action_label,subaction,subaction_label,category,title,cents,source,line,field,approximate)"
        )
        db.execute("CREATE TABLE sources(id,data)")
        db.execute(
            "INSERT INTO facts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (2026, "PLF", "CP", "BG", "RC", "Relations avec les collectivités territoriales", "122", "Concours spécifiques", "", "", "", "", "", "", 25630482700, "3833a5f825d0f24ed1ef", 14, "PLF CP 2026 · PAP p. 14", 0),
        )
        db.execute(
            "INSERT INTO facts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (2026, "LFI", "CP", "BG", "M26985a5788", "Monde combattant, mémoire et liens avec la Nation", "158", "Indemnisation", "", "", "", "", "", "", 100, "source", 1, "LFI CP 2026", 0),
        )
        parameters = dict(start=2026, end=2026, measure="CP", budget="BG")
        rows = api.selected_records(db, parameters)
        self.assertEqual(rows[0]["page"], 14)
        self.assertEqual(rows[1]["mission"], "MB")
        self.assertEqual(rows[1]["mission_label"], "Monde combattant, mémoire et liens avec la Nation")
        self.assertIn("programmes 158 et 169", rows[1]["_mission_lineage_note"])
        db.close()

    def test_corrupted_or_ambiguous_plans_are_refused(self):
        mutations = {
            "amount": lambda plan: plan["rows"][0].__setitem__("cents", plan["rows"][0]["cents"] + 1),
            "duplicate": lambda plan: plan["rows"].__setitem__(1, plan["rows"][0]),
            "zero": lambda plan: plan["rows"][0].__setitem__("cents", 0),
            "wrong_source": lambda plan: plan["rows"][0].__setitem__("source", "unknown"),
            "unchecked_programme": lambda plan: plan["checks"][0].__setitem__("passed", False),
            "unchecked_total": lambda plan: plan["mission_total_checks"][0].__setitem__("passed", False),
            "wrong_summary": lambda plan: plan["summary"].__setitem__("rows_to_add", 337),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                plan = copy.deepcopy(self.plan)
                mutate(plan)
                with self.assertRaises(ValueError):
                    validate_plan(plan)


if __name__ == "__main__":
    unittest.main()
