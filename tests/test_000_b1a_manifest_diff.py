import hashlib
import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "docs/evidence/ARTIFACT_MANIFEST.json"
SELF = "tests/test_000_b1a_manifest_diff.py"


class B1aManifestDiffTests(unittest.TestCase):
    def test_emit_manifest_diff(self):
        data = json.loads((ROOT / MANIFEST).read_text(encoding="utf-8"))
        recorded = {e[0]: (e[1], e[2]) for e in data["artifacts"]}
        paths = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
        paths = sorted(p for p in paths if p and p not in {MANIFEST, SELF})
        expected = {}
        for path in paths:
            raw = (ROOT / path).read_bytes()
            expected[path] = (hashlib.sha256(raw).hexdigest(), len(raw))
        print(f"B1A_MANIFEST_COUNT recorded={len(recorded)} expected={len(expected)}", flush=True)
        for path in sorted(set(expected) - set(recorded)):
            print(f"B1A_MANIFEST_MISSING path={path} expected={expected[path]}", flush=True)
        for path in sorted(set(recorded) - set(expected)):
            print(f"B1A_MANIFEST_EXTRA path={path} recorded={recorded[path]}", flush=True)
        for path in sorted(set(recorded) & set(expected)):
            if recorded[path] != expected[path]:
                print(f"B1A_MANIFEST_MISMATCH path={path} recorded={recorded[path]} expected={expected[path]}", flush=True)
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
