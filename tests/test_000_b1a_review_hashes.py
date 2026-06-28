import hashlib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = (
    "docs/finance/RULE_RESOLUTION_CONTRACT.md",
    "tests/test_b1a_financial_contracts.py",
    "tests/contracts/fixtures/b1a-rule-resolution-vectors.json",
    "schemas/safe-expression.schema.json",
    "tests/test_b1a_contract_edge_cases.py",
)


class B1aReviewHashTests(unittest.TestCase):
    def test_emit_review_hashes(self):
        for path in TARGETS:
            data = (ROOT / path).read_bytes()
            print(
                f"B1A_REVIEW_HASH path={path} "
                f"sha256={hashlib.sha256(data).hexdigest()} size={len(data)}",
                flush=True,
            )
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
