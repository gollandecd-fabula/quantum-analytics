from __future__ import annotations

import json
import unittest

from tests.test_b1a_artifact_manifest import expected_manifest, load_effective_manifest


class ManifestDiagnosticTests(unittest.TestCase):
    def test_manifest_diff_is_empty(self) -> None:
        current = load_effective_manifest()
        expected = expected_manifest(current)
        current_rows = {row[0]: row for row in current["artifacts"]}
        expected_rows = {row[0]: row for row in expected["artifacts"]}
        missing_paths = sorted(expected_rows.keys() - current_rows.keys())
        shared = sorted(current_rows.keys() & expected_rows.keys())
        diagnostic = {
            "missing": missing_paths,
            "missing_entries": [expected_rows[path] for path in missing_paths],
            "extra": sorted(current_rows.keys() - expected_rows.keys()),
            "mismatched": [
                {
                    "path": path,
                    "manifest": current_rows[path],
                    "tracked": expected_rows[path],
                }
                for path in shared
                if current_rows[path] != expected_rows[path]
            ],
            "top_level": {
                key: {"manifest": current.get(key), "tracked": expected.get(key)}
                for key in expected
                if key != "artifacts" and current.get(key) != expected.get(key)
            },
        }
        if diagnostic != {
            "missing": [],
            "missing_entries": [],
            "extra": [],
            "mismatched": [],
            "top_level": {},
        }:
            print("MANIFEST_DIFF=" + json.dumps(diagnostic, sort_keys=True), flush=True)
        self.assertEqual(current, expected)


if __name__ == "__main__":
    unittest.main()
