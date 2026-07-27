from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools import m9_maximum_assurance_control_plane as m9


class M9MaximumAssuranceControlPlaneTests(unittest.TestCase):
    exact_head = "a" * 40
    repo_root = Path(__file__).resolve().parents[1]

    def _bundle(self, root: Path) -> Path:
        bundle = root / "bundle"
        m9.bootstrap_bundle(bundle, self.exact_head, self.repo_root)
        return bundle

    def test_bootstrap_emits_literal_release_blocked_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = self._bundle(Path(temporary))
            self.assertEqual(
                sorted(path.name for path in bundle.iterdir()),
                sorted(m9.REQUIRED_ARTIFACTS),
            )
            rtm = m9._read_json(bundle / "REQUIREMENTS_TRACEABILITY_MATRIX.json")
            self.assertEqual(rtm["protocol_version"], "3.1")
            self.assertEqual(rtm["requirement_count"], 712)
            self.assertEqual(len(rtm["requirements"]), 712)
            self.assertNotIn("REQ-M9-001", {row["requirement_id"] for row in rtm["requirements"]})
            report = m9.audit_bundle(bundle, self.exact_head)
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["decision"], "RELEASE_BLOCKED")
            self.assertFalse(report["release_authorized"])
            self.assertFalse(report["marketplace_write_enabled"])

    def test_missing_claim_status_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = self._bundle(Path(temporary))
            ledger = m9._read_json(bundle / "CLAIM_LEDGER.json")
            ledger["claims"][0].pop("status")
            m9._write_json(bundle / "CLAIM_LEDGER.json", ledger)
            findings = m9.validate_bundle(bundle, self.exact_head)
            self.assertIn("CLAIM_STATUS_MISSING:CLM-M9-001", findings)

    def test_forged_l5_claim_is_rejected(self) -> None:
        findings = m9.validate_l5_claim(
            {
                "status": "VERIFIED",
                "level": "L5",
                "physical_pass": False,
                "artifact_sha256": None,
                "installed_root": None,
                "entry_point": None,
                "actual_command_line": None,
                "environment_id": None,
                "evidence_ids": [],
            }
        )
        self.assertEqual(findings, ["FORGED_L5_REJECTED"])

    def test_release_authorization_requires_full_plateau(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = self._bundle(Path(temporary))
            (bundle / "FINAL_RELEASE_DECISION.md").write_text(
                m9._decision_text(self.exact_head, "RELEASE_AUTHORIZED"),
                encoding="utf-8",
            )
            findings = m9.validate_bundle(bundle, self.exact_head)
            self.assertIn("RELEASE_GATE_OPEN_P0_P1", findings)
            self.assertIn("RELEASE_GATE_PHYSICAL_L5_INCOMPLETE", findings)
            self.assertIn("RELEASE_GATE_ARTIFACT_IDENTITY_UNPROVEN", findings)

    def test_marketplace_write_enablement_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = self._bundle(Path(temporary))
            security = m9._read_json(bundle / "SECURITY_REPORT.json")
            security["marketplace_write_enabled"] = True
            m9._write_json(bundle / "SECURITY_REPORT.json", security)
            self.assertIn(
                "MARKETPLACE_WRITES_ENABLED",
                m9.validate_bundle(bundle, self.exact_head),
            )

    def test_historical_harness_negative_controls_all_turn_gate_red(self) -> None:
        report = m9.run_negative_controls(self.exact_head, self.repo_root)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["controls_passed"], 5)
        self.assertEqual(report["controls_total"], 5)


if __name__ == "__main__":
    unittest.main()
