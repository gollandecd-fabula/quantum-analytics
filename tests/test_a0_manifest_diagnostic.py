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
        extra_paths = sorted(current_rows.keys() - expected_rows.keys())
        shared = sorted(current_rows.keys() & expected_rows.keys())
        mismatched = [
            {
                "path": path,
                "manifest": current_rows[path],
                "tracked": expected_rows[path],
            }
            for path in shared
            if current_rows[path] != expected_rows[path]
        ]
        top_level = {
            key: {"manifest": current.get(key), "tracked": expected.get(key)}
            for key in expected
            if key != "artifacts" and current.get(key) != expected.get(key)
        }
        for path in missing_paths:
            print(
                "MANIFEST_MISSING_ENTRY="
                + json.dumps(expected_rows[path], separators=(",", ":")),
                flush=True,
            )
        for item in mismatched:
            print(
                "MANIFEST_MISMATCH_TRACKED="
                + json.dumps(item["tracked"], separators=(",", ":")),
                flush=True,
            )
        for path in extra_paths:
            print("MANIFEST_EXTRA_PATH=" + path, flush=True)
        if top_level:
            print(
                "MANIFEST_TOP_LEVEL="
                + json.dumps(top_level, sort_keys=True, separators=(",", ":")),
                flush=True,
            )
        self.assertEqual(current, expected)


if __name__ == "__main__":
    unittest.main()
