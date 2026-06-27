from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class B1aExecutionStateTests(unittest.TestCase):
    def test_live_execution_state_matches_current_state_document(self) -> None:
        state = (ROOT / "docs/evidence/STAGE_B_EXECUTION_STATE.yaml").read_text(encoding="utf-8")
        current = (ROOT / "docs/governance/CURRENT_STATE.md").read_text(encoding="utf-8")

        self.assertIn("source_of_truth_for_live_unit_state: true", state)
        self.assertRegex(state, r"B0:\n    state: COMPLETE")
        self.assertIn("Live execution state: `docs/evidence/STAGE_B_EXECUTION_STATE.yaml`", current)

        state_unit = re.search(r"^current_unit: ([A-Za-z0-9]+)$", state, re.MULTILINE)
        current_unit = re.search(r"^Current unit: `([A-Za-z0-9]+) —", current, re.MULTILINE)
        self.assertIsNotNone(state_unit)
        self.assertIsNotNone(current_unit)
        self.assertEqual(state_unit.group(1), current_unit.group(1))

        self.assertIn("production_release: BLOCKED", state)
        self.assertIn("`RELEASE_BLOCKED`", current)
        self.assertIn("marketplace_write_capability: DISABLED", state)


if __name__ == "__main__":
    unittest.main()
