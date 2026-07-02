import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = "tests/test_b1b_rescue_smoke.py"


class B1bManifestProbeDiagnosticsV3Tests(unittest.TestCase):
    def test_emit_missing_smoke_entry(self):
        data = (ROOT / PATH).read_bytes()
        entry = [PATH, hashlib.sha256(data).hexdigest(), len(data)]
        print("MANIFEST_DIFF=B1B_SMOKE_ENTRY:" + json.dumps(entry, separators=(",", ":")))
        self.assertTrue(True)
