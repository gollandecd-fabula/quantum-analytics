import hashlib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = (
    "docs/evidence/STAGE_B_B3_CONTRACT_EVIDENCE.yaml",
    "docs/evidence/STAGE_B_EXECUTION_STATE.yaml",
    "docs/governance/CURRENT_STATE.md",
)


class B3MetadataHashDiagnostic(unittest.TestCase):
    def test_emit_hashes(self):
        for path in TARGETS:
            data = (ROOT / path).read_bytes()
            print(
                f"B3_METADATA_HASH path={path} sha256={hashlib.sha256(data).hexdigest()} size={len(data)}",
                flush=True,
            )
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
