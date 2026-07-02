import hashlib
import json
import unittest
from pathlib import Path

from tests.test_b1b_manifest_probe_v3 import PATHS

ROOT = Path(__file__).resolve().parents[1]


class B1bManifestProbeDiagnosticsV3Tests(unittest.TestCase):
    def test_emit_ci_preserved_entries(self):
        for path in PATHS:
            data = (ROOT / path).read_bytes()
            entry = [path, hashlib.sha256(data).hexdigest(), len(data)]
            print("MANIFEST_DIFF=B1B_MANIFEST_ENTRY:" + json.dumps(entry, separators=(",", ":")))
        self.assertTrue(True)
