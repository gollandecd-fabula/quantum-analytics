from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OVERLAY_PATH = ROOT / "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_P15.json"
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


def expected_entries() -> list[list[object]]:
    entries: list[list[object]] = []
    for path in P15_PATHS:
        data = (ROOT / path).read_bytes()
        entries.append([path, hashlib.sha256(data).hexdigest(), len(data)])
    return entries


class P15ManifestPayloadTests(unittest.TestCase):
    def test_overlay_payload_matches_p15_artifacts_exactly(self) -> None:
        overlay = json.loads(OVERLAY_PATH.read_text(encoding="utf-8"))
        expected = expected_entries()
        if overlay["entries"] != expected:
            raise AssertionError(
                "P15_MANIFEST_ENTRIES="
                + json.dumps(expected, ensure_ascii=False, separators=(",", ":"))
            )

    def test_paths_are_sorted_unique_and_exist(self) -> None:
        self.assertEqual(P15_PATHS, tuple(sorted(set(P15_PATHS))))
        self.assertTrue(all((ROOT / path).is_file() for path in P15_PATHS))


if __name__ == "__main__":
    unittest.main()
