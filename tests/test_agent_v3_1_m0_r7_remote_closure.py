from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import unittest

from tests.integration_manifest_support_m8 import load_effective_manifest

ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "docs/evidence/agent_v3_1"
EVIDENCE = ROOT / "docs/evidence"
CLOSURE = AGENT / "M0_R7_REMOTE_BINDING_CLOSURE.json"
STATE = AGENT / "AUTONOMOUS_EXECUTION_STATE_M0_R7_REMOTE_CLOSURE.json"
LEDGER = AGENT / "WORK_ORDER_LEDGER_M0_R7_REMOTE_CLOSURE.json"
FAILED_ATTEMPT = AGENT / "M0_R7_REMOTE_CLOSURE_ATTEMPT_001_FAILURE.json"
CORRECTIVE_WORK_ORDER = AGENT / "WORK_ORDER_M0_R7_REMOTE_CLOSURE_CORRECTIVE_001.json"
OVERLAY = EVIDENCE / "ARTIFACT_MANIFEST_OVERLAY_AGENT_V3_1_M0_R7_REMOTE_CLOSURE.json"
BASE_OVERLAY = EVIDENCE / "ARTIFACT_MANIFEST_OVERLAY_AGENT_V3_1_M0_R7.json"
EXPECTED_COMMIT = "ff4b861ee11a5e437091b30b39228bfc97e95a7e"
EXPECTED_TREE = "df7aecd89c220dc193dd92238b37c395f33f70e9"
EXPECTED_ARTIFACT_DIGEST = "sha256:b4e4331624cda2650fb4e7251f4f1fe1116d6f86f6e9b4fb3f6c3ed3bee66c8a"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _verify_signature(value: dict, field: str) -> bool:
    candidate = copy.deepcopy(value)
    actual = candidate.pop(field)
    return hashlib.sha256(_canonical(candidate)).hexdigest() == actual


def _git_blob(raw: bytes) -> str:
    return hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()


def _validate(closure: dict, state: dict) -> list[str]:
    findings: list[str] = []
    binding = closure.get("binding", {})
    result = closure.get("result", {})
    if binding.get("remote_candidate_commit") != EXPECTED_COMMIT:
        findings.append("CANDIDATE_COMMIT_MISMATCH")
    if binding.get("remote_candidate_tree") != EXPECTED_TREE:
        findings.append("CANDIDATE_TREE_MISMATCH")
    if closure.get("artifact", {}).get("digest") != EXPECTED_ARTIFACT_DIGEST:
        findings.append("ARTIFACT_DIGEST_MISMATCH")
    if result.get("release_authorized") is not False or state.get("release_authorized") is not False:
        findings.append("FORGED_RELEASE_AUTHORIZATION")
    if result.get("m1_started") is not False or state.get("m1", {}).get("started") is not False:
        findings.append("M1_STARTED_WITHOUT_WORK_ORDER")
    if result.get("m0_milestone_complete") is not True or state.get("m0", {}).get("complete") is not True:
        findings.append("M0_NOT_CLOSED")
    return findings


class AgentV31M0R7RemoteClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.closure = _read(CLOSURE)
        cls.state = _read(STATE)
        cls.ledger = _read(LEDGER)
        cls.overlay = _read(OVERLAY)
        cls.failed_attempt = _read(FAILED_ATTEMPT)
        cls.corrective_work_order = _read(CORRECTIVE_WORK_ORDER)

    def test_closure_records_exact_remote_binding(self) -> None:
        self.assertEqual(_validate(self.closure, self.state), [])
        self.assertEqual(self.closure["remote_execution"]["steps"]["targeted_positive_negative_historical_controls"], "15/15 PASS")
        self.assertEqual(self.closure["remote_execution"]["steps"]["manifest_equality"], "2/2 PASS")
        self.assertEqual(self.closure["remote_execution"]["steps"]["complete_source_ci"], "971/971 PASS")
        self.assertEqual(self.closure["scope_evidence"]["changed_path_count"], 45)

    def test_append_only_signatures_and_predecessors_are_valid(self) -> None:
        self.assertTrue(_verify_signature(self.closure, "closure_record_sha256"))
        self.assertTrue(_verify_signature(self.state, "state_snapshot_sha256"))
        self.assertTrue(_verify_signature(self.ledger, "ledger_snapshot_sha256"))
        self.assertTrue(_verify_signature(self.failed_attempt, "failure_record_sha256"))
        self.assertTrue(_verify_signature(self.corrective_work_order, "work_order_sha256"))
        self.assertEqual(self.failed_attempt["status"], "FAILED_NOT_COMMITTED")
        self.assertEqual(self.corrective_work_order["work_order_id"], "WO-M0-R7-CLOSURE-CORRECTIVE-001")
        self.assertEqual(self.state["previous_state_blob_sha"], _git_blob((AGENT / "AUTONOMOUS_EXECUTION_STATE.json").read_bytes()))
        self.assertEqual(self.ledger["previous_ledger_blob_sha"], _git_blob((AGENT / "WORK_ORDER_LEDGER.json").read_bytes()))

    def test_m0_closes_without_elevating_project_or_release(self) -> None:
        self.assertTrue(self.state["m0"]["complete"])
        self.assertFalse(self.state["m1"]["started"])
        self.assertFalse(self.state["m1"]["migration_authorized"])
        self.assertFalse(self.state["release_authorized"])
        self.assertEqual(self.state["physical_l5_status"], "FAILED_OR_UNVERIFIED_CURRENT_ARTIFACT")
        self.assertIn("RELEASE_BLOCKED", self.state["current_decision"])

    def test_closure_overlay_is_effective_and_product_paths_are_absent(self) -> None:
        self.assertEqual(self.overlay["base_agent_v3_1_m0_r7_overlay_git_blob_sha"], _git_blob(BASE_OVERLAY.read_bytes()))
        rows = {row[0]: row for row in load_effective_manifest()["artifacts"]}
        for path, digest, size in self.overlay["entries"]:
            self.assertEqual(rows[path], [path, digest, size])
            self.assertFalse(path.startswith(("src/", "tools/", "scripts/", ".github/workflows/", "requirements/")))

    def test_negative_control_tree_swap_is_detected(self) -> None:
        candidate = copy.deepcopy(self.closure)
        candidate["binding"]["remote_candidate_tree"] = "0" * 40
        self.assertIn("CANDIDATE_TREE_MISMATCH", _validate(candidate, self.state))

    def test_negative_control_artifact_swap_is_detected(self) -> None:
        candidate = copy.deepcopy(self.closure)
        candidate["artifact"]["digest"] = "sha256:" + "0" * 64
        self.assertIn("ARTIFACT_DIGEST_MISMATCH", _validate(candidate, self.state))

    def test_negative_control_forged_release_is_detected(self) -> None:
        candidate = copy.deepcopy(self.state)
        candidate["release_authorized"] = True
        self.assertIn("FORGED_RELEASE_AUTHORIZATION", _validate(self.closure, candidate))

    def test_negative_control_m1_start_without_work_order_is_detected(self) -> None:
        candidate = copy.deepcopy(self.state)
        candidate["m1"]["started"] = True
        self.assertIn("M1_STARTED_WITHOUT_WORK_ORDER", _validate(self.closure, candidate))


if __name__ == "__main__":
    unittest.main()
