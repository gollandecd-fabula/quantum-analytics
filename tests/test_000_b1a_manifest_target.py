import hashlib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = "docs/finance/RULE_RESOLUTION_CONTRACT.md"


class B1aManifestTargetTests(unittest.TestCase):
    def test_emit_target_hash(self):
        data = (ROOT / TARGET).read_bytes()
        print(
            f"B1A_MANIFEST_TARGET path={TARGET} "
            f"sha256={hashlib.sha256(data).hexdigest()} size={len(data)}",
            flush=True,
        )
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
