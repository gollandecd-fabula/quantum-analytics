import hashlib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = (
    "schemas/rule-resolution-result.schema.json",
    "tests/test_b1a_valid_trace.py",
)

class B1aTraceHashTests(unittest.TestCase):
    def test_emit_hashes(self):
        for path in TARGETS:
            data = (ROOT / path).read_bytes()
            print(f"B1A_TRACE_HASH path={path} sha256={hashlib.sha256(data).hexdigest()} size={len(data)}", flush=True)
        self.assertTrue(True)

if __name__ == "__main__":
    unittest.main()
