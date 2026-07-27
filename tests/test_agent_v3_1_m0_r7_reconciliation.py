from __future__ import annotations

import base64
import copy
import gzip
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "docs/evidence/agent_v3_1"
SUBJECT_HEAD = "b151e67c2bea8d4d50c5c4a2aeb0695e89921c01"
PROTOCOL_SHA = "be69b8f1f919066c67086d6dd4678acf5e3cb3c4f1db9bc587dc540018601a90"
UI_SHA = "2482074aea312b065b4094792c5676445514dd555d50a064a5ae3e189dc60d13"


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(path)
    return value


def _validate(index: dict, state: dict, inventory: dict, duplicate: dict) -> list[str]:
    findings: list[str] = []
    if index.get("protocol_sha256") != PROTOCOL_SHA:
        findings.append("PROTOCOL_HASH_MISMATCH")
    if index.get("ui_reference_sha256") != UI_SHA:
        findings.append("UI_REFERENCE_HASH_MISMATCH")
    if index.get("requirement_count") != 712:
        findings.append("RTM_COUNT_MISMATCH")
    if state.get("subject_exact_head") != SUBJECT_HEAD:
        findings.append("STATE_HEAD_MISMATCH")
    if state.get("release_authorized") is not False:
        findings.append("FORGED_RELEASE_AUTHORIZATION")
    if inventory.get("subject_exact_head") != SUBJECT_HEAD:
        findings.append("INVENTORY_HEAD_MISMATCH")
    if inventory.get("inventory_evidence", {}).get("entry_count") != 760:
        findings.append("INVENTORY_COUNT_MISMATCH")
    decisions = duplicate.get("decisions", {})
    for key in ("parallel_control_plane_authorized", "parallel_rtm_authorized", "parallel_release_gate_authorized"):
        if decisions.get(key) is not False:
            findings.append("PARALLEL_COMPONENT_AUTHORIZED:" + key)
    return findings


class AgentV31M0R7ReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.index = _read(AGENT / "REQUIREMENTS_TRACEABILITY_MATRIX.json")
        cls.state = _read(AGENT / "AUTONOMOUS_EXECUTION_STATE.json")
        cls.inventory = _read(AGENT / "CURRENT_ARCHITECTURE_INVENTORY.json")
        cls.duplicate = _read(AGENT / "DUPLICATE_RISK_ASSESSMENT.json")

    def test_canonical_registry_materializes_712_unique_requirements(self) -> None:
        rows = []
        for shard in self.index["shards"]:
            path = ROOT / shard["path"]
            raw = path.read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), shard["sha256"])
            value = json.loads(raw)
            if shard["payload_encoding"] == "plain-json-tuples":
                data = value["rows"]
            else:
                compressed = base64.b64decode(value["payload"])
                self.assertEqual(hashlib.sha256(compressed).hexdigest(), value["compressed_sha256"])
                unpacked = gzip.decompress(compressed)
                self.assertEqual(hashlib.sha256(unpacked).hexdigest(), value["uncompressed_sha256"])
                data = json.loads(unpacked)
            self.assertEqual(len(data), shard["requirement_count"])
            rows.extend(data)
        self.assertEqual(len(rows), 712)
        self.assertEqual(len({row[0] for row in rows}), 712)
        self.assertEqual(self.index["protocol_sha256"], PROTOCOL_SHA)
        self.assertEqual(self.index["ui_reference_sha256"], UI_SHA)

    def test_current_head_inventory_and_fail_closed_state(self) -> None:
        self.assertEqual(_validate(self.index, self.state, self.inventory, self.duplicate), [])
        self.assertFalse(self.state["release_authorized"])
        self.assertFalse(self.state["marketplace_writes_enabled"])
        self.assertIn("RELEASE_BLOCKED", self.state["current_decision"])

    def test_historical_evidence_is_not_rebound_to_current_head(self) -> None:
        self.assertNotEqual(self.index["subject_exact_head"], SUBJECT_HEAD)
        self.assertEqual(self.index["validation"]["evidence_level"], "L0_STATIC")
        self.assertFalse(self.index["claim_policy"]["release_claim_allowed"])

    def test_negative_control_protocol_hash_swap_is_detected(self) -> None:
        candidate = copy.deepcopy(self.index)
        candidate["protocol_sha256"] = "0" * 64
        self.assertIn("PROTOCOL_HASH_MISMATCH", _validate(candidate, self.state, self.inventory, self.duplicate))

    def test_negative_control_forged_release_is_detected(self) -> None:
        candidate = copy.deepcopy(self.state)
        candidate["release_authorized"] = True
        self.assertIn("FORGED_RELEASE_AUTHORIZATION", _validate(self.index, candidate, self.inventory, self.duplicate))

    def test_negative_control_parallel_rtm_is_detected(self) -> None:
        candidate = copy.deepcopy(self.duplicate)
        candidate["decisions"]["parallel_rtm_authorized"] = True
        self.assertIn("PARALLEL_COMPONENT_AUTHORIZED:parallel_rtm_authorized", _validate(self.index, self.state, self.inventory, candidate))

    def test_negative_control_inventory_head_swap_is_detected(self) -> None:
        candidate = copy.deepcopy(self.inventory)
        candidate["subject_exact_head"] = "0" * 40
        self.assertIn("INVENTORY_HEAD_MISMATCH", _validate(self.index, self.state, candidate, self.duplicate))


if __name__ == "__main__":
    unittest.main()
