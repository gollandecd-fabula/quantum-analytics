from __future__ import annotations

import json
import sys
import unittest

from tests.integration_manifest_support import expected_manifest, load_effective_manifest


class LocalPilotManifestDumpTests(unittest.TestCase):
    def test_dump_changed_entries_for_internal_ci_remediation(self):
        current = load_effective_manifest()
        expected = expected_manifest(current)
        effective = {row[0]: row for row in current["artifacts"]}
        changed = [
            row
            for row in expected["artifacts"]
            if effective.get(row[0]) != row
        ]
        encoded = json.dumps(changed, separators=(",", ":"))
        for index in range(0, len(encoded), 1800):
            chunk = encoded[index : index + 1800]
            print(
                f"PILOT_MANIFEST_CHUNK_{index // 1800:02d}={chunk}",
                file=sys.stderr,
            )
        self.assertTrue(changed)


if __name__ == "__main__":
    unittest.main()
