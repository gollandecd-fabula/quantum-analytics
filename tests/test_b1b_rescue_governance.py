from __future__ import annotations

import inspect
import unittest
from pathlib import Path

import quantum.finance.runtime as finance_runtime


ROOT = Path(__file__).resolve().parents[1]


class B1bRescueGovernanceTests(unittest.TestCase):
    def test_rescue_preserves_current_real_data_live_state(self) -> None:
        state = (ROOT / "docs/evidence/STAGE_B_EXECUTION_STATE.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("current_unit: R3D1", state)
        self.assertIn("R3_REAL_DATA_PILOT_ADMISSION:", state)
        self.assertIn("state: AUTHORIZED_PENDING_CONTROLS", state)
        self.assertIn(
            "real_commercial_data: REQUIRED_FOR_CLOSED_PILOT_PENDING_ADMISSION_CONTROLS",
            state,
        )
        self.assertIn("marketplace_write_capability: DISABLED", state)
        self.assertIn("production_release: BLOCKED", state)

    def test_rescue_does_not_prematurely_complete_dependent_units(self) -> None:
        state = (ROOT / "docs/evidence/STAGE_B_EXECUTION_STATE.yaml").read_text(
            encoding="utf-8"
        )
        self.assertRegex(state, r"(?s)B1b:\n\s+state: GATED")
        self.assertRegex(state, r"(?s)B2:\n\s+state: GATED")
        self.assertIn("blocker: B1B_NOT_COMPLETE", state)
        self.assertRegex(state, r"(?s)B6:\n\s+state: GATED")
        self.assertIn("blocker: B1B_AND_B2_NOT_COMPLETE", state)

    def test_current_state_keeps_real_data_and_release_boundaries(self) -> None:
        current = (ROOT / "docs/governance/CURRENT_STATE.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("R3D1 — REAL_DATA_PILOT_ADMISSION", current)
        self.assertIn("AUTHORIZED_FOR_CLOSED_PILOT_PENDING_ADMISSION_CONTROLS", current)
        self.assertIn("row-level and aggregate source reconciliation", current)
        self.assertIn("no marketplace write credentials", current)
        self.assertIn("`RELEASE_BLOCKED`", current)

    def test_financial_kernel_remains_preview_only_and_write_free(self) -> None:
        source = inspect.getsource(finance_runtime)
        self.assertIn('PUBLICATION_STATE', source)
        self.assertIn('"SHADOW", "PILOT"', source)
        self.assertIn("PRODUCTION_RELEASE_BLOCKED", source)
        self.assertNotIn("RELEASE_ALLOWED", source)
        self.assertNotIn("marketplace_write", source.lower())
        self.assertNotIn("source_authority_activated = true", source.lower())

    def test_synthetic_golden_fixture_is_not_real_pilot_evidence(self) -> None:
        fixture = (
            ROOT / "tests/contracts/fixtures/b1b-golden-baseline.json"
        ).read_text(encoding="utf-8")
        self.assertIn('"real_commercial_data": false', fixture)
        current = (ROOT / "docs/governance/CURRENT_STATE.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Synthetic fixtures remain required", current)
        self.assertIn("insufficient for `PILOT_READY`", current)


if __name__ == "__main__":
    unittest.main()
