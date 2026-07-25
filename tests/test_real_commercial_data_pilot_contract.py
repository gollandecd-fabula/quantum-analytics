from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RealCommercialDataPilotContractTests(unittest.TestCase):
    def test_machine_plan_requires_real_data_and_keeps_writes_blocked(self) -> None:
        text = (
            ROOT / "docs/governance/ASSURANCE_EXECUTION_PLAN_2026_07_08.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("real_commercial_data: REQUIRED_FOR_CLOSED_PILOT", text)
        self.assertIn("raw_data_in_external_model_prompts: PROHIBITED", text)
        self.assertIn("marketplace_write_capability: DISABLED", text)
        self.assertIn("authorized_real_dataset_admitted: true", text)
        self.assertNotIn("NOT_ADMITTED_WITHOUT_SEPARATE_GATE", text)

    def test_local_disk_encryption_is_not_a_pilot_gate(self) -> None:
        text = (
            ROOT / "docs/governance/ASSURANCE_EXECUTION_PLAN_2026_07_08.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("full_disk_encryption: NOT_REQUIRED", text)
        self.assertIn("application_storage_encryption_at_rest: NOT_REQUIRED", text)
        self.assertIn("local_disk_encryption_required: false", text)
        self.assertNotIn("ENCRYPTION_IN_TRANSIT_AT_REST", text)

    def test_hosted_storage_and_non_loopback_transport_remain_protected(self) -> None:
        text = (
            ROOT / "docs/governance/ASSURANCE_EXECUTION_PLAN_2026_07_08.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("HOSTED_EXTERNAL_STORAGE_ENCRYPTION_AT_REST", text)
        self.assertIn("TLS_FOR_APPROVED_NON_LOOPBACK_TRANSPORT", text)

    def test_human_plan_has_admission_gate_and_local_storage_amendment(self) -> None:
        text = (
            ROOT / "docs/governance/ASSURANCE_EXECUTION_PLAN_2026_07_08.md"
        ).read_text(encoding="utf-8")
        amendment = (
            ROOT
            / "docs/governance/ASSURANCE_EXECUTION_PLAN_2026_07_08_LOCAL_STORAGE_AMENDMENT.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Real commercial data admission", text)
        self.assertIn("DECLARED → QUARANTINED → VALIDATED → ADMITTED", text)
        self.assertIn("full-disk encryption is not required", amendment)
        self.assertIn("local disk encryption is not a P0/P1 finding", amendment)
        self.assertNotIn("synthetic-only unless", text)

    def test_live_state_records_r3_authorization_and_local_exception(self) -> None:
        current = (ROOT / "docs/governance/CURRENT_STATE.md").read_text(
            encoding="utf-8"
        )
        execution = (ROOT / "docs/evidence/STAGE_B_EXECUTION_STATE.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("AUTHORIZED_FOR_CLOSED_PILOT_PENDING_ADMISSION_CONTROLS", current)
        self.assertIn("REQUIRED_FOR_CLOSED_PILOT_PENDING_ADMISSION_CONTROLS", execution)
        self.assertIn("local_disk_encryption: NOT_REQUIRED", execution)
        self.assertIn("production_release: BLOCKED", execution)

    def test_admission_contract_prohibits_raw_data_and_exempts_local_disk(self) -> None:
        text = (
            ROOT
            / "docs/security/REAL_COMMERCIAL_DATA_ADMISSION_CONTRACT_2026_07_08.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Raw real commercial data must not be sent to OpenAI, DeepSeek", text)
        self.assertIn("Only `ADMITTED` data may be used", text)
        self.assertIn("Cross-tenant and same-tenant non-owner access attempts fail closed", text)
        self.assertIn("Full-disk encryption is not required", text)
        self.assertIn("Encryption at rest is required", text)


if __name__ == "__main__":
    unittest.main()
