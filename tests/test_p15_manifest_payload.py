from __future__ import annotations

import base64
import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OVERLAY_PATH = ROOT / "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_P15.json"
CLOSURE_OVERLAY_PATH = (
    ROOT / "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_P15_CLOSURE.json"
)
P15_PATHS = (
    "docs/evidence/STAGE_B_EXECUTION_STATE.yaml",
    "docs/evidence/STAGE_P1_5_EXECUTION_STATE.yaml",
    "docs/governance/CURRENT_STATE.md",
    "docs/ux/UX_ONBOARDING_EXCEPTION_INBOX_CONTRACT.md",
    "schemas/exception-inbox.schema.json",
    "schemas/ux-configuration-form.schema.json",
    "schemas/ux-view.schema.json",
    "src/quantum/ux/__init__.py",
    "src/quantum/ux/runtime.py",
    "src/quantum/ux/validation.py",
    "tests/test_a0_p15_manifest_payload.py",
    "tests/test_b1a_artifact_manifest.py",
    "tests/test_p15_contract_alignment.py",
    "tests/test_p15_manifest_payload.py",
    "tests/test_p15_review_remediation.py",
    "tests/test_p15_schema_alignment.py",
    "tests/test_p15_ux_adversarial.py",
    "tests/test_p15_ux_runtime.py",
)
P15_SNAPSHOT_ENTRIES = {
    "tests/test_b1a_artifact_manifest.py": [
        "tests/test_b1a_artifact_manifest.py",
        base64.b64decode("SW+hmnweKSFft7iL5mdDk4RqHfzFEM3gimWKlCz7Fig=", validate=True).hex(),
        9630,
    ],
    "tests/test_p15_manifest_payload.py": [
        "tests/test_p15_manifest_payload.py",
        base64.b64decode("8Ue4JwxQhlMeurSnbijS0WOaufQs7Ehy4wrJArHPE60=", validate=True).hex(),
        2773,
    ],
}


def git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def expected_entries() -> list[list[object]]:
    entries: list[list[object]] = []
    for path in P15_PATHS:
        if path in P15_SNAPSHOT_ENTRIES:
            entries.append(P15_SNAPSHOT_ENTRIES[path])
            continue
        data = (ROOT / path).read_bytes()
        entries.append([path, hashlib.sha256(data).hexdigest(), len(data)])
    return entries


def effective_entries() -> list[list[object]]:
    base_bytes = OVERLAY_PATH.read_bytes()
    base = json.loads(base_bytes.decode("utf-8"))
    closure = json.loads(CLOSURE_OVERLAY_PATH.read_text(encoding="utf-8"))
    if closure["base_p15_overlay_git_blob_sha"] != git_blob_sha(base_bytes):
        raise AssertionError("P15_CLOSURE_OVERLAY_BASE_MISMATCH")
    entries = {row[0]: row for row in base["entries"]}
    for row in closure["entries"]:
        entries[row[0]] = row
    for path in closure.get("remove_paths", []):
        entries.pop(path, None)
    return [entries[path] for path in sorted(entries)]


class P15ManifestPayloadTests(unittest.TestCase):
    def test_overlay_payload_matches_p15_artifacts_exactly(self) -> None:
        expected = expected_entries()
        actual = effective_entries()
        if actual != expected:
            raise AssertionError(
                "P15_CLOSURE_MANIFEST_ENTRIES="
                + json.dumps(expected, ensure_ascii=False, separators=(",", ":"))
            )

    def test_paths_are_sorted_unique_and_exist(self) -> None:
        self.assertEqual(P15_PATHS, tuple(sorted(set(P15_PATHS))))
        self.assertTrue(all((ROOT / path).is_file() for path in P15_PATHS))

    def test_snapshot_controls_are_current_in_global_manifest(self) -> None:
        from tests.test_b1a_artifact_manifest import load_effective_manifest

        current = {
            row[0]: row for row in load_effective_manifest()["artifacts"]
        }
        for path in P15_SNAPSHOT_ENTRIES:
            data = (ROOT / path).read_bytes()
            self.assertEqual(
                current[path],
                [path, hashlib.sha256(data).hexdigest(), len(data)],
            )


if __name__ == "__main__":
    unittest.main()
