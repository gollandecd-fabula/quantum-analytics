from __future__ import annotations

import json
from pathlib import Path
import unittest

from tests.integration_manifest_support_m8 import load_effective_manifest


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "docs/evidence/WB_RELEASE_R2_EXECUTION_STATE.yaml"
CURRENT = ROOT / "docs/governance/CURRENT_STATE.md"
RTM = ROOT / "docs/evidence/WBR2_M5_CLOSURE_CORRECTIVE_R2_RTM.json"
OVERLAY = (
    ROOT
    / "docs/evidence"
    / "ARTIFACT_MANIFEST_OVERLAY_WBR2_M5_CLOSURE_R2.json"
)
UNIVERSAL_OVERLAY_PATH = (
    ROOT
    / "docs/evidence"
    / "ARTIFACT_MANIFEST_OVERLAY_UNIVERSAL_PARTIAL_R1.json"
)
XNF1_OVERLAY_PATH = (
    ROOT
    / "docs/evidence"
    / "ARTIFACT_MANIFEST_OVERLAY_XLSX_NAMESPACE_FALLBACK_R1.json"
)
SLR1_OVERLAY_PATH = (
    ROOT
    / "docs/evidence"
    / "ARTIFACT_MANIFEST_OVERLAY_SHORTCUT_LAUNCH_REPAIR_R1.json"
)
QUR2_OVERLAY_PATH = (
    ROOT
    / "docs/evidence"
    / "ARTIFACT_MANIFEST_OVERLAY_QUANTUM_UNIVERSAL_RELAUNCH_R2.json"
)
AGENT_M0_R7_OVERLAY_PATH = (
    ROOT
    / "docs/evidence"
    / "ARTIFACT_MANIFEST_OVERLAY_AGENT_V3_1_M0_R7.json"
)
AGENT_M0_R7_REMOTE_CLOSURE_OVERLAY_PATH = (
    ROOT
    / "docs/evidence"
    / "ARTIFACT_MANIFEST_OVERLAY_AGENT_V3_1_M0_R7_REMOTE_CLOSURE.json"
)
AGENT_M1_OPEN_OVERLAY_PATH = (
    ROOT
    / "docs/evidence"
    / "ARTIFACT_MANIFEST_OVERLAY_AGENT_V3_1_M1_OPEN.json"
)


class Wbr2M5ClosureCorrectiveR2Tests(unittest.TestCase):
    def test_rtm_is_corrective_only(self) -> None:
        rtm = json.loads(RTM.read_text(encoding="utf-8"))
        self.assertEqual(rtm["rtm_id"], "WBR2-M5-CLOSURE-CORRECTIVE-R2")
        self.assertEqual(
            rtm["capability_gate"]["result"],
            "PASS_FOR_GOVERNANCE_CORRECTIVE_ONLY",
        )
        self.assertIn("src/** changes", rtm["forbidden"])

    def test_static_self_reference_is_removed(self) -> None:
        state = STATE.read_text(encoding="utf-8")
        self.assertNotIn("working_branch_exact_head:", state)
        self.assertIn(
            "validated_product_exact_head: "
            "5e0e52c0141c5860ea108ba515a073094037ad72",
            state,
        )
        self.assertIn("containing_governance_head: RESOLVE_FROM_GIT", state)
        self.assertIn(
            "build_evidence_authority: "
            "GITHUB_ACTIONS_AT_CONTAINING_GIT_HEAD",
            state,
        )
        self.assertIn(
            "static_state_claim: DOES_NOT_PREDECLARE_DYNAMIC_BUILD_PASS",
            state,
        )

    def test_safety_and_compatibility_markers_remain(self) -> None:
        state = STATE.read_text(encoding="utf-8")
        current = CURRENT.read_text(encoding="utf-8")
        for marker in (
            "state: VALIDATED_IN_WORKING_BRANCH",
            "state: VALIDATED_CANDIDATE_NOT_INTEGRATED",
            "state: UNASSIGNED_NOT_AUTHORIZED",
            "scope: WB_ONLY",
            "ozon: DEFERRED",
            "gatekeeper: DISCONNECTED",
            "marketplace_writes: DISABLED",
            "release: BLOCKED",
            "physical_user_path_l5: UNVERIFIED",
        ):
            self.assertIn(marker, state)
        self.assertIn(
            "AUTHORIZED_FOR_CLOSED_PILOT_PENDING_ADMISSION_CONTROLS",
            current,
        )
        self.assertIn("does not predeclare a dynamic build PASS", current)

    def test_r2_overlay_is_effective(self) -> None:
        overlay = json.loads(OVERLAY.read_text(encoding="utf-8"))
        self.assertEqual(
            overlay["base_m5_closure_r1_overlay_git_blob_sha"],
            "8323094c94b08894063b7e89b033c640a38e6910",
        )
        rows = {row[0]: row for row in load_effective_manifest()["artifacts"]}
        universal = json.loads(
            UNIVERSAL_OVERLAY_PATH.read_text(encoding="utf-8")
        )
        final = {
            path: [path, digest, size]
            for path, digest, size in overlay["entries"]
        }
        final.update(
            {
                path: [path, digest, size]
                for path, digest, size in universal["entries"]
            }
        )
        xnf1 = json.loads(XNF1_OVERLAY_PATH.read_text(encoding="utf-8"))
        final.update(
            {path: [path, digest, size] for path, digest, size in xnf1["entries"]}
        )
        slr1 = json.loads(SLR1_OVERLAY_PATH.read_text(encoding="utf-8"))
        final.update(
            {path: [path, digest, size] for path, digest, size in slr1["entries"]}
        )
        qur2 = json.loads(QUR2_OVERLAY_PATH.read_text(encoding="utf-8"))
        final.update(
            {path: [path, digest, size] for path, digest, size in qur2["entries"]}
        )
        agent_m0_r7 = json.loads(
            AGENT_M0_R7_OVERLAY_PATH.read_text(encoding="utf-8")
        )
        final.update(
            {
                path: [path, digest, size]
                for path, digest, size in agent_m0_r7["entries"]
            }
        )
        agent_m0_r7_remote_closure = json.loads(
            AGENT_M0_R7_REMOTE_CLOSURE_OVERLAY_PATH.read_text(encoding="utf-8")
        )
        final.update(
            {
                path: [path, digest, size]
                for path, digest, size in agent_m0_r7_remote_closure["entries"]
            }
        )
        agent_m1_open = json.loads(
            AGENT_M1_OPEN_OVERLAY_PATH.read_text(encoding="utf-8")
        )
        final.update(
            {path: [path, digest, size] for path, digest, size in agent_m1_open["entries"]}
        )
        for path, _digest, _size in overlay["entries"]:
            self.assertEqual(rows[path], final[path])


if __name__ == "__main__":
    unittest.main()
