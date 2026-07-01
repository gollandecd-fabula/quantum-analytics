from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RealCommercialDataPilotContractTests(unittest.TestCase):
    def test_machine_plan_requires_real_data_and_keeps_writes_blocked(self) -> None:
        text = (ROOT / "docs/governance/ASSURANCE_EXECUTION_PLAN_2026_07_08.yaml").read_text()
        self.assertIn("real_commercial_data: REQUIRED_FOR_CLOSED_PILOT", text)
        self.assertIn("raw_data_in_external_model_prompts: PROHIBITED", text)
        self.assertIn("marketplace_write_capability: DISABLED", text)
        self.assertIn("authorized_real_dataset_admitted: true", text)
        self.assertNotIn("NOT_ADMITTED_WITHOUT_SEPARATE_GATE", text)

    def test_human_plan_has_admission_gate_and_no_synthetic_only_boundary(self) -> None:
        text = (ROOT / "docs/governance/ASSURANCE_EXECUTION_PLAN_2026_07_08.md").read_text()
        self.assertIn("Real commercial data admission", text)
        self.assertIn("DECLARED → QUARANTINED → VALIDATED → ADMITTED", text)
        self.assertIn("raw commercial data", text.lower())
        self.assertNotIn("synthetic-only unless", text)

    def test_live_state_records_r3_authorization_not_unconditional_admission(self) -> None:
        current = (ROOT / "docs/governance/CURRENT_STATE.md").read_text()
        execution = (ROOT / "docs/evidence/STAGE_B_EXECUTION_STATE.yaml").read_text()
        self.assertIn("AUTHORIZED_FOR_CLOSED_PILOT_PENDING_ADMISSION_CONTROLS", current)
        self.assertIn("REQUIRED_FOR_CLOSED_PILOT_PENDING_ADMISSION_CONTROLS", execution)
        self.assertIn("production_release: BLOCKED", execution)

    def test_admission_contract_prohibits_raw_data_in_external_models(self) -> None:
        text = (ROOT / "docs/security/REAL_COMMERCIAL_DATA_ADMISSION_CONTRACT_2026_07_08.md").read_text()
        self.assertIn("Raw real commercial data must not be sent to OpenAI, DeepSeek", text)
        self.assertIn("Only `ADMITTED` data may be used", text)
        self.assertIn("Cross-tenant access attempts fail closed", text)


if __name__ == "__main__":
    unittest.main()
