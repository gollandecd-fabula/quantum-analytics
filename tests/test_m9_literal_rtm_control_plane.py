from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools import m9_maximum_assurance_control_plane as m9


class M9LiteralRtmControlPlaneTests(unittest.TestCase):
    repo_root = Path(__file__).resolve().parents[1]
    exact_head = "b" * 40
    allowed_changed_paths = [
        ".github/workflows/m9-maximum-assurance-control-plane.yml",
        "tools/m9_maximum_assurance_control_plane.py",
        "tests/test_m9_maximum_assurance_control_plane.py",
        "tests/test_m9_literal_rtm_control_plane.py",
    ]

    @classmethod
    def setUpClass(cls) -> None:
        cls.ingestion = m9.ingest_literal_rtm(cls.repo_root)
        cls.rows = cls.ingestion["_rows"]
        cls.governing_work_order = m9._load_governing_work_order(cls.repo_root)

    def test_literal_ingestion_binds_all_712_rows_and_hashes(self) -> None:
        report = self.ingestion
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["requirement_count"], 712)
        self.assertEqual(report["unique_requirement_count"], 712)
        self.assertEqual(report["shards_validated"], 12)
        self.assertEqual(report["mandatory_field_count"], 19)
        self.assertEqual(report["protocol_sha256"], m9.EXPECTED_PROTOCOL_SHA256)
        self.assertEqual(report["master_prompt_sha256"], m9.EXPECTED_MASTER_PROMPT_SHA256)
        self.assertEqual(report["ui_reference_sha256"], m9.EXPECTED_UI_REFERENCE_SHA256)
        self.assertEqual(report["registry_set_sha256"], m9.EXPECTED_REGISTRY_SET_SHA256)
        self.assertEqual(report["ui_reference_p0_count"], 24)
        self.assertEqual(report["m1_requirement_count"], 100)
        self.assertEqual(report["findings"], [])

    def test_original_text_and_source_location_are_literal(self) -> None:
        by_id = {row["requirement_id"]: row for row in self.rows}
        row = by_id["REQ-MP2-0142"]
        self.assertEqual(
            row["original_text"],
            "1. Заменить synthetic bootstrap requirements на literal extraction полного Protocol v3.1 без сокращения.",
        )
        self.assertEqual(row["source_location"], "13. Milestone 1 — protocol/control-plane upgrade / paragraph block 215")

    def test_scheduler_is_deterministic_and_selects_signed_primary_requirement(self) -> None:
        context = m9.default_scheduler_context(self.rows, self.governing_work_order)
        first = m9.select_next_requirement(self.rows, context)
        second = m9.select_next_requirement(self.rows, copy.deepcopy(context))
        self.assertEqual(first, second)
        self.assertEqual(first["selected_requirement_id"], "REQ-MP2-0142")
        self.assertEqual(first["scheduler"], "DETERMINISTIC_NO_LLM_SELECTION")
        self.assertTrue(m9._verify_signature(first, "decision_sha256"))

    def test_scheduler_fails_when_required_environment_is_missing(self) -> None:
        context = m9.default_scheduler_context(self.rows, self.governing_work_order)
        context["available_environments"] = []
        with self.assertRaisesRegex(m9.ControlPlaneError, "SCHEDULER_NO_ELIGIBLE_REQUIREMENT"):
            m9.select_next_requirement(self.rows, context)

    def test_parallel_lock_is_rejected(self) -> None:
        with self.assertRaisesRegex(m9.ControlPlaneError, "PARALLEL_REQUIREMENT_LOCK_REJECTED"):
            m9.acquire_exclusive_lock(
                "REQ-MP2-0142",
                "CONTROL_PLANE",
                [{"requirement_id": "REQ-MP2-0013", "state": "ACQUIRED"}],
                self.governing_work_order["work_order_sha256"],
            )

    def test_signed_runtime_work_order_detects_tampering(self) -> None:
        context = m9.default_scheduler_context(self.rows, self.governing_work_order)
        decision = m9.select_next_requirement(self.rows, context)
        lock = m9.acquire_exclusive_lock(
            decision["selected_requirement_id"],
            "CONTROL_PLANE",
            [],
            self.governing_work_order["work_order_sha256"],
        )
        row = next(row for row in self.rows if row["requirement_id"] == decision["selected_requirement_id"])
        work_order = m9.emit_runtime_work_order(
            row, decision, lock, self.governing_work_order, self.exact_head
        )
        self.assertEqual(m9.verify_runtime_work_order(work_order), [])
        tampered = copy.deepcopy(work_order)
        tampered["expected_result"] = "FORGED_PASS"
        self.assertIn(
            "RUNTIME_WORK_ORDER_SIGNATURE_INVALID",
            m9.verify_runtime_work_order(tampered),
        )

    def test_role_privilege_escalation_and_protected_path_are_rejected(self) -> None:
        findings = m9.authorize_role_action(
            "VERIFIER",
            "modify_production",
            [m9.CANONICAL_RTM_INDEX],
        )
        self.assertIn("ROLE_PRIVILEGE_ESCALATION:VERIFIER:modify_production", findings)
        self.assertIn(
            f"PROTECTED_PATH_CHANGE_REJECTED:{m9.CANONICAL_RTM_INDEX}",
            findings,
        )

    def test_all_mandatory_negative_controls_make_gate_red(self) -> None:
        report = m9.run_m1_negative_controls(
            self.repo_root,
            self.rows,
            self.governing_work_order,
            self.exact_head,
        )
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["controls_passed"], 10)
        self.assertEqual(report["controls_total"], 10)
        self.assertTrue(report["all_controls_make_gate_red"])
        self.assertTrue(m9._verify_signature(report, "report_sha256"))

    def test_gate_m1_passes_only_for_signed_scope(self) -> None:
        report = m9.evaluate_m1_gate(
            self.repo_root, self.exact_head, self.allowed_changed_paths
        )
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["literal_rtm_coverage"], 1.0)
        self.assertTrue(report["protocol_hash_bound"])
        self.assertTrue(report["scheduler_deterministic"])
        self.assertEqual(report["exclusive_lock_count"], 1)
        self.assertTrue(report["product_code_unchanged"])
        self.assertFalse(report["release_authorized"])

    def test_gate_m1_rejects_product_path(self) -> None:
        report = m9.evaluate_m1_gate(
            self.repo_root,
            self.exact_head,
            [*self.allowed_changed_paths, "src/quantum/application/desktop_center.py"],
        )
        self.assertEqual(report["status"], "FAIL")
        self.assertIn(
            "PRODUCT_CODE_CHANGED_WITHOUT_REQUIREMENT:src/quantum/application/desktop_center.py",
            report["findings"],
        )

    def test_protocol_hash_mutation_fails_ingestion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            shutil.copytree(
                self.repo_root / "docs/evidence/agent_v3_1",
                root / "docs/evidence/agent_v3_1",
            )
            index_path = root / m9.CANONICAL_RTM_INDEX
            index = json.loads(index_path.read_text(encoding="utf-8"))
            index["protocol_sha256"] = "0" * 64
            index_path.write_text(json.dumps(index), encoding="utf-8")
            report = m9.ingest_literal_rtm(root)
            self.assertEqual(report["status"], "FAIL")
            self.assertIn(
                "RTM_INDEX_BINDING_MISMATCH:protocol_sha256", report["findings"]
            )

    def test_independent_cli_verification_recomputes_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            changed = root / "changed.txt"
            changed.write_text("\n".join(self.allowed_changed_paths) + "\n", encoding="utf-8")
            output = root / "evidence"
            result = subprocess.run(
                [
                    sys.executable,
                    str(self.repo_root / "tools/m9_maximum_assurance_control_plane.py"),
                    "m1-run",
                    "--repo-root",
                    str(self.repo_root),
                    "--output-dir",
                    str(output),
                    "--exact-head",
                    self.exact_head,
                    "--changed-paths-file",
                    str(changed),
                ],
                cwd=self.repo_root,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(
                sorted(path.name for path in output.iterdir()),
                sorted(m9.M1_EVIDENCE_FILES),
            )
            implementation = json.loads((output / "M1_IMPLEMENTATION_REPORT.json").read_text(encoding="utf-8"))
            ingestion = json.loads((output / "M1_LITERAL_RTM_INGESTION_REPORT.json").read_text(encoding="utf-8"))
            negatives = json.loads((output / "M1_NEGATIVE_CONTROL_REPORT.json").read_text(encoding="utf-8"))
            work_order = json.loads((output / "M1_SIGNED_WORK_ORDER.json").read_text(encoding="utf-8"))
            self.assertEqual(implementation["status"], "PASS")
            self.assertEqual(ingestion["requirement_count"], 712)
            self.assertEqual(negatives["controls_passed"], 10)
            self.assertTrue(m9._verify_signature(work_order, "work_order_sha256"))
            self.assertFalse(implementation["release_authorized"])

    def test_only_existing_m9_control_plane_implements_scheduler(self) -> None:
        matches = []
        for path in (self.repo_root / "tools").glob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "DETERMINISTIC_NO_LLM_SELECTION" in text:
                matches.append(path.name)
        self.assertEqual(matches, ["m9_maximum_assurance_control_plane.py"])


if __name__ == "__main__":
    unittest.main()
