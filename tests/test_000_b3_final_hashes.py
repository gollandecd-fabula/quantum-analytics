import hashlib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = (
    "docs/evidence/STAGE_B_B3_CONTRACT_EVIDENCE.yaml",
    "tests/test_b3_manifest_overlay.py",
)


class B3FinalHashDiagnostic(unittest.TestCase):
    def test_emit_hashes(self):
        for path in TARGETS:
            data = (ROOT / path).read_bytes()
            print(
                f"B3_FINAL_HASH path={path} sha256={hashlib.sha256(data).hexdigest()} size={len(data)}",
                flush=True,
            )
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
