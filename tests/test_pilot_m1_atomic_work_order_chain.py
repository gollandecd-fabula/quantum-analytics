from __future__ import annotations

import copy
import hashlib
import json
import unittest

from tools import m9_work_order_chain as chain


def _signed(value: dict, field: str = "work_order_sha256") -> dict:
    result = copy.deepcopy(value)
    result.pop(field, None)
    payload = json.dumps(
        result,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    result[field] = hashlib.sha256(payload).hexdigest()
    return result


def _work_order(work_order_id: str, allowed: list[str]) -> dict:
    return _signed(
        {
            "artifact_type": "SIGNED_WORK_ORDER",
            "schema_version": "3.0.0",
            "work_order_id": work_order_id,
            "files_allowed_to_change": allowed,
            "files_forbidden_to_change": ["src/**", "requirements/**"],
            "product_change_authorized": False,
            "release_authorized": False,
        }
    )


class PilotM1AtomicWorkOrderChainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.primary = _work_order("WO-PRIMARY", ["a.txt"])
        self.corrective = _work_order("WO-CORRECTIVE", ["b.txt"])
        self.valid_chain = [
            {
                "parent_exact_head": "1" * 40,
                "result_exact_head": "2" * 40,
                "actual_changed_paths": ["a.txt"],
                "governing_work_order": self.primary,
            },
            {
                "parent_exact_head": "2" * 40,
                "result_exact_head": "3" * 40,
                "actual_changed_paths": ["b.txt"],
                "governing_work_order": self.corrective,
            },
        ]

    def test_valid_two_segment_chain_passes_without_retroactive_scope_expansion(self) -> None:
        report = chain.validate_atomic_work_order_chain(self.valid_chain)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["segment_count"], 2)
        self.assertEqual(report["findings"], [])

    def test_union_against_primary_is_not_used(self) -> None:
        report = chain.validate_atomic_work_order_chain(self.valid_chain)
        self.assertNotIn("WORK_ORDER_SCOPE_VIOLATION:b.txt", report["findings"])

    def test_unlisted_path_is_rejected_in_its_segment(self) -> None:
        candidate = copy.deepcopy(self.valid_chain)
        candidate[1]["actual_changed_paths"].append("c.txt")
        report = chain.validate_atomic_work_order_chain(candidate)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("WORK_ORDER_SCOPE_VIOLATION:1:c.txt", report["findings"])

    def test_forged_work_order_signature_is_rejected(self) -> None:
        candidate = copy.deepcopy(self.valid_chain)
        candidate[1]["governing_work_order"]["files_allowed_to_change"].append("c.txt")
        report = chain.validate_atomic_work_order_chain(candidate)
        self.assertIn("WORK_ORDER_SIGNATURE_INVALID:1", report["findings"])

    def test_broken_parent_continuity_is_rejected(self) -> None:
        candidate = copy.deepcopy(self.valid_chain)
        candidate[1]["parent_exact_head"] = "9" * 40
        report = chain.validate_atomic_work_order_chain(candidate)
        self.assertIn("WORK_ORDER_CHAIN_PARENT_MISMATCH:1", report["findings"])

    def test_product_path_is_rejected_when_not_authorized(self) -> None:
        candidate = copy.deepcopy(self.valid_chain)
        candidate[1]["actual_changed_paths"] = ["src/quantum/application/desktop_center.py"]
        report = chain.validate_atomic_work_order_chain(candidate)
        self.assertIn(
            "PRODUCT_CODE_CHANGED_WITHOUT_REQUIREMENT:1:src/quantum/application/desktop_center.py",
            report["findings"],
        )


if __name__ == "__main__":
    unittest.main()
