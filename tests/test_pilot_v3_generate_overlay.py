from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path

from tools import pilot_v3_generate_overlay as pilot


class PilotV3GenerateOverlayTests(unittest.TestCase):
    repo_root = Path(__file__).resolve().parents[1]

    def test_generates_all_712_canonical_requirements(self) -> None:
        payload = pilot.generate(self.repo_root)
        entries = payload["entries"]
        ids = [item["requirement_id"] for item in entries]
        self.assertEqual(len(entries), 712)
        self.assertEqual(len(set(ids)), 712)
        self.assertEqual(payload["canonical_requirement_count"], 712)
        self.assertEqual(payload["protocol_sha256"], pilot.m9.EXPECTED_PROTOCOL_SHA256)
        self.assertEqual(
            payload["canonical_registry_set_sha256"],
            pilot.m9.EXPECTED_REGISTRY_SET_SHA256,
        )

    def test_overlay_schema_is_literal_and_production_status_is_unchanged(self) -> None:
        payload = pilot.generate(self.repo_root)
        fields = {
            "requirement_id",
            "pilot_applicability",
            "pilot_priority",
            "pilot_dependency",
            "pilot_action",
            "pilot_test",
            "pilot_target_evidence_level",
            "pilot_evidence_ids",
            "pilot_status",
            "justification",
            "production_status_unchanged",
        }
        self.assertTrue(payload["production_status_unchanged"])
        self.assertFalse(payload["release_authorized"])
        self.assertEqual(payload["pilot_decision"], "PILOT_BLOCKED")
        self.assertEqual(payload["production_release_decision"], "RELEASE_BLOCKED")
        for entry in payload["entries"]:
            self.assertEqual(set(entry), fields)
            self.assertTrue(entry["production_status_unchanged"])
            self.assertEqual(entry["pilot_status"], "NOT_STARTED")
            self.assertIn(
                entry["pilot_applicability"],
                {"REQUIRED", "APPLICABLE_REGRESSION", "POST_PILOT"},
            )

    def test_generator_is_deterministic(self) -> None:
        first = pilot.generate(self.repo_root)
        second = pilot.generate(self.repo_root)
        self.assertEqual(first, second)

    def test_governing_work_order_signature_and_parent_are_exact(self) -> None:
        path = (
            self.repo_root
            / "docs/evidence/pilot_v3_0/WORK_ORDER_P0_CANONICAL_EXECUTION_002.json"
        )
        work_order = json.loads(path.read_text(encoding="utf-8"))
        actual = work_order["work_order_sha256"]
        unsigned = copy.deepcopy(work_order)
        unsigned.pop("work_order_sha256")
        canonical = json.dumps(
            unsigned,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.assertEqual(actual, hashlib.sha256(canonical).hexdigest())
        self.assertEqual(work_order["parent_exact_head"], "9ddb908c77e033edc7e3712014d6d15da2e5e7d0")
        self.assertEqual(work_order["canonical_branch"], "fix/quantum-pilot-v3-canonical")
        self.assertFalse(work_order["release_authorized"])


if __name__ == "__main__":
    unittest.main()
