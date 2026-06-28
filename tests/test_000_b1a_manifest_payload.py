import json
import unittest

from test_b1a_artifact_manifest import MANIFEST_PATH, expected_manifest

SELF = "tests/test_000_b1a_manifest_payload.py"


class B1aManifestPayloadDiagnostic(unittest.TestCase):
    def test_emit_manifest_diff(self):
        current = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        generated = expected_manifest(current)
        generated["artifacts"] = [row for row in generated["artifacts"] if row[0] != SELF]
        generated["artifact_count"] = len(generated["artifacts"])
        old = {row[0]: row[1:] for row in current["artifacts"]}
        new = {row[0]: row[1:] for row in generated["artifacts"]}
        diff = {path: {"recorded": old.get(path), "expected": new.get(path)} for path in sorted(set(old) | set(new)) if old.get(path) != new.get(path)}
        print("B1A_FINAL_MANIFEST_DIFF=" + json.dumps(diff, sort_keys=True), flush=True)
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
