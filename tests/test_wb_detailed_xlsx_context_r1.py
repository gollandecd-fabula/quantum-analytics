import unittest

from quantum.adapters.wildberries.detailed_xlsx import (
    WbDetailedXlsxError,
    bridge_detailed_financial_xlsx,
)
from tests.test_wb_detailed_xlsx_r1 import (
    HEADERS,
    SALE,
    discovery,
    limits,
    workbook,
)


class WbDetailedXlsxContextTests(unittest.TestCase):
    def test_reviewed_context_supplies_missing_report_metadata(self):
        business_headers = HEADERS[5:]
        business_row = SALE[5:]
        result = bridge_detailed_financial_xlsx(
            payload=workbook(headers=business_headers, rows=(business_row,)),
            schema_discovery=discovery(business_headers),
            limits=limits(),
            source_id="SRC-07",
            source_context={
                "report_id": "706623362",
                "date_from": "2026-04-27",
                "date_to": "2026-05-03",
                "currency": "RUB",
            },
        )
        self.assertEqual(result["event_count"], 1)
        self.assertEqual(result["report_ids"], ["706623362"])
        self.assertEqual(
            result["report_periods"]["706623362"],
            {"date_from": "2026-04-27", "date_to": "2026-05-03"},
        )
        self.assertEqual(
            result["observed_metrics"]["gross_sales_amount"]["value"],
            "1764.00",
        )

    def test_context_does_not_override_present_source_values(self):
        result = bridge_detailed_financial_xlsx(
            payload=workbook(),
            schema_discovery=discovery(),
            limits=limits(),
            source_id="SRC-07",
            source_context={
                "report_id": "999999999",
                "date_from": "2026-01-01",
                "date_to": "2026-01-02",
                "currency": "RUB",
            },
        )
        self.assertEqual(result["report_ids"], ["706623362"])

    def test_unknown_context_field_is_blocked(self):
        with self.assertRaises(WbDetailedXlsxError) as error:
            bridge_detailed_financial_xlsx(
                payload=workbook(),
                schema_discovery=discovery(),
                limits=limits(),
                source_id="SRC-07",
                source_context={"invented": "value"},
            )
        self.assertEqual(
            error.exception.code,
            "WB_DETAILED_XLSX_CONTEXT_INVALID",
        )


if __name__ == "__main__":
    unittest.main()
