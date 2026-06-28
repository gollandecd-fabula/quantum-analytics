import hashlib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = (
    "docs/finance/SAFE_EXPRESSION_CONTRACT.md",
    "tests/test_b1a_safe_expression_semantics.py",
    "tests/test_b1a_contract_alignment.py",
)


class B1aSemanticHashTests(unittest.TestCase):
    def test_emit_semantic_hashes(self):
        for path in TARGETS:
            data = (ROOT / path).read_bytes()
            print(
                f"B1A_SEMANTIC_HASH path={path} "
                f"sha256={hashlib.sha256(data).hexdigest()} size={len(data)}",
                flush=True,
            )
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
