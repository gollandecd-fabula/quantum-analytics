import io
import unittest
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from quantum.adapters.wildberries import (
    WbSourceBridgeError,
    bridge_admitted_xlsx,
)
from quantum.ingestion import XlsxInspectionLimits
from quantum.ingestion._xlsx_contracts import normalized_header_sha256


HEADERS = [
    "Бренд",
    "Предмет",
    "Сезон",
    "Коллекция",
    "Наименование",
    "Артикул продавца",
    "Артикул WB",
    "Баркод",
    "Размер",
    "Контракт",
    "Склад",
    "шт.",
    "Сумма заказов минус комиссия WB, руб.",
    "Выкупили, шт.",
    "К перечислению за товар, руб.",
    "Текущий остаток, шт.",
]


def _column(index):
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _inline_cell(column, row, value):
    reference = f"{_column(column)}{row}"
    return (
        f'<c r="{reference}" t="inlineStr"><is><t>'
        f"{escape(str(value))}"
        "</t></is></c>"
    )


def _row(index, values):
    cells = "".join(
        _inline_cell(column, index, value)
        for column, value in enumerate(values, start=1)
    )
    return f'<row r="{index}">{cells}</row>'


def workbook(rows):
    sheet_rows = [_row(1, ["Отчёт по товарам"]), _row(2, HEADERS)]
    sheet_rows.extend(_row(index, values) for index, values in enumerate(rows, 3))
    worksheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData>"
        + "".join(sheet_rows)
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


def discovery(row_count, headers=None):
    headers = HEADERS if headers is None else headers
    return {
        "sheet_name": "Sheet1",
        "header_row_index": 2,
        "headers": headers,
        "header_sha256": normalized_header_sha256(tuple(headers)),
        "data_row_count": row_count,
    }


def supplier_row(
    *,
    article,
    barcode,
    size,
    warehouse,
    ordered,
    ordered_amount,
    bought,
    payout,
    stock,
):
    return [
        "LarannA",
        "Футболка",
        "Лето",
        "2026",
        "Тестовый товар",
        article,
        "100001",
        barcode,
        size,
        "FBO",
        warehouse,
        ordered,
        ordered_amount,
        bought,
        payout,
        stock,
    ]


class WbSourceBridgeR1Tests(unittest.TestCase):
    def test_supplier_goods_is_aggregated_without_raw_rows(self):
        payload = workbook(
            [
                supplier_row(
                    article="A-1",
                    barcode="460000000001",
                    size="S",
                    warehouse="Коледино",
                    ordered="3",
                    ordered_amount="300,50",
                    bought="2",
                    payout="200,25",
                    stock="5",
                ),
                supplier_row(
                    article="A-2",
                    barcode="460000000002",
                    size="M",
                    warehouse="Тула",
                    ordered="4",
                    ordered_amount="400.50",
                    bought="1",
                    payout="100.25",
                    stock="1",
                ),
            ]
        )
        result = bridge_admitted_xlsx(
            payload=payload,
            schema_discovery=discovery(2),
            limits=limits(),
        )
        self.assertEqual(result["status"], "SOURCE_BRIDGE_COMPLETE")
        self.assertEqual(result["source_type"], "WB_SUPPLIER_GOODS")
        self.assertEqual(result["row_count"], 2)
        self.assertEqual(result["canonical_key_count"], 2)
        self.assertEqual(result["dimensions"]["seller_article_count"], 2)
        self.assertEqual(result["dimensions"]["warehouse_count"], 2)
        metrics = result["observed_metrics"]
        self.assertEqual(metrics["ordered_units"]["value"], "7")
        self.assertEqual(
            metrics["ordered_amount_net_commission"]["value"],
            "701.00",
        )
        self.assertEqual(metrics["bought_units"]["value"], "3")
        self.assertEqual(metrics["payout_amount"]["value"], "300.50")
        self.assertEqual(metrics["current_stock_units"]["value"], "6")
        self.assertIsNone(result["finance_request"])
        self.assertEqual(result["finance_request_state"], "BLOCKED")
        self.assertFalse(result["raw_rows_in_report"])
        self.assertNotIn("rows", result)

    def test_duplicate_business_key_is_blocked(self):
        duplicate = supplier_row(
            article="A-1",
            barcode="460000000001",
            size="S",
            warehouse="Коледино",
            ordered="1",
            ordered_amount="100",
            bought="1",
            payout="80",
            stock="1",
        )
        payload = workbook([duplicate, duplicate])
        with self.assertRaises(WbSourceBridgeError) as error:
            bridge_admitted_xlsx(
                payload=payload,
                schema_discovery=discovery(2),
                limits=limits(),
            )
        self.assertEqual(
            error.exception.code,
            "WB_SUPPLIER_GOODS_DUPLICATE_KEY",
        )

    def test_negative_amount_is_blocked(self):
        payload = workbook(
            [
                supplier_row(
                    article="A-1",
                    barcode="460000000001",
                    size="S",
                    warehouse="Коледино",
                    ordered="1",
                    ordered_amount="-1",
                    bought="1",
                    payout="80",
                    stock="1",
                )
            ]
        )
        with self.assertRaises(WbSourceBridgeError) as error:
            bridge_admitted_xlsx(
                payload=payload,
                schema_discovery=discovery(1),
                limits=limits(),
            )
        self.assertEqual(
            error.exception.code,
            "WB_SUPPLIER_GOODS_ORDERED_AMOUNT_INVALID",
        )

    def test_discovery_hash_tampering_is_blocked(self):
        payload = workbook(
            [
                supplier_row(
                    article="A-1",
                    barcode="460000000001",
                    size="S",
                    warehouse="Коледино",
                    ordered="1",
                    ordered_amount="100",
                    bought="1",
                    payout="80",
                    stock="1",
                )
            ]
        )
        candidate = discovery(1)
        candidate["header_sha256"] = "0" * 64
        with self.assertRaises(WbSourceBridgeError) as error:
            bridge_admitted_xlsx(
                payload=payload,
                schema_discovery=candidate,
                limits=limits(),
            )
        self.assertEqual(
            error.exception.code,
            "WB_BRIDGE_DISCOVERY_HASH_MISMATCH",
        )

    def test_unknown_wb_schema_is_blocked(self):
        payload = workbook([])
        unknown = list(HEADERS)
        unknown[-1] = "Неизвестный остаток"
        with self.assertRaises(WbSourceBridgeError) as error:
            bridge_admitted_xlsx(
                payload=payload,
                schema_discovery=discovery(0, unknown),
                limits=limits(),
            )
        self.assertEqual(error.exception.code, "WB_SOURCE_SCHEMA_UNSUPPORTED")


if __name__ == "__main__":
    unittest.main()
