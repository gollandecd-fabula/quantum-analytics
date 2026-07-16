from __future__ import annotations

import unittest

from quantum.adapters.wildberries.dispatcher import bridge_reviewed_wb_source
from quantum.adapters.wildberries.source_bridge import _EXPECTED_SUPPLIER_GOODS_HEADERS
from quantum.ingestion._xlsx_contracts import normalized_header_sha256
from tests.p16_fixtures import build_xlsx
from tests.test_wb_detailed_xlsx_r1 import limits


class WbSupplierGoodsResultSchemaR5Tests(unittest.TestCase):
    def test_supplier_goods_exposes_canonical_reason_codes_list(self):
        headers = tuple(_EXPECTED_SUPPLIER_GOODS_HEADERS)
        payload = build_xlsx(
            headers=headers,
            rows=(
                (
                    "LarannA",
                    "Футболка",
                    "Лето",
                    "База",
                    "Футболка LarannA",
                    "IZ001",
                    "123456789",
                    "4600000000000",
                    "48",
                    "Договор",
                    "Коледино",
                    "1",
                    "100.00",
                    "1",
                    "90.00",
                    "5",
                ),
            ),
        )
        result = bridge_reviewed_wb_source(
            payload=payload,
            schema_discovery={
                "sheet_name": "Sheet1",
                "header_row_index": 1,
                "headers": list(headers),
                "header_sha256": normalized_header_sha256(headers),
                "column_count": len(headers),
                "data_row_count": 1,
            },
            limits=limits(),
            source_id="SRC-SUPPLIER-GOODS",
        )

        self.assertEqual(result["status"], "SOURCE_BRIDGE_COMPLETE")
        self.assertEqual(result["source_type"], "WB_SUPPLIER_GOODS")
        self.assertEqual(result["finance_request_state"], "BLOCKED")
        self.assertEqual(
            result["finance_request_reason_codes"],
            ["EVENT_LEVEL_FINANCIAL_SOURCE_REQUIRED_FOR_KERNEL"],
        )
        self.assertFalse(result["raw_rows_in_report"])


if __name__ == "__main__":
    unittest.main()
