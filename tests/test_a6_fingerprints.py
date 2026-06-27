import csv
import unittest
from pathlib import Path

from quantum.ingestion.fingerprints import semantic_fingerprint, structural_fingerprint


class A6FingerprintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.valid = cls.root / "tests/contracts/fixtures/a6/wb-synthetic-valid.csv"
        cls.drift = cls.root / "tests/contracts/fixtures/a6/wb-synthetic-semantic-drift.csv"

    def test_structural_fingerprint_is_deterministic(self):
        self.assertEqual(
            structural_fingerprint(self.valid),
            structural_fingerprint(self.valid),
        )

    def test_same_headers_can_have_different_semantics(self):
        with self.valid.open("r", encoding="utf-8", newline="") as handle:
            valid = semantic_fingerprint(list(csv.DictReader(handle)))
        with self.drift.open("r", encoding="utf-8", newline="") as handle:
            drift = semantic_fingerprint(list(csv.DictReader(handle)))
        self.assertNotEqual(valid["sha256"], drift["sha256"])


if __name__ == "__main__":
    unittest.main()
