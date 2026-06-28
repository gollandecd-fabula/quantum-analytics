import hashlib
import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = "docs/evidence/ARTIFACT_MANIFEST.json"
SELF_PATH = "tests/test_000_b1a_manifest_diff.py"


class B1aManifestDiffDiagnostic(unittest.TestCase):
    def test_emit_manifest_diff(self):
        manifest = json.loads((ROOT / MANIFEST_PATH).read_text(encoding="utf-8"))
        recorded = {row[0]: (row[1], row[2]) for row in manifest["artifacts"]}
        tracked = subprocess.check_output(
            ["git", "ls-files", "-z"], cwd=ROOT
        ).decode("utf-8").split("\0")
        tracked = [path for path in tracked if path and path not in {MANIFEST_PATH, SELF_PATH}]

        expected = {}
        for path in tracked:
            data = (ROOT / path).read_bytes()
            expected[path] = (hashlib.sha256(data).hexdigest(), len(data))

        missing = sorted(set(expected) - set(recorded))
        extra = sorted(set(recorded) - set(expected))
        mismatched = sorted(
            path for path in set(expected) & set(recorded)
            if expected[path] != recorded[path]
        )

        print(f"B1A_MANIFEST_COUNTS recorded={len(recorded)} expected={len(expected)}", flush=True)
        for path in missing:
            sha256, size = expected[path]
            print(f"B1A_MANIFEST_MISSING path={path} sha256={sha256} size={size}", flush=True)
        for path in extra:
            sha256, size = recorded[path]
            print(f"B1A_MANIFEST_EXTRA path={path} sha256={sha256} size={size}", flush=True)
        for path in mismatched:
            old_sha, old_size = recorded[path]
            new_sha, new_size = expected[path]
            print(
                f"B1A_MANIFEST_MISMATCH path={path} "
                f"recorded_sha256={old_sha} recorded_size={old_size} "
                f"expected_sha256={new_sha} expected_size={new_size}",
                flush=True,
            )

        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
