from __future__ import annotations

import json
from pathlib import Path
import unittest

from tests.integration_manifest_support_m8 import load_effective_manifest


ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "docs/evidence/WB_RELEASE_R2_EXECUTION_STATE.yaml"
CURRENT_PATH = ROOT / "docs/governance/CURRENT_STATE.md"
RTM_PATH = ROOT / "docs/evidence/WBR2_M5_CLOSURE_RTM.json"
OVERLAY_PATH = (
    ROOT
    / "docs/evidence"
    / "ARTIFACT_MANIFEST_OVERLAY_WBR2_M5_CLOSURE_R1.json"
)


class Wbr2M5ClosureContracts(unittest.TestCase):
    def test_rtm_and_capability_gate_are_explicit(self) -> None:
        rtm = json.loads(RTM_PATH.read_text(encoding="utf-8"))
        self.assertEqual(rtm["rtm_id"], "WBR2-M5-CLOSURE-R1")
        self.assertEqual(
            rtm["base_exact_head"],
            "5e0e52c0141c5860ea108ba515a073094037ad72",
        )
        self.assertEqual(
            rtm["capability_gate"]["result"],
            "PASS_FOR_GOVERNANCE_CLOSURE_ONLY",
        )
        self.assertIn("src/** changes", rtm["scope"]["forbidden"])

    def test_live_state_records_validated_working_branch(self) -> None:
        state = STATE_PATH.read_text(encoding="utf-8")
        required = (
            "state: VALIDATED_IN_WORKING_BRANCH",
            "exact_head: 5e0e52c0141c5860ea108ba515a073094037ad72",
            "validation_pull_request: 130",
            "validation_pr_state: CLOSED",
            "validation_pr_merged: false",
            "working_branch_fast_forward: COMPLETE",
            "state: UNASSIGNED_NOT_AUTHORIZED",
            "scope: WB_ONLY",
            "ozon: DEFERRED",
            "gatekeeper: DISCONNECTED",
            "marketplace_writes: DISABLED",
            "physical_user_path_l5: UNVERIFIED",
        )
        for marker in required:
            self.assertIn(marker, state)

    def test_current_state_does_not_claim_release_or_l5(self) -> None:
        current = CURRENT_PATH.read_text(encoding="utf-8")
        self.assertIn("Validation PR #130", current)
        self.assertIn("No `WBR2-M6` is assigned or authorized.", current)
        self.assertIn("`RELEASE_BLOCKED`", current)
        self.assertIn("physical installation", current)
        self.assertNotIn("PHYSICAL_L5=PASS", current)

    def test_closure_overlay_is_effective(self) -> None:
        overlay = json.loads(OVERLAY_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            overlay["base_m5_r100_overlay_git_blob_sha"],
            "914a10017125e025eb86968a52b028dfabb05ef2",
        )
        manifest = load_effective_manifest()
        rows = {row[0]: row for row in manifest["artifacts"]}
        for path, digest, size in overlay["entries"]:
            self.assertEqual(rows[path], [path, digest, size])


if __name__ == "__main__":
    unittest.main()
