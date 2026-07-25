from __future__ import annotations

import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch

from tests import integration_manifest_support_m8 as manifest_support


ROOT = Path(__file__).resolve().parents[1]
STAGE_B_BLOB_SHA = "e132b51f2dae47777d379304731e1b7738d47aac"


def git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


class WbReleaseR2PlanReconciliationTests(unittest.TestCase):
    def read(self, path: str) -> str:
        return (ROOT / path).read_text(encoding="utf-8")

    def test_historical_stage_b_is_byte_preserved(self) -> None:
        data = (ROOT / "docs/evidence/STAGE_B_EXECUTION_STATE.yaml").read_bytes()
        self.assertEqual(git_blob_sha(data), STAGE_B_BLOB_SHA)

    def test_current_state_has_one_live_pointer(self) -> None:
        text = self.read("docs/governance/CURRENT_STATE.md")
        self.assertEqual(
            text.count("docs/evidence/WB_RELEASE_R2_EXECUTION_STATE.yaml"),
            1,
        )
        self.assertIn("historical Stage-B snapshot", text)
        self.assertEqual(text.count("Current unit: `M9"), 1)
        self.assertIn("## Historical Stage-B compatibility markers", text)
        self.assertLess(
            text.index("docs/evidence/WB_RELEASE_R2_EXECUTION_STATE.yaml"),
            text.index("## Historical Stage-B compatibility markers"),
        )
        self.assertIn(
            "AUTHORIZED_FOR_CLOSED_PILOT_PENDING_ADMISSION_CONTROLS",
            text,
        )

    def test_namespace_and_exact_heads_are_unambiguous(self) -> None:
        state = self.read("docs/evidence/WB_RELEASE_R2_EXECUTION_STATE.yaml")
        for unit in (
            "WBR2-M0:",
            "WBR2-M1:",
            "WBR2-M2:",
            "WBR2-M3:",
            "WBR2-M4:",
            "WBR2-GOV-R1:",
            "WBR2-M5:",
            "WBR2-M6:",
        ):
            self.assertEqual(state.count(unit), 1)
        for digest in (
            "e32a7e9ec77eb8abd051f7f1cc7ba32b22ce33fb",
            "ad5229bbaca3cf8ae692ecb09f54220cde1db16b",
            "3aad43573b205a98e2f2f718e208c8ba763d535e",
            "f6df81ee62f7ee419c0303886362d917b6d82103",
            "050ce0cbae33dd06d0eee1dafb3676addf3dfee0",
            "d89c29edfa93ecc61290a0fdeb9e218214638f7d",
        ):
            self.assertIn(digest, state)

    def test_m5_is_next_but_not_integrated_and_m6_is_unassigned(self) -> None:
        state = self.read("docs/evidence/WB_RELEASE_R2_EXECUTION_STATE.yaml")
        self.assertIn("title: Scheduled weekly and monthly reports", state)
        self.assertIn("state: VALIDATED_CANDIDATE_NOT_INTEGRATED", state)
        self.assertIn(
            "candidate_exact_head: 1563b9c9de6a78142930719073f43e2b931eaa6e",
            state,
        )
        self.assertIn("integration_authorized: false", state)
        self.assertIn("state: UNASSIGNED_NOT_AUTHORIZED", state)

    def test_safety_boundaries_remain_fail_closed(self) -> None:
        state = self.read("docs/evidence/WB_RELEASE_R2_EXECUTION_STATE.yaml")
        for expected in (
            "scope: WB_ONLY",
            "ozon: DEFERRED",
            "gatekeeper: DISCONNECTED",
            "marketplace_writes: DISABLED",
            "main_merge: NOT_AUTHORIZED",
            "release: BLOCKED",
            "physical_user_path_l5: UNVERIFIED",
        ):
            self.assertIn(expected, state)

    def test_governance_overlay_is_separate_from_r100(self) -> None:
        self.assertEqual(len(manifest_support.FINAL_NAMES), 99)
        self.assertEqual(
            manifest_support.FINAL_NAMES[-1],
            "ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R99.json",
        )
        self.assertEqual(
            manifest_support.GOVERNANCE_OVERLAY[0],
            "ARTIFACT_MANIFEST_OVERLAY_WB_RELEASE_R2_GOV_R1.json",
        )

    def test_governance_overlay_rejects_wrong_r99_anchor(self) -> None:
        original = manifest_support._core._read_overlay

        def fake(name: str):
            raw, value = original(name)
            if name == manifest_support.GOVERNANCE_OVERLAY[0]:
                value = dict(value)
                value[manifest_support.GOVERNANCE_OVERLAY[1]] = "0" * 40
            return raw, value

        with patch.object(manifest_support._core, "_read_overlay", side_effect=fake):
            with self.assertRaisesRegex(
                AssertionError,
                "ARTIFACT_MANIFEST_OVERLAY_BASE_MISMATCH",
            ):
                manifest_support.load_effective_manifest()

    def test_rtm_does_not_predeclare_pass_or_leave_source_work_not_started(self) -> None:
        rtm = self.read(
            "docs/evidence/WB_RELEASE_R2_PLAN_RECONCILIATION_RTM.json"
        )
        self.assertNotIn('"NOT_STARTED"', rtm)
        self.assertNotIn('"PASS"', rtm)
        self.assertIn(
            '"AWAITING_EXACT_HEAD_GITHUB_ACTIONS"',
            rtm,
        )
        self.assertIn(
            '"dynamic_exact_head_ci_and_pr_status": '
            '"AUTHORITATIVE_IN_VALIDATION_PR_AND_ISSUE_124"',
            rtm,
        )

    def test_no_product_runtime_paths_are_in_reconciliation_scope(self) -> None:
        rtm = self.read(
            "docs/evidence/WB_RELEASE_R2_PLAN_RECONCILIATION_RTM.json"
        )
        self.assertNotIn('"src/', rtm)
        self.assertIn('"M5 product integration"', rtm)
        self.assertIn('"M6 invention or assignment"', rtm)


if __name__ == "__main__":
    unittest.main()
