from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "docs/evidence/ARTIFACT_MANIFEST_OVERLAY.json"
CONTROL_PATHS = {
    "docs/evidence/ARTIFACT_MANIFEST.json",
    "docs/evidence/ARTIFACT_MANIFEST_OVERLAY.json",
}


class B3ManifestOverlayTests(unittest.TestCase):
    def test_overlay_structure_is_unique_sorted_and_control_safe(self) -> None:
        overlay = json.loads(OVERLAY.read_text(encoding="utf-8"))
        self.assertEqual(overlay["overlay_version"], 1)
        self.assertRegex(overlay["base_manifest_git_blob_sha"], r"^[a-f0-9]{40}$")
        self.assertEqual(set(overlay["control_paths_excluded_from_payload"]), CONTROL_PATHS)

        entries = overlay["entries"]
        paths = [entry[0] for entry in entries]
        self.assertEqual(paths, sorted(paths))
        self.assertEqual(len(paths), len(set(paths)))
        self.assertFalse(set(paths) & CONTROL_PATHS)
        for path, digest, size in entries:
            self.assertRegex(digest, r"^[a-f0-9]{64}$", path)
            self.assertIsInstance(size, int, path)
            self.assertGreaterEqual(size, 0, path)

        removed = overlay["remove_paths"]
        self.assertEqual(len(removed), len(set(removed)))
        self.assertFalse(set(removed) & set(paths))
        self.assertFalse(set(removed) & CONTROL_PATHS)

    def test_no_temporary_diagnostic_tests_are_tracked(self) -> None:
        temporary = sorted(
            path.relative_to(ROOT).as_posix()
            for path in (ROOT / "tests").glob("test_000_*.py")
        )
        self.assertEqual(temporary, [])
        overlay = json.loads(OVERLAY.read_text(encoding="utf-8"))
        overlay_paths = {entry[0] for entry in overlay["entries"]}
        self.assertFalse(any(path.startswith("tests/test_000_") for path in overlay_paths))


if __name__ == "__main__":
    unittest.main()
