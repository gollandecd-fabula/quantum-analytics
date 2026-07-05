from __future__ import annotations

from io import BytesIO
import unittest
from xml.etree import ElementTree
from zipfile import ZipFile

from quantum.outputs import build_local_output_bundle, render_xlsx_report
from quantum.outputs.xlsx_ooxml import Cell, ColumnSpec, WorksheetSpec, _worksheet_xml
from tests.test_local_output_bundle_r1 import GENERATED_AT, report


MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
CHART = "{http://schemas.openxmlformats.org/drawingml/2006/chart}"


def _cell(root, reference: str):
    return root.find(f".//{MAIN}c[@r='{reference}']")


def _inline_text(root, reference: str) -> str:
    cell = _cell(root, reference)
    if cell is None:
        return ""
    text = cell.find(f".//{MAIN}t")
    return "" if text is None or text.text is None else text.text


class ExcelReportR1Tests(unittest.TestCase):
    def _payload(self) -> bytes:
        bundle = build_local_output_bundle(report(), generated_at=GENERATED_AT)
        return render_xlsx_report(bundle)

    def test_workbook_is_deterministic_and_management_formatted(self):
        first = self._payload()
        second = self._payload()
        self.assertEqual(first, second)
        with ZipFile(BytesIO(first)) as archive:
            summary = ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
            recommendations = ElementTree.fromstring(archive.read("xl/worksheets/sheet2.xml"))
            finance = ElementTree.fromstring(archive.read("xl/worksheets/sheet3.xml"))
            styles = ElementTree.fromstring(archive.read("xl/styles.xml"))
            chart = ElementTree.fromstring(archive.read("xl/charts/chart1.xml"))

            self.assertEqual(_inline_text(summary, "A1"), "QUANTUM ANALYTICS — УПРАВЛЕНЧЕСКИЙ ОТЧЁТ")
            self.assertEqual(_inline_text(summary, "A5"), "Чистая прибыль")
            self.assertEqual(_cell(summary, "A6").get("t"), None)
            self.assertEqual(_cell(summary, "A6").find(f"{MAIN}v").text, "-2400.00")
            self.assertEqual(_cell(summary, "B13").get("s"), "35")
            self.assertIsNotNone(summary.find(f"{MAIN}hyperlinks"))
            self.assertIsNotNone(summary.find(f"{MAIN}drawing"))

            self.assertEqual(_inline_text(recommendations, "A5"), "Срочность")
            self.assertEqual(_inline_text(recommendations, "D5"), "Действие")
            self.assertEqual(_inline_text(recommendations, "L5"), "ID")
            pane = recommendations.find(f".//{MAIN}pane")
            self.assertEqual(pane.get("xSplit"), "4")
            self.assertEqual(pane.get("ySplit"), "5")
            self.assertEqual(_cell(recommendations, "F6").get("t"), None)

            self.assertEqual(_cell(finance, "D9").get("s"), "35")
            self.assertEqual(_cell(finance, "D12").get("s"), "9")

            num_formats = styles.find(f"{MAIN}numFmts")
            self.assertEqual(num_formats.get("count"), "4")
            self.assertEqual(styles.find(f"{MAIN}dxfs").get("count"), "4")

            self.assertEqual(chart.findall(f".//{CHART}f"), [])
            labels = [node.text for node in chart.findall(f".//{CHART}strLit/{CHART}pt/{CHART}v")]
            self.assertIn("Продажи", labels)
            self.assertIn("Себестоимость", labels)
            self.assertIn("Прибыль", labels)

    def test_only_static_negative_conditional_rules_are_used(self):
        with ZipFile(BytesIO(self._payload())) as archive:
            operators = []
            for name in archive.namelist():
                if not (name.startswith("xl/worksheets/sheet") and name.endswith(".xml")):
                    continue
                root = ElementTree.fromstring(archive.read(name))
                self.assertEqual(root.findall(f".//{MAIN}f"), [])
                operators.extend(
                    rule.get("operator")
                    for rule in root.findall(f".//{MAIN}cfRule")
                )
            self.assertTrue(operators)
            self.assertEqual(set(operators), {"lessThan"})

    def test_source_text_starting_with_equals_remains_inline_string(self):
        worksheet = WorksheetSpec(
            name="Formula safety",
            rows=((Cell("=HYPERLINK(\"https://example.invalid\",\"x\")"),),),
            columns=(ColumnSpec(20),),
        )
        root = ElementTree.fromstring(_worksheet_xml(worksheet))
        self.assertEqual(root.findall(f".//{MAIN}f"), [])
        cell = _cell(root, "A1")
        self.assertEqual(cell.get("t"), "inlineStr")
        self.assertTrue(_inline_text(root, "A1").startswith("="))

    def test_hyperlinks_are_internal_only(self):
        with ZipFile(BytesIO(self._payload())) as archive:
            for index in range(1, 13):
                root = ElementTree.fromstring(
                    archive.read(f"xl/worksheets/sheet{index}.xml")
                )
                for hyperlink in root.findall(f".//{MAIN}hyperlink"):
                    location = hyperlink.get("location") or ""
                    self.assertTrue(location.startswith("'"))
                    self.assertNotIn("://", location)


if __name__ == "__main__":
    unittest.main()
