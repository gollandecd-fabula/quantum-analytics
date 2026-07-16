import hashlib
import io
import unittest
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from quantum.adapters.wildberries.detailed_xlsx import (
    WbDetailedXlsxError,
    bridge_detailed_financial_xlsx,
)
from quantum.ingestion import XlsxInspectionLimits
from quantum.ingestion._xlsx_contracts import normalized_header_sha256


HEADERS = [
    "reportId",
    "rrdId",
    "dateFrom",
    "dateTo",
    "currency",
    "vendorCode",
    "techSize",
    "sku",
    "docTypeName",
    "sellerOperName",
    "quantity",
    "retailAmount",
    "ppvzSalesCommission",
    "forPay",
    "ppvzReward",
    "acquiringFee",
    "deliveryAmount",
    "returnAmount",
    "deliveryService",
    "paidStorage",
    "penalty",
    "deduction",
    "paidAcceptance",
    "rebillLogisticCost",
    "additionalPayment",
    "orderDt",
    "saleDt",
    "srid",
]

SALE = [
    "706623362",
    "1",
    "2026-04-27",
    "2026-05-03",
    "RUB",
    "IZ-507",
    "2XL",
    "2040259223865",
    "Продажа",
    "Продажа",
    "1",
    "1764",
    "327",
    "1200",
    "70",
    "80",
    "0",
    "0",
    "0",
    "0",
    "0",
    "0",
    "0",
    "0",
    "0",
    "2026-04-24T00:00:00Z",
    "2026-04-27T00:00:00Z",
    "shared-srid",
]


def _column(index):
    value = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        value = chr(65 + remainder) + value
    return value


def _cell(column, row, value):
    reference = f"{_column(column)}{row}"
    return (
        f'<c r="{reference}" t="inlineStr"><is><t>'
        f"{escape(str(value))}"
        "</t></is></c>"
    )


def _row(index, values):
    return (
        f'<row r="{index}">'
        + "".join(
            _cell(column, index, value)
            for column, value in enumerate(values, start=1)
        )
        + "</row>"
    )


def workbook(headers=HEADERS, rows=(SALE,)):
    worksheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData>"
        + _row(1, headers)
        + "".join(_row(index, values) for index, values in enumerate(rows, 2))
        + "</sheetData></worksheet>"
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )
    relationships = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )
    root_relationships = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    stream = io.BytesIO()
    with ZipFile(stream, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_relationships)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", relationships)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)
    return stream.getvalue()


def wrapped_workbook(payload):
    stream = io.BytesIO()
    with ZipFile(stream, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("report.xlsx", payload)
    return stream.getvalue()


def limits():
    return XlsxInspectionLimits(
        max_file_bytes=10_000_000,
        max_archive_entries=100,
        max_total_uncompressed_bytes=20_000_000,
        max_entry_uncompressed_bytes=10_000_000,
        max_compression_ratio=100,
        max_xml_bytes=10_000_000,
        max_rows=100_000,
        max_columns=100,
    )


def discovery(headers=HEADERS, row_count=1):
    return {
        "sheet_name": "Sheet1",
        "header_row_index": 1,
        "headers": list(headers),
        "header_sha256": normalized_header_sha256(tuple(headers)),
        "column_count": len(headers),
        "data_row_count": row_count,
    }


class WbDetailedXlsxTests(unittest.TestCase):
    def test_direct_xlsx_is_bound_and_normalized(self):
        payload = workbook()
        result = bridge_detailed_financial_xlsx(
            payload=payload,
            schema_discovery=discovery(),
            limits=limits(),
            source_id="SRC-07",
        )
        self.assertEqual(result["event_count"], 1)
        self.assertEqual(
            result["observed_metrics"]["gross_sales_amount"]["value"],
            "1764.00",
        )
        self.assertEqual(result["xlsx_binding"]["data_row_count"], 1)
        self.assertEqual(result["xlsx_binding"]["column_count"], len(HEADERS))
        self.assertFalse(result["raw_rows_in_report"])
        self.assertNotIn("rows", result)

    def test_outer_zip_wrapper_is_supported(self):
        payload = wrapped_workbook(workbook())
        result = bridge_detailed_financial_xlsx(
            payload=payload,
            schema_discovery=discovery(),
            limits=limits(),
            source_id="SRC-07",
        )
        self.assertEqual(result["source_sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(result["event_count"], 1)

    def test_discovery_hash_tampering_is_blocked(self):
        candidate = discovery()
        candidate["header_sha256"] = "0" * 64
        with self.assertRaises(WbDetailedXlsxError) as error:
            bridge_detailed_financial_xlsx(
                payload=workbook(),
                schema_discovery=candidate,
                limits=limits(),
                source_id="SRC-07",
            )
        self.assertEqual(
            error.exception.code,
            "WB_DETAILED_XLSX_DISCOVERY_HASH_MISMATCH",
        )

    def test_workbook_header_change_is_blocked(self):
        changed = list(HEADERS)
        changed[0] = "changedReportId"
        with self.assertRaises(WbDetailedXlsxError) as error:
            bridge_detailed_financial_xlsx(
                payload=workbook(headers=changed),
                schema_discovery=discovery(),
                limits=limits(),
                source_id="SRC-07",
            )
        self.assertEqual(
            error.exception.code,
            "WB_DETAILED_XLSX_HEADER_CHANGED",
        )

    def test_row_count_change_is_blocked(self):
        with self.assertRaises(WbDetailedXlsxError) as error:
            bridge_detailed_financial_xlsx(
                payload=workbook(),
                schema_discovery=discovery(row_count=2),
                limits=limits(),
                source_id="SRC-07",
            )
        self.assertEqual(
            error.exception.code,
            "WB_DETAILED_XLSX_ROW_COUNT_MISMATCH",
        )

    def test_duplicate_discovery_headers_are_blocked(self):
        duplicate = list(HEADERS)
        duplicate[-1] = duplicate[0]
        with self.assertRaises(WbDetailedXlsxError) as error:
            bridge_detailed_financial_xlsx(
                payload=workbook(headers=duplicate),
                schema_discovery=discovery(duplicate),
                limits=limits(),
                source_id="SRC-07",
            )
        self.assertEqual(
            error.exception.code,
            "WB_DETAILED_XLSX_HEADERS_DUPLICATE",
        )


if __name__ == "__main__":
    unittest.main()
