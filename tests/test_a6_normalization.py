import csv
import unittest
from pathlib import Path

from quantum.adapters.wildberries.synthetic import normalize_row, validate_row


class A6NormalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        with (root / "tests/contracts/fixtures/a6/wb-synthetic-valid.csv").open(
            "r", encoding="utf-8", newline=""
        ) as handle:
            cls.rows = list(csv.DictReader(handle))

    def normalize(self, row):
        return normalize_row(
            row,
            organization_id="org",
            marketplace_account_id="account",
            import_batch_id="batch",
            source_record_id=f"src-{row['row_id']}",
            source_file_sha256="a" * 64,
            schema_version="wb-synthetic-operations-v1",
            adapter_id="wildberries-synthetic",
            adapter_version="1.0",
            trace_id="trace",
        )

    def test_revision_links_to_superseded_event(self):
        result = self.normalize(self.rows[2])
        self.assertEqual(result.event.revision, 2)
        self.assertEqual(result.event.supersedes_event_id, "evt-sale-002-r1")

    def test_return_links_to_reversed_sale(self):
        result = self.normalize(self.rows[3])
        self.assertEqual(result.event.event_type, "RETURN_ACCEPTED")
        self.assertEqual(result.event.reversal_of_event_id, "evt-sale-001-r1")

    def test_semantic_validation_rejects_bad_quantity(self):
        broken = dict(self.rows[0])
        broken["quantity"] = "one"
        with self.assertRaises(ValueError):
            validate_row(broken)


if __name__ == "__main__":
    unittest.main()
