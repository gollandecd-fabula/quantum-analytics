from __future__ import annotations

import base64
import hashlib
import json
import lzma
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs/evidence/ARTIFACT_MANIFEST.json"
MANIFEST_REPO_PATH = "docs/evidence/ARTIFACT_MANIFEST.json"
B1A_SCHEMAS = {
    "schemas/calculation-profile.schema.json",
    "schemas/configuration-rule.schema.json",
    "schemas/metric-definition.schema.json",
    "schemas/rounding-policy.schema.json",
    "schemas/rule-resolution-result.schema.json",
    "schemas/safe-expression.schema.json",
}


def tracked_paths() -> list[str]:
    output = subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=ROOT
    ).decode("utf-8")
    return sorted(
        path for path in output.split("\0")
        if path and path != MANIFEST_REPO_PATH
    )


def expected_manifest(current: dict) -> dict:
    artifacts = []
    for path in tracked_paths():
        data = (ROOT / path).read_bytes()
        artifacts.append(
            {
                "path": path,
                "sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
            }
        )

    return {
        "project": current["project"],
        "generated_on": "2026-06-27",
        "package_version": "6",
        "source_constitution_file": current["source_constitution_file"],
        "source_constitution_sha256": current["source_constitution_sha256"],
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
    }


def emit_regenerated_manifest(manifest: dict) -> None:
    payload = json.dumps(
        manifest, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    encoded = base64.b64encode(
        lzma.compress(payload, preset=9 | lzma.PRESET_EXTREME)
    ).decode("ascii")
    print(f"MANIFEST_LZMA_B64={encoded}")


class B1aArtifactManifestTests(unittest.TestCase):
    def test_manifest_matches_current_tracked_tree(self) -> None:
        current = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        expected = expected_manifest(current)
        if current != expected:
            emit_regenerated_manifest(expected)
        self.assertEqual(current, expected)

    def test_manifest_contains_all_b1a_schemas(self) -> None:
        current = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        paths = {entry["path"] for entry in current["artifacts"]}
        self.assertTrue(B1A_SCHEMAS.issubset(paths), B1A_SCHEMAS - paths)


if __name__ == "__main__":
    unittest.main()
