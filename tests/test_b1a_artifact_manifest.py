import unittest

from tests.integration_manifest_support_m6 import (
    ARTIFACT_FIELDS,
    B1A_SCHEMAS,
    CONTROL_PATHS,
    expected_manifest,
    load_effective_manifest,
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

    def test_control_paths_have_no_misspelled_manifest_names(self) -> None:
        self.assertFalse(
            any("MANIEST" in path for path in CONTROL_PATHS),
            sorted(path for path in CONTROL_PATHS if "MANIEST" in path),
        )


if __name__ == "__main__":
    unittest.main()
