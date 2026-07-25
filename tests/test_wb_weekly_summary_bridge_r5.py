from __future__ import annotations

from hashlib import sha256
import unittest

from quantum.adapters.wildberries.dispatcher import bridge_reviewed_wb_source
from quantum.adapters.wildberries.weekly_summary import (
    EXPECTED_WEEKLY_SUMMARY_HEADERS,
    EXPECTED_WEEKLY_SUMMARY_HEADER_SHA256,
    WEEKLY_SUMMARY_SOURCE_TYPE,
)
from quantum.ingestion.xlsx_inspection import normalized_header_sha256
from tests.p16_fixtures import build_xlsx, policy


ROWS = (
    (
        "1000001",
        "ООО Тест",
        "2026-07-01",
        "2026-07-07",
        "2026-07-08",
        "Основной",
        "1000.00",
        "50.00",
        "700.00",
        "5.00",
        "100.00",
        "20.00",
        "10.00",
        "-5.00",
        "3.00",
        "-2.00",
        "4.00",
        "1.00",
        "0.00",
        "655.00",
        "RUB",
    ),
    (
        "1000002",
        "ООО Тест",
        "2026-07-08",
        "2026-07-14",
        "2026-07-15",
        "Основной",
        "500.00",
        "25.00",
        "350.00",
        "4.00",
        "40.00",
        "5.00",
        "0.00",
        "2.00",
        "0.00",
        "1.00",
        "2.00",
        "0.00",
        "0.00",
        "304.00",
        "RUB",
    ),
)


def _schema(headers=EXPECTED_WEEKLY_SUMMARY_HEADERS, rows=ROWS):
    return {
        "sheet_name": "Sheet1",
        "header_row_index": 1,
        "headers": list(headers),
        "header_sha256": normalized_header_sha256(headers),
        "column_count": len(headers),
        "data_row_count": len(rows),
    }


class WbWeeklySummaryBridgeR5Tests(unittest.TestCase):
    def test_exact_header_hash_is_stable(self):
        self.assertEqual(
            normalized_header_sha256(EXPECTED_WEEKLY_SUMMARY_HEADERS),
            EXPECTED_WEEKLY_SUMMARY_HEADER_SHA256,
        )

    def test_weekly_summary_routes_and_exposes_direct_metrics(self):
        workbook = build_xlsx(
            headers=EXPECTED_WEEKLY_SUMMARY_HEADERS,
            rows=ROWS,
        )
        result = bridge_reviewed_wb_source(
            payload=workbook,
            schema_discovery=_schema(),
            limits=policy(headers=EXPECTED_WEEKLY_SUMMARY_HEADERS).limits,
            source_id="dataset:test-weekly",
            source_context={"currency": "RUB"},
        )
        self.assertEqual(result["status"], "SOURCE_BRIDGE_COMPLETE")
        self.assertEqual(result["source_type"], WEEKLY_SUMMARY_SOURCE_TYPE)
        self.assertEqual(result["source_sha256"], sha256(workbook).hexdigest())
        self.assertEqual(result["row_count"], 2)
        self.assertEqual(result["observed_metrics"]["gross_sales_amount"]["value"], "1500.00")
        self.assertEqual(result["observed_metrics"]["payout_amount"]["value"], "959.00")
        self.assertEqual(result["observed_metrics"]["total_logistics_amount"]["value"], "140.00")
        self.assertEqual(result["observed_metrics"]["storage_amount"]["value"], "25.00")
        self.assertEqual(result["observed_metrics"]["fines_amount"]["value"], "3.00")
        self.assertEqual(result["finance_request_state"], "BLOCKED")
        self.assertIn("PRODUCT_COST_PROFILE_REQUIRED", result["finance_request_reason_codes"])
        self.assertIn("SOLD_UNITS_SOURCE_REQUIRED", result["finance_request_reason_codes"])
        self.assertFalse(result["raw_rows_in_report"])
        self.assertNotIn("rows", result)

    def test_invalid_money_blocks_weekly_bridge_without_crash(self):
        broken = list(ROWS[0])
        broken[6] = "not-money"
        rows = (tuple(broken),)
        workbook = build_xlsx(
            headers=EXPECTED_WEEKLY_SUMMARY_HEADERS,
            rows=rows,
        )
        result = bridge_reviewed_wb_source(
            payload=workbook,
            schema_discovery=_schema(rows=rows),
            limits=policy(headers=EXPECTED_WEEKLY_SUMMARY_HEADERS).limits,
            source_id="dataset:test-broken",
        )
        self.assertEqual(result["status"], "SOURCE_BRIDGE_BLOCKED")
        self.assertEqual(result["finance_request_state"], "BLOCKED")
        self.assertIn(
            "WB_WEEKLY_AMOUNT_INVALID:gross_sales_amount",
            result["finance_request_reason_codes"],
        )
        self.assertFalse(result["raw_rows_in_report"])

    def test_unknown_table_receives_generic_partial_bridge(self):
        headers = ("Новая колонка", "Другое поле", "Значение")
        rows = (("A", "B", "1"),)
        workbook = build_xlsx(headers=headers, rows=rows)
        result = bridge_reviewed_wb_source(
            payload=workbook,
            schema_discovery=_schema(headers=headers, rows=rows),
            limits=policy(headers=headers).limits,
            source_id="dataset:test-generic",
        )
        self.assertEqual(result["status"], "SOURCE_BRIDGE_PARTIAL")
        self.assertEqual(result["source_type"], "WB_GENERIC_TABULAR")
        self.assertEqual(result["finance_request_state"], "BLOCKED")
        self.assertEqual(result["observed_metrics"]["source_row_count"]["value"], "1")
        self.assertEqual(result["observed_metrics"]["source_column_count"]["value"], "3")
        self.assertIn("WB_SCHEMA_PROFILE_REQUIRED", result["finance_request_reason_codes"])
        self.assertFalse(result["raw_rows_in_report"])


if __name__ == "__main__":
    unittest.main()
