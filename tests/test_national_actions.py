import json
import unittest
from pathlib import Path
from budget_service.rap_validation import validate_action


ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "budget_service" / "data" / "actions-national.json"


class NationalActionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(FILE.read_text(encoding="utf-8"))
        cls.groups = cls.data["groups"]

    def test_expected_reviewed_coverage(self):
        self.assertEqual(len(self.groups), 1401)
        self.assertEqual(len({(g["year"], g["mission"], g["program"]) for g in self.groups}), 351)
        self.assertEqual(len({(g["year"], g["mission"]) for g in self.groups}), 94)
        self.assertEqual(sum(len(g["actions"]) for g in self.groups), 7120)

    def test_every_group_reconciles_to_its_unchanged_parents(self):
        for group in self.groups:
            with self.subTest(year=group["year"], mission=group["mission"],
                              program=group["program"], measure=group["measure"], stage=group["stage"]):
                if group.get('review_required'):
                    self.assertFalse(group['reconciliation']['accepted'])
                    self.assertGreater(abs(group['reconciliation']['difference_cents']),1000)
                    self.assertTrue(group['reconciliation_note'])
                    with self.assertRaises(AssertionError):validate_action(group)
                else:validate_action(group)

    def test_codes_labels_pages_and_subactions_are_unambiguous(self):
        for group in self.groups:
            self.assertGreater(group["page"], 0)
            self.assertGreater(group["total_page"], 0)
            self.assertEqual(len(group["actions"]), len({a["code"] for a in group["actions"]}))
            for action in group["actions"]:
                self.assertRegex(action["code"], r"^\d{2}$")
                self.assertTrue(action["label"].strip())
                self.assertGreater(action["page"], 0)
                children = action.get("subactions", [])
                self.assertEqual(len(children), len({child["code"] for child in children}))
                if children:
                    from budget_service.rap_validation import validate_action_subactions
                    validate_action_subactions(group,action)
                for child in children:
                    self.assertTrue(child["label"].strip())
                    self.assertGreater(child["page"], 0)


if __name__ == "__main__":
    unittest.main()
