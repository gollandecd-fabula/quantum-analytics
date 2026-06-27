import unittest
from pathlib import Path

from quantum.ingestion.schema_registry import detect_csv_schema


class A6SchemaDetectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]

    def test_known_schema_matches(self):
        result = detect_csv_schema(
            self.root / "tests/contracts/fixtures/a6/wb-synthetic-valid.csv"
        )
        self.assertEqual(result.status, "MATCHED")
        self.assertEqual(result.schema_id, "wb-synthetic-operations-v1")

    def test_unknown_schema_is_diagnostic(self):
        result = detect_csv_schema(
            self.root / "tests/contracts/fixtures/a6/wb-synthetic-unknown-schema.csv"
        )
        self.assertEqual(result.status, "UNKNOWN")
        self.assertIn("missing_columns=gross_amount", result.diagnostics)
        self.assertIn("unexpected_columns=gross_sales_amount", result.diagnostics)


if __name__ == "__main__":
    unittest.main()
