from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class B1aExecutionStateTests(unittest.TestCase):
    def test_live_state_marks_b0_complete_and_b1a_active(self) -> None:
        state = (ROOT / "docs/evidence/STAGE_B_EXECUTION_STATE.yaml").read_text(encoding="utf-8")
        current = (ROOT / "docs/governance/CURRENT_STATE.md").read_text(encoding="utf-8")

        self.assertIn("current_unit: B1a", state)
        self.assertRegex(state, r"B0:\n    state: COMPLETE")
        self.assertRegex(state, r"B1a:\n    state: IN_PROGRESS")
        self.assertIn("source_of_truth_for_live_unit_state: true", state)
        self.assertIn("Live execution state: `docs/evidence/STAGE_B_EXECUTION_STATE.yaml`", current)
        self.assertIn("Status: `BUILD_B1A_REVIEW_PENDING`", current)
        self.assertIn("B1b financial calculation implementation is R3 and is not approved", current)


if __name__ == "__main__":
    unittest.main()
