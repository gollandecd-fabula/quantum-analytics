from __future__ import annotations

import copy
import importlib.util
import re
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "laranna_quantum_verifier_gate",
    ROOT / "tools/laranna_quantum_verifier_gate.py",
)
assert SPEC is not None and SPEC.loader is not None
gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gate
SPEC.loader.exec_module(gate)


class LarannAQuantumVerifierGateTests(unittest.TestCase):
    def authorization(self, *, enforce_unexpired: bool = True):
        return gate.load_authorization(
            ROOT,
            enforce_unexpired=enforce_unexpired,
        )

    def test_installed_key_signatures_and_exact_bindings_are_valid(self) -> None:
        authorization = self.authorization()
        self.assertEqual(gate.TRUSTED_KEY_ID, authorization.permit["key_id"])
        self.assertEqual(
            authorization.request["work_order_sha256"],
            authorization.work_order["work_order_sha256"],
        )
        self.assertEqual(
            authorization.permit["request_hash"],
            gate.sha256_value(authorization.request),
        )
        self.assertFalse(authorization.permit["release_authorized"])

    def test_every_authorized_path_is_quantum_only_and_canonical(self) -> None:
        authorization = self.authorization()
        paths = authorization.work_order["files_allowed_to_change"]
        self.assertEqual(paths, gate.normalize_paths(paths))
        self.assertFalse(any("imagelab" in path.casefold() for path in paths))
        self.assertIn(
            "docs/evidence/"
            "ARTIFACT_MANIFEST_OVERLAY_PILOT_V3_0_P0_OVERLAY_CLOSURE.json",
            authorization.work_order["implementation_commit_paths"],
        )
        self.assertIn(
            "docs/evidence/"
            "ARTIFACT_MANIFEST_OVERLAY_PILOT_V3_0_P0_OVERLAY_CLOSURE.json",
            authorization.work_order["receipt_commit_paths"],
        )

    def test_permit_mutation_is_rejected(self) -> None:
        authorization = self.authorization()
        permit = copy.deepcopy(authorization.permit)
        permit["action_hash"] = "0" * 64
        with self.assertRaises(gate.GateError) as caught:
            gate.validate_documents(
                authorization.binding,
                authorization.work_order,
                authorization.request,
                permit,
                enforce_unexpired=True,
            )
        self.assertEqual("SIGNATURE_INVALID", caught.exception.code)

    def test_cross_project_mutation_is_rejected(self) -> None:
        authorization = self.authorization()
        request = copy.deepcopy(authorization.request)
        request["project_id"] = "imagelab"
        with self.assertRaises(gate.GateError) as caught:
            gate.validate_documents(
                authorization.binding,
                authorization.work_order,
                request,
                authorization.permit,
                enforce_unexpired=True,
            )
        self.assertIn(
            caught.exception.code,
            {"PROJECT_MISMATCH", "REQUEST_HASH_INVALID", "ACTION_HASH_INVALID"},
        )

    def test_exact_two_commit_implementation_topology_is_valid(self) -> None:
        verdict = gate.execute(ROOT, "verify-implementation", "HEAD")
        self.assertEqual("VERIFIED", verdict["status"])
        self.assertEqual("implementation", verdict["phase"])
        self.assertRegex(verdict["diff_sha256"], r"^[0-9a-f]{64}$")

    def test_extra_path_in_authorization_commit_is_rejected(self) -> None:
        authorization = self.authorization()
        bad = tuple(authorization.work_order["authorization_commit_paths"]) + (
            "src/quantum/forbidden.py",
        )
        with mock.patch.object(gate, "changed_paths", return_value=bad):
            with self.assertRaises(gate.GateError) as caught:
                gate.validate_topology(ROOT, authorization, "HEAD", "implementation")
        self.assertEqual("COMMIT_SCOPE_MISMATCH", caught.exception.code)

    def test_final_gate_fails_closed_before_windows_receipt(self) -> None:
        with self.assertRaises(gate.GateError) as caught:
            gate.execute(ROOT, "verify-final", "HEAD")
        self.assertEqual("TOPOLOGY_INVALID", caught.exception.code)

    def test_diff_digest_is_deterministic(self) -> None:
        authorization = self.authorization()
        head = gate.resolve_commit(ROOT, "HEAD")
        first = gate.diff_digest(ROOT, authorization.base_head, head)
        second = gate.diff_digest(ROOT, authorization.base_head, head)
        self.assertEqual(first, second)
        self.assertTrue(re.fullmatch(r"[0-9a-f]{64}", first))

    def test_github_gate_is_read_only_and_exact_runtime(self) -> None:
        workflow = (
            ROOT / ".github/workflows/laranna-quantum-verifier.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertNotIn("pull_request_target", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertIn('python-version: "3.13.14"', workflow)
        self.assertIn("--require-hashes", workflow)
        self.assertIn("verify-final", workflow)
        self.assertIn("laranna/quantum-verifier", workflow)

    def test_release_workflow_stops_before_build_without_release_permit(self) -> None:
        workflow = (
            ROOT / ".github/workflows/windows-release-gate.yml"
        ).read_text(encoding="utf-8")
        guard = workflow.index("verify-release")
        source_ci = workflow.index("Run complete Foundation suite")
        windows_build = workflow.index("build-install-and-test:")
        self.assertLess(guard, source_ci)
        self.assertLess(guard, windows_build)
        self.assertIn('python-version: "3.13.14"', workflow)
        self.assertNotIn('python-version: "3.12"', workflow)

    def test_codex_instructions_require_preflight_before_edit(self) -> None:
        instructions = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn(
            "python tools/laranna_quantum_verifier_gate.py preflight",
            instructions,
        )
        self.assertIn("Before changing any tracked or untracked", instructions)
        self.assertIn("ImageLab is a different project", instructions)
        self.assertIn("Never squash, reorder, merge into, or append", instructions)

    def test_oss_runtime_is_exactly_hash_locked(self) -> None:
        requirements = (
            ROOT / "requirements/laranna-quantum-verifier.txt"
        ).read_text(encoding="utf-8")
        bom = (
            ROOT / "docs/evidence/laranna_quantum/OSS_BOM.md"
        ).read_text(encoding="utf-8")
        expected = {
            "cryptography==49.0.0": (
                "cbc77da8c523d5abd028635ba850a6966fcee2c82e2bf65a41d1d8afe0f98be9"
            ),
            "cffi==2.1.0": (
                "799416bae98336e400981ff6e532d67d5c709cfb30afb79865a1315f94b0e224"
            ),
            "pycparser==3.0": (
                "b727414169a36b7d524c1c3e31839a521725078d7b2ff038656844266160a992"
            ),
        }
        for package, digest in expected.items():
            self.assertIn(package, requirements)
            self.assertIn(f"--hash=sha256:{digest}", requirements)
            self.assertIn(digest, bom)
        self.assertIn("binary-only", bom)
        self.assertIn("ImageLab is excluded", bom)


if __name__ == "__main__":
    unittest.main()
