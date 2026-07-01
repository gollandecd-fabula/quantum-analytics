from __future__ import annotations
import unittest
from tests._artifact_manifest_runtime_v3 import (
    ARTIFACT_FIELDS, B1A_SCHEMAS, CONTROL_PATHS, MANIFEST_PATH, ROOT,
    apply_entries, expected_manifest, git_blob_sha, load_effective_manifest,
    tracked_paths,
)

class B1aArtifactManifestTests(unittest.TestCase):
    def test_manifest_matches_current_tracked_tree(self) -> None:
        current = load_effective_manifest()
        self.assertEqual(current, expected_manifest(current))

    def test_manifest_contains_all_b1a_schemas(self) -> None:
        current = load_effective_manifest()
        self.assertEqual(current["artifact_fields"], ARTIFACT_FIELDS)
        paths = {entry[0] for entry in current["artifacts"]}
        self.assertTrue(B1A_SCHEMAS.issubset(paths), B1A_SCHEMAS - paths)

if __name__ == "__main__":
    unittest.main()
