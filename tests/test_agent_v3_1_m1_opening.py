from __future__ import annotations

import base64
import copy
import gzip
import hashlib
import json
from pathlib import Path
import unittest

from tests.integration_manifest_support_m8 import load_effective_manifest

ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "docs/evidence/agent_v3_1"
EVIDENCE = ROOT / "docs/evidence"
SCOPE = AGENT / "M1_EXISTING_M9_MIGRATION_RTM.json"
GATE = AGENT / "M1_CAPABILITY_GATE.json"
WORK_ORDER = AGENT / "WORK_ORDER_M1_EXISTING_M9_MIGRATION_001.json"
STATE = AGENT / "AUTONOMOUS_EXECUTION_STATE_M1_OPEN.json"
LEDGER = AGENT / "WORK_ORDER_LEDGER_M1_OPEN.json"
INDEX = AGENT / "REQUIREMENTS_TRACEABILITY_MATRIX.json"
OVERLAY = EVIDENCE / "ARTIFACT_MANIFEST_OVERLAY_AGENT_V3_1_M1_OPEN.json"
M1_RUNTIME_OVERLAY = EVIDENCE / "ARTIFACT_MANIFEST_OVERLAY_AGENT_V3_1_M1.json"
BASE_OVERLAY = EVIDENCE / "ARTIFACT_MANIFEST_OVERLAY_AGENT_V3_1_M0_R7_REMOTE_CLOSURE.json"
EXPECTED_BASE_COMMIT = "848c3eb847b7812e352ff851d1574de429d23724"
EXPECTED_BASE_TREE = "38f178153e39f433a55c57de8401125ba2825d19"
EXPECTED_PROTOCOL = "be69b8f1f919066c67086d6dd4678acf5e3cb3c4f1db9bc587dc540018601a90"
EXPECTED_RTM_HASH = "4cd2561b2da074b73ebe9ac8a3ccec6f2c890f7f7bf7998ac1a0ca698ed1037a"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _verify(value: dict, field: str) -> bool:
    candidate = copy.deepcopy(value)
    actual = candidate.pop(field)
    return hashlib.sha256(_canonical(candidate)).hexdigest() == actual


def _git_blob(raw: bytes) -> str:
    return hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()


def _canonical_rows() -> dict[str, dict]:
    index = _read(INDEX)
    rows: dict[str, dict] = {}
    fields = None
    for shard in index["shards"]:
        raw = (ROOT / shard["path"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != shard["sha256"]:
            raise AssertionError("SHARD_HASH_MISMATCH")
        payload = json.loads(raw)
        fields = fields or payload.get("row_fields")
        if shard["payload_encoding"] == "plain-json-tuples":
            tuples = payload.get("requirements") or payload.get("rows") or payload.get("tuples")
        else:
            decoded = gzip.decompress(base64.b64decode(payload["payload"]))
            if hashlib.sha256(decoded).hexdigest() != shard["uncompressed_sha256"]:
                raise AssertionError("SHARD_UNCOMPRESSED_HASH_MISMATCH")
            inner = json.loads(decoded)
            tuples = inner if isinstance(inner, list) else inner.get("requirements") or inner.get("rows") or inner.get("tuples")
        for item in tuples:
            row = dict(zip(fields, item))
            rows[row["requirement_id"]] = row
    return rows


class AgentV31M1OpeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scope = _read(SCOPE)
        cls.gate = _read(GATE)
        cls.work_order = _read(WORK_ORDER)
        cls.state = _read(STATE)
        cls.ledger = _read(LEDGER)
        cls.overlay = _read(OVERLAY)

    def test_all_opening_records_are_hash_signed(self) -> None:
        self.assertTrue(_verify(self.scope, "m1_scope_sha256"))
        self.assertTrue(_verify(self.gate, "capability_gate_sha256"))
        self.assertTrue(_verify(self.work_order, "work_order_sha256"))
        self.assertTrue(_verify(self.state, "state_snapshot_sha256"))
        self.assertTrue(_verify(self.ledger, "ledger_snapshot_sha256"))

    def test_scope_is_literal_subset_of_canonical_712_rows(self) -> None:
        rows = _canonical_rows()
        self.assertEqual(len(rows), 712)
        self.assertEqual(self.scope["canonical_rtm"]["requirement_count"], 712)
        self.assertEqual(self.scope["canonical_rtm"]["registry_set_sha256"], EXPECTED_RTM_HASH)
        self.assertEqual(self.scope["selected_requirement_count"], 65)
        for entry in self.scope["selected_requirements"]:
            row = entry["canonical_row"]
            self.assertEqual(rows[row["requirement_id"]], row)
            self.assertEqual(hashlib.sha256(_canonical(row)).hexdigest(), entry["canonical_row_sha256"])
            self.assertEqual(row["milestone"], "M1")

    def test_source_hashes_and_m0_binding_are_immutable(self) -> None:
        self.assertEqual(self.scope["canonical_rtm"]["protocol_sha256"], EXPECTED_PROTOCOL)
        self.assertEqual(self.scope["base_commit"], EXPECTED_BASE_COMMIT)
        self.assertEqual(self.scope["base_tree"], EXPECTED_BASE_TREE)
        self.assertEqual(self.gate["base_commit"], EXPECTED_BASE_COMMIT)
        self.assertEqual(self.state["base_tree"], EXPECTED_BASE_TREE)

    def test_capability_gate_assigns_existing_m9_method_only(self) -> None:
        self.assertEqual(self.gate["gate_result"], "PASS_METHOD_SUPPORTED")
        self.assertIn("existing historical tools/m9_maximum_assurance_control_plane.py", self.gate["assigned_method"])
        self.assertIn("parallel controller", self.gate["forbidden_substitutions"])
        self.assertFalse(self.gate["release_authorized"])

    def test_work_order_has_required_audit_fields_and_exact_lock(self) -> None:
        self.assertEqual(self.work_order["work_order_id"], "WO-M1-EXISTING-M9-MIGRATION-001")
        self.assertEqual(self.work_order["active_milestone"], "M1")
        self.assertEqual(self.work_order["assigned_role"], "IMPLEMENTER")
        self.assertEqual(self.work_order["exclusive_lock"]["state"], "ACQUIRED_FOR_IMPLEMENTATION")
        self.assertFalse(self.work_order["exclusive_lock"]["parallel_lock_authorized"])
        for field in ("change_boundary", "files_allowed_to_change", "files_forbidden_to_change", "hypothesis", "next_test", "expected_result", "rollback_condition", "rollback_command", "target_evidence_level"):
            self.assertTrue(self.work_order[field])

    def test_product_ui_installer_config_and_scheduled_report_paths_are_forbidden(self) -> None:
        forbidden = " ".join(self.work_order["files_forbidden_to_change"])
        for marker in ("src/**", "installer", "UI", "scheduled-report", "configuration migration"):
            self.assertIn(marker, forbidden)
        self.assertFalse(self.work_order["product_change_authorized"])
        self.assertFalse(self.work_order["release_authorized"])

    def test_state_opens_m1_without_claiming_implementation_or_release(self) -> None:
        self.assertTrue(self.state["m0"]["complete"])
        self.assertTrue(self.state["m1"]["started"])
        self.assertTrue(self.state["m1"]["migration_authorized"])
        self.assertFalse(self.state["m1"]["implementation_started"])
        self.assertFalse(self.state["m1"]["complete"])
        self.assertFalse(self.state["release_authorized"])
        self.assertEqual(self.state["canonical_rtm"]["runtime_ingestion"], "NOT_STARTED")

    def test_append_only_predecessors_and_ledger_match(self) -> None:
        previous_state = AGENT / "AUTONOMOUS_EXECUTION_STATE_M0_R7_REMOTE_CLOSURE.json"
        previous_ledger = AGENT / "WORK_ORDER_LEDGER_M0_R7_REMOTE_CLOSURE.json"
        self.assertEqual(self.state["previous_state_blob_sha"], _git_blob(previous_state.read_bytes()))
        self.assertEqual(self.ledger["previous_ledger_blob_sha"], _git_blob(previous_ledger.read_bytes()))
        self.assertEqual(self.ledger["active_work_order_id"], self.work_order["work_order_id"])
        self.assertEqual(self.ledger["entries"][0]["work_order_sha256"], self.work_order["work_order_sha256"])

    def test_negative_controls_detect_forged_signature_and_scope(self) -> None:
        forged = copy.deepcopy(self.work_order)
        forged["product_change_authorized"] = True
        self.assertFalse(_verify(forged, "work_order_sha256"))
        forged = copy.deepcopy(self.scope)
        forged["selected_requirements"][0]["canonical_row"]["original_text"] += " forged"
        self.assertFalse(_verify(forged, "m1_scope_sha256"))

    def test_opening_overlay_is_effective(self) -> None:
        self.assertEqual(self.overlay["base_agent_v3_1_m0_r7_remote_closure_overlay_git_blob_sha"], _git_blob(BASE_OVERLAY.read_bytes()))
        rows = {row[0]: row for row in load_effective_manifest()["artifacts"]}
        latest = _read(M1_RUNTIME_OVERLAY)
        expected = {
            path: [path, digest, size]
            for path, digest, size in self.overlay["entries"]
        }
        expected.update(
            {
                path: [path, digest, size]
                for path, digest, size in latest["entries"]
            }
        )
        for path, _digest, _size in self.overlay["entries"]:
            self.assertEqual(rows[path], expected[path])
            self.assertFalse(path.startswith(("src/", "tools/", "scripts/", ".github/workflows/", "requirements/")))


if __name__ == "__main__":
    unittest.main()
