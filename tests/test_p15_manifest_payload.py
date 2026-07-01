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
P15_SNAPSHOT_ENTRIES = {
    "docs/evidence/STAGE_B_EXECUTION_STATE.yaml": [
        "docs/evidence/STAGE_B_EXECUTION_STATE.yaml",
        base64.b64decode("sqhb9rqFbcuJtZsR6VKyeg5dWwbKf9k73fMROl2aMw0=", validate=True).hex(),
        3460,
    ],
    "docs/evidence/STAGE_P1_5_EXECUTION_STATE.yaml": [
        "docs/evidence/STAGE_P1_5_EXECUTION_STATE.yaml",
        base64.b64decode("Koler6LelyNKZkQrDtbHlxGYSMJzS6OFQ9/iE3dWtoI=", validate=True).hex(),
        3480,
    ],
    "docs/governance/CURRENT_STATE.md": [
        "docs/governance/CURRENT_STATE.md",
        base64.b64decode("E1IGDaqKK9gngVvvdgRnhDAj9tkTLCB3V5LJ3ypeXDM=", validate=True).hex(),
        2356,
    ],
    "docs/ux/UX_ONBOARDING_EXCEPTION_INBOX_CONTRACT.md": [
        "docs/ux/UX_ONBOARDING_EXCEPTION_INBOX_CONTRACT.md",
        base64.b64decode("sqmJfB2mKPWzE5vsrLAc46J5NhZ2R5eQs8TJYhQqdi4=", validate=True).hex(),
        8008,
    ],
    "schemas/exception-inbox.schema.json": [
        "schemas/exception-inbox.schema.json",
        base64.b64decode("9IUEB0MTJZW8A3b7nV6hkjQYe7kWZHNLlMfQvHGNDb0=", validate=True).hex(),
        3796,
    ],
    "schemas/ux-configuration-form.schema.json": [
        "schemas/ux-configuration-form.schema.json",
        base64.b64decode("tx/B+WrVULbpyW7HuxFKCuPVf0c/UuM0G4elmBUxRbw=", validate=True).hex(),
        7177,
    ],
    "schemas/ux-view.schema.json": [
        "schemas/ux-view.schema.json",
        base64.b64decode("AGq8oajOwVuMCHgdRxURw9aF6zCXNE/5s3kCiJVvalY=", validate=True).hex(),
        5940,
    ],
    "src/quantum/ux/__init__.py": [
        "src/quantum/ux/__init__.py",
        base64.b64decode("DX9WxwcrK0Tho2J4uHtbM6WmqrPTtL6m7lhlWCA/kZ0=", validate=True).hex(),
        5474,
    ],
    "src/quantum/ux/runtime.py": [
        "src/quantum/ux/runtime.py",
        base64.b64decode("RoFGdwTuFTsqOilpnAS0wJD+KV+TV2w8d08GDoAmnWI=", validate=True).hex(),
        31812,
    ],
    "src/quantum/ux/validation.py": [
        "src/quantum/ux/validation.py",
        base64.b64decode("2831mZYrjmfvJbeS9h9i+bS+y6KZzcRi2xRsCMDU3+Y=", validate=True).hex(),
        8298,
    ],
    "tests/test_a0_p15_manifest_payload.py": [
        "tests/test_a0_p15_manifest_payload.py",
        base64.b64decode("lFwKy+lzOOiY0IayjbbCDcHSKMDjl2LiambARs1Ukg0=", validate=True).hex(),
        670,
    ],
    "tests/test_b1a_artifact_manifest.py": [
        "tests/test_b1a_artifact_manifest.py",
        base64.b64decode("SW+hmnweKSFft7iL5mdDk4RqHfzFEM3gimWKlCz7Fig=", validate=True).hex(),
        9630,
    ],
    "tests/test_p15_contract_alignment.py": [
        "tests/test_p15_contract_alignment.py",
        base64.b64decode("D6ZtZQcmZ5XDijZoHtB0wp/EGQIpErVmn9nj9kNus9c=", validate=True).hex(),
        4194,
    ],
    "tests/test_p15_manifest_payload.py": [
        "tests/test_p15_manifest_payload.py",
        base64.b64decode("8Ue4JwxQhlMeurSnbijS0WOaufQs7Ehy4wrJArHPE60=", validate=True).hex(),
        2773,
    ],
    "tests/test_p15_review_remediation.py": [
        "tests/test_p15_review_remediation.py",
        base64.b64decode("dF4fRjDvgRV37A4I4KPiB0u8vplhEcQBvm1e/hUhv9Y=", validate=True).hex(),
        5505,
    ],
    "tests/test_p15_schema_alignment.py": [
        "tests/test_p15_schema_alignment.py",
        base64.b64decode("0fYtGz/sBb25QDvOjeE+wj+WjRPjwDK71dxHP8bA6+g=", validate=True).hex(),
        6835,
    ],
    "tests/test_p15_ux_adversarial.py": [
        "tests/test_p15_ux_adversarial.py",
        base64.b64decode("VQO49Re/XcbUaJJx74pf2r0UyLWzE/KzMTC8O2zXUws=", validate=True).hex(),
        9373,
    ],
    "tests/test_p15_ux_runtime.py": [
        "tests/test_p15_ux_runtime.py",
        base64.b64decode("hyQV+GP/IhvTyEpqeMD3fXOwwWes02YrefA880eoMkQ=", validate=True).hex(),
        14662,
    ],
}
P15_PATHS = tuple(sorted(P15_SNAPSHOT_ENTRIES))


def git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def expected_entries() -> list[list[object]]:
    return [P15_SNAPSHOT_ENTRIES[path] for path in P15_PATHS]


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
    def test_overlay_payload_matches_immutable_p15_snapshot(self) -> None:
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

    def test_current_p15_paths_are_current_in_global_manifest(self) -> None:
        from tests.test_b1a_artifact_manifest import load_effective_manifest

        current = {
            row[0]: row for row in load_effective_manifest()["artifacts"]
        }
        for path in P15_PATHS:
            data = (ROOT / path).read_bytes()
            self.assertEqual(
                current[path],
                [path, hashlib.sha256(data).hexdigest(), len(data)],
            )


if __name__ == "__main__":
    unittest.main()
