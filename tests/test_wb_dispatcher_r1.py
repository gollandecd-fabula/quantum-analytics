import unittest

from quantum.adapters.wildberries.dispatcher import bridge_reviewed_wb_source
from quantum.ingestion._xlsx_contracts import normalized_header_sha256
from tests.test_wb_detailed_xlsx_r1 import (
    HEADERS,
    SALE,
    discovery,
    limits,
    workbook,
)


class WbDispatcherTests(unittest.TestCase):
    def test_detailed_financial_schema_is_routed(self):
        result = bridge_reviewed_wb_source(
            payload=workbook(),
            schema_discovery=discovery(),
            limits=limits(),
            source_id="SRC-07",
        )
        self.assertEqual(result["status"], "SOURCE_BRIDGE_COMPLETE")
        self.assertEqual(result["source_type"], "WB_DETAILED_FINANCIAL")
        self.assertEqual(result["event_count"], 1)
        self.assertEqual(
            result["dispatch_schema_version"],
            "quantum-wb-source-dispatch-v2",
        )
        self.assertFalse(result["raw_rows_in_report"])

    def test_unknown_schema_remains_admitted_with_partial_metadata(self):
        headers = ["Unknown A", "Unknown B", "Unknown C"]
        result = bridge_reviewed_wb_source(
            payload=workbook(headers=headers, rows=(("1", "2", "3"),)),
            schema_discovery={
                "sheet_name": "Sheet1",
                "header_row_index": 1,
                "headers": headers,
                "header_sha256": normalized_header_sha256(tuple(headers)),
                "column_count": 3,
                "data_row_count": 1,
            },
            limits=limits(),
            source_id="SRC-UNKNOWN",
        )
        self.assertEqual(result["status"], "SOURCE_BRIDGE_PARTIAL")
        self.assertEqual(result["source_type"], "WB_GENERIC_TABULAR")
        self.assertEqual(result["finance_request_state"], "BLOCKED")
        self.assertEqual(
            result["finance_request_reason_codes"],
            ["WB_SCHEMA_PROFILE_REQUIRED", "CALCULATION_PROFILE_REQUIRED"],
        )
        self.assertEqual(
            result["observed_metrics"]["source_row_count"]["value"],
            "1",
        )
        self.assertEqual(
            result["observed_metrics"]["source_column_count"]["value"],
            "3",
        )
        self.assertFalse(result["raw_rows_in_report"])

    def test_known_schema_mapping_error_is_reported_not_raised(self):
        malformed = list(SALE)
        malformed[9] = "Неизвестная операция"
        result = bridge_reviewed_wb_source(
            payload=workbook(rows=(malformed,)),
            schema_discovery=discovery(),
            limits=limits(),
            source_id="SRC-07",
        )
        self.assertEqual(result["status"], "SOURCE_BRIDGE_BLOCKED")
        self.assertEqual(result["finance_request_state"], "BLOCKED")
        self.assertTrue(
            result["finance_request_reason_codes"][0].startswith(
                "WB_DETAILED_OPERATION_UNSUPPORTED:"
            )
        )


if __name__ == "__main__":
    unittest.main()
