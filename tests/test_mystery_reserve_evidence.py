"""Keep documentary reserve qualifications separate from measured money."""
import json
import unittest
from pathlib import Path

from budget_service import rap_quality, reserves


class MysteryReserveEvidenceTests(unittest.TestCase):
    CASES = ((2023, "DB/367"), (2023, "PR/362"), (2023, "PR/363"),
             (2023, "PR/364"), (2025, "AD/370"), (2025, "PR/362"),
             (2025, "PR/363"))
    SOURCE = "2ec6de25d671f24e0e80"
    SHA = "2ec6de25d671f24e0e80229b9631b3f63fd7f5c380a23e6778b3714ac1612072"

    def setUp(self):
        rap_quality.registry.cache_clear()
        reserves.registry.cache_clear()
        self.meta = {"indices": {"2023": 100, "2024": 110, "2025": 120}}
        self.research = json.loads((Path(rap_quality.__file__).parent / "data" /
                                   "rap-investigation.json").read_text(encoding="utf8"))

    def query(self, year, scope, measure="CP", **changes):
        p = dict(start=year, end=year, budget="BG", measure=measure, scope=scope,
                 exclude=[], constant=False, base=2025, topic="", topic_mode="only")
        return reserves.query(dict(p, **changes), self.meta)

    def test_permanent_exemption_has_current_context_and_verified_source(self):
        proof = next(s for s in self.research["sources"] if s["id"] == self.SOURCE)
        self.assertEqual(proof["sha256"], self.SHA)
        self.assertEqual(proof["years_title"], ["2022"])
        self.assertEqual(proof["applies_to_years"], ["2025"])
        self.assertFalse(proof["numeric_import"])
        self.assertTrue(proof["url"].startswith("https://www.diplomatie.gouv.fr/"))
        cell = self.query(2025, "AD/370")["items"][0]["cells"]["initial"]
        note = cell["explanation"]
        self.assertEqual(note["title"], "Réserve : exemption documentée")
        refs = [r for r in note["references"] if r.get("source") == self.SOURCE]
        self.assertEqual({r["page"] for r in refs}, {5, 6})
        self.assertTrue(all(r["sha256"] == self.SHA for r in refs))
        self.assertTrue(any(r.get("source") == "18a66d93f7cacc822267" and
                            r.get("page") == 137 for r in note["references"]))
        self.assertIn("régime applicable", " ".join(note["details"]))

    def test_seven_cases_never_become_numeric_zero_tables(self):
        # An exemption document or a zero LFI cannot populate annual flow cells.
        for year, scope in self.CASES:
            for measure in ("AE", "CP"):
                for constant in (False, True):
                    with self.subTest(year=year, scope=scope, measure=measure, constant=constant):
                        rows = self.query(year, scope, measure, constant=constant)["items"]
                        self.assertEqual(len(rows), 1)
                        self.assertFalse(rows[0]["table_available"])
                        for cell in rows[0]["cells"].values():
                            self.assertIsNone(cell["value"])
                            self.assertIsNone(cell["nominal_cents"])
                            self.assertIsNone(cell["source_cells"])
                            self.assertNotEqual(cell["status"], "published")

    def test_p367_reports_do_not_turn_into_precautionary_reserve(self):
        row = self.query(2023, "DB/367", "AE")["items"][0]
        note = row["cells"]["surgels"]["explanation"]
        detail = " ".join(note["details"])
        self.assertIn("2 000 000 000", detail)
        self.assertIn("ne prouvent", detail)
        self.assertIn("reliquat 2022", detail)
        self.assertEqual(row["cells"]["surgels"]["status"], "table_unavailable")
        self.assertNotEqual(note["title"], "Réserve : exemption documentée")

    def test_plan_relance_qualifications_preserve_year_and_measure_boundaries(self):
        cases = {(r["year"], r["program"]): r for r in self.research["records"]
                 if r["kind"] == "reserves"}
        for prog in ("362", "363", "364"):
            row = cases[2023, prog]
            self.assertEqual(row["outcome"], "partial_initial_exemption_only")
            self.assertTrue(row["evidence_scope"]["initial_only"])
        for prog in ("362", "363"):
            row = cases[2025, prog]
            self.assertEqual(row["evidence_scope"]["annual_no_freeze_measures"], ["CP"])
            self.assertFalse(row["evidence_scope"]["annual_execution_table_found"])
            self.assertIn("AE", row["limitation"])
            self.assertIn("note 34", " ".join(row["evidence_notes"]))

    def test_fine_scope_exclusion_and_topic_do_not_allocate_documentary_amounts(self):
        for year, scope in self.CASES:
            self.assertEqual(self.query(year, scope, exclude=[scope])["items"], [])
            for changes in ({"scope": scope + "/01"}, {"exclude": [scope + "/01"]}):
                p_scope = changes.get("scope", scope)
                rest = {k: v for k, v in changes.items() if k != "scope"}
                rows = self.query(year, p_scope, **rest)["items"]
                self.assertEqual(len(rows), 1)
                for cell in rows[0]["cells"].values():
                    self.assertEqual(cell["status"], "detail_unavailable")
                    self.assertIsNone(cell["value"])
                    self.assertTrue(cell["explanation"]["references"])
        for year in (2023, 2025):
            for mode in ("only", "without"):
                row = self.query(year, "PR/362", topic="maprimerenov", topic_mode=mode)["items"][0]
                for cell in row["cells"].values():
                    self.assertEqual(cell["status"], "detail_unavailable")
                    self.assertIsNone(cell["value"])
                    self.assertIn("MaPrimeRénov", cell["reason"])


if __name__ == "__main__":
    unittest.main()
