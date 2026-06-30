from __future__ import annotations

import json
import unittest
from pathlib import Path

from quantum.reporting import EXPORT_SCHEMA_VERSION, REPORT_SCHEMA_VERSION


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"


def load_schema(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


class P14SchemaAlignmentTests(unittest.TestCase):
    def test_schema_versions_match_runtime_constants(self) -> None:
        report = load_schema("report-record.schema.json")
        export = load_schema("report-export-bundle.schema.json")
        self.assertEqual(
            report["properties"]["schema_version"]["const"],
            REPORT_SCHEMA_VERSION,
        )
        self.assertEqual(
            export["properties"]["schema_version"]["const"],
            EXPORT_SCHEMA_VERSION,
        )

    def test_report_schema_requires_integrity_and_evidence_hashes(self) -> None:
        report = load_schema("report-record.schema.json")
        required = set(report["required"])
        self.assertIn("record_hash", required)
        self.assertIn("metric_content_hash", required)
        self.assertIn("evidence_chain_content_hash", required)
        self.assertEqual(
            report["properties"]["record_hash"]["pattern"],
            "^[a-f0-9]{64}$",
        )

    def test_nested_report_contracts_are_closed(self) -> None:
        report = load_schema("report-record.schema.json")
        for field in ("evidence_chain_ref", "rounding", "freshness", "confidence"):
            with self.subTest(field=field):
                self.assertFalse(
                    report["properties"][field]["additionalProperties"]
                )

    def test_export_records_have_machine_readable_uniqueness_floor(self) -> None:
        export = load_schema("report-export-bundle.schema.json")
        records = export["properties"]["records"]
        self.assertTrue(records["uniqueItems"])
        self.assertEqual(records["minItems"], 1)
        self.assertEqual(records["maxItems"], 10_000)

    def test_expense_boundary_is_closed_and_duplicate_free(self) -> None:
        report = load_schema("report-record.schema.json")
        boundary = report["properties"]["expense_boundary"]
        self.assertTrue(boundary["uniqueItems"])
        allowed = set(boundary["items"]["enum"])
        self.assertEqual(
            allowed,
            {
                "MARKETPLACE_COMMISSION",
                "FORWARD_LOGISTICS",
                "REVERSE_LOGISTICS",
                "STORAGE",
                "ADVERTISING",
                "FINES_WITHHOLDINGS",
                "PRODUCT_COST",
                "OTHER_EXPENSE",
                "TAX",
            },
        )


if __name__ == "__main__":
    unittest.main()
