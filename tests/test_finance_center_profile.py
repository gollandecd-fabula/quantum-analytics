from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from quantum.application.local_processing import (
    FinanceRunResult,
    GroupCalculation,
    ProductRecord,
    apply_costs,
    build_profile,
    calculate_by_group,
    confirm_profile,
    detect_products_from_xlsx,
    parse_cost_workbook,
    read_detailed_financial_rows,
    reassign_product,
    rename_group,
    validate_profile,
    write_cost_template,
    write_run_dashboard,
    write_run_result_xlsx,
)


SUPPLIER_HEADERS = [
    "Бренд",
    "Предмет",
    "Наименование",
    "Артикул продавца",
    "Артикул WB",
    "Баркод",
]


def _column(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _row(index: int, values: list[object]) -> str:
    cells = "".join(
        f'<c r="{_column(column)}{index}" t="inlineStr">'
        f"<is><t>{escape(str(value))}</t></is></c>"
        for column, value in enumerate(values, start=1)
    )
    return f'<row r="{index}">{cells}</row>'


def _workbook(
    path: Path,
    headers: list[object],
    rows: list[list[object]],
    *,
    title: str = "Отчёт",
) -> None:
    sheet_rows = [_row(1, [title]), _row(2, headers)]
    sheet_rows.extend(
        _row(index, values)
        for index, values in enumerate(rows, start=3)
    )
    worksheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/'
        'spreadsheetml/2006/main"><sheetData>'
        + "".join(sheet_rows)
        + "</sheetData></worksheet>"
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/'
        'spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships"><sheets><sheet name="Sheet1" '
        'sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    relationships = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
        '2006/relationships"><Relationship Id="rId1" Type="http://schemas.'
        'openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/></Relationships>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
        'content-types"><Default Extension="rels" ContentType="application/'
        'vnd.openxmlformats-package.relationships+xml"/><Default '
        'Extension="xml" ContentType="application/xml"/><Override '
        'PartName="/xl/workbook.xml" ContentType="application/vnd.'
        'openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/'
        'vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )
    root_relationships = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
        '2006/relationships"><Relationship Id="rId1" Type="http://schemas.'
        'openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/></Relationships>'
    )
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_relationships)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", relationships)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)


def _confirmed_profile(
    product_id: str = "KNOWN",
    group_name: str = "Футболка",
):
    profile = build_profile(
        (ProductRecord(product_id, "Товар", group_name, "one.xlsx"),)
    )
    profile.tax_rate_percent = "6"
    profile.tax_base_metric_id = "gross_sales_amount"
    profile.other_expense_per_unit = "40"
    group = profile.groups[group_name]
    group.cost_per_unit = "400"
    group.resalable_returned_units = "0"
    group.compensated_returned_units = "0"
    group.return_compensation_amount = "0"
    group.discounts_amount = "0"
    group.subsidies_amount = "0"
    group.advertising_amount = "0"
    confirm_profile(profile)
    return profile


class FinanceCenterProfileTests(unittest.TestCase):
    def test_standard_wb_identifiers_use_seller_article_priority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "supplier.xlsx"
            _workbook(
                path,
                SUPPLIER_HEADERS,
                [
                    [
                        "LarannA",
                        "Футболка",
                        "Модель 1",
                        "SELLER-1",
                        "10001",
                        "46001",
                    ],
                    [
                        "LarannA",
                        "Лонгслив",
                        "Модель 2",
                        "SELLER-2",
                        "10002",
                        "46002",
                    ],
                ],
            )
            products = detect_products_from_xlsx(path)
        self.assertEqual(
            [item.product_id for item in products],
            ["SELLER-1", "SELLER-2"],
        )
        self.assertEqual(
            [item.detected_group for item in products],
            ["Футболка", "Лонгслив"],
        )

    def test_manual_group_mapping_is_preserved_and_editable(self) -> None:
        products = (
            ProductRecord("A", "Товар A", "Футболка", "one.xlsx"),
            ProductRecord("B", "Товар B", "Лонгслив", "one.xlsx"),
        )
        profile = build_profile(products)
        reassign_product(profile, "B", "Футболка")
        rename_group(profile, "Футболка", "Верх")
        profile.tax_rate_percent = "6"
        profile.tax_base_metric_id = "gross_sales_amount"
        profile.other_expense_per_unit = "40"
        profile.groups["Верх"].cost_per_unit = "400"
        confirm_profile(profile)
        rebuilt = build_profile(products, profile)
        self.assertEqual(
            rebuilt.product_to_group,
            {"A": "Верх", "B": "Верх"},
        )
        self.assertEqual(rebuilt.groups["Верх"].product_ids, ["A", "B"])
        self.assertTrue(rebuilt.confirmed)
        self.assertEqual(
            rebuilt.tax_base_metric_id,
            "gross_sales_amount",
        )

    def test_missing_values_block_but_explicit_zero_is_valid(self) -> None:
        profile = build_profile(
            (ProductRecord("A", "Товар", "Футболка", "one.xlsx"),)
        )
        self.assertEqual(
            validate_profile(profile),
            (
                "Налоговая ставка",
                "Налоговая база",
                "Прочие расходы на единицу",
                "Себестоимость: Футболка",
            ),
        )
        profile.tax_rate_percent = "0"
        profile.tax_base_metric_id = "gross_sales_amount"
        profile.other_expense_per_unit = "0"
        profile.groups["Футболка"].cost_per_unit = "0"
        confirm_profile(profile)
        self.assertTrue(profile.confirmed)
        self.assertEqual(
            profile.groups["Футболка"].cost_per_unit,
            "0.00",
        )
        self.assertEqual(profile.other_expense_per_unit, "0.00")

    def test_cost_excel_import_maps_one_value_per_group(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cost.xlsx"
            _workbook(
                path,
                ["Группа", "Себестоимость, ₽"],
                [["Футболка", "400"], ["Лонгслив", "500,50"]],
                title="Себестоимость",
            )
            costs = parse_cost_workbook(path)
        profile = build_profile(
            (
                ProductRecord("A", "Товар A", "Футболка", "one.xlsx"),
                ProductRecord("B", "Товар B", "Лонгслив", "one.xlsx"),
            )
        )
        self.assertEqual(apply_costs(profile, costs), ())
        self.assertEqual(
            profile.groups["Футболка"].cost_per_unit,
            "400.00",
        )
        self.assertEqual(
            profile.groups["Лонгслив"].cost_per_unit,
            "500.50",
        )

    def test_group_merge_conflict_requires_cost_reconfirmation(self) -> None:
        profile = build_profile(
            (
                ProductRecord("A", "Товар A", "Футболка", "one.xlsx"),
                ProductRecord("B", "Товар B", "Лонгслив", "one.xlsx"),
            )
        )
        profile.groups["Футболка"].cost_per_unit = "400"
        profile.groups["Лонгслив"].cost_per_unit = "500"
        rename_group(profile, "Лонгслив", "Футболка")
        self.assertIsNone(profile.groups["Футболка"].cost_per_unit)
        self.assertIn(
            "Себестоимость: Футболка",
            validate_profile(profile),
        )

    def test_duplicate_cost_group_is_blocked_even_when_values_match(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate-cost.xlsx"
            _workbook(
                path,
                ["Группа", "Себестоимость, ₽"],
                [["Футболка", "400"], ["Футболка", "400"]],
                title="Себестоимость",
            )
            with self.assertRaisesRegex(
                ValueError,
                "COST_GROUP_DUPLICATE",
            ):
                parse_cost_workbook(path)

    def test_generated_cost_template_is_valid_xlsx_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "template.xlsx"
            write_cost_template(path, ["Футболка", "Лонгслив"])
            with ZipFile(path) as archive:
                names = set(archive.namelist())
                worksheet = archive.read(
                    "xl/worksheets/sheet1.xml"
                ).decode("utf-8")
        self.assertIn("[Content_Types].xml", names)
        self.assertIn("xl/workbook.xml", names)
        self.assertIn("Футболка", worksheet)
        self.assertIn("Лонгслив", worksheet)

    def test_blank_context_aliases_are_filled_without_conflict(self) -> None:
        headers = [
            "№ отчёта",
            "Начало периода",
            "Конец периода",
            "Валюта",
            "Обоснование",
            "Кол-во",
            "Продажи/возвраты, ₽",
            "К перечислению продавцу, ₽",
        ]
        report = {
            "source_bridge": {
                "report_ids": ["77"],
                "report_periods": {
                    "77": {
                        "date_from": "2026-07-01",
                        "date_to": "2026-07-07",
                    }
                },
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "detailed.xlsx"
            _workbook(
                path,
                headers,
                [["", "", "", "", "Продажа", "1", "1000", "800"]],
            )
            rows = read_detailed_financial_rows(path, report)
        self.assertEqual(rows[0]["№ отчёта"], "77")
        self.assertEqual(rows[0]["Начало периода"], "2026-07-01")
        self.assertEqual(rows[0]["Конец периода"], "2026-07-07")
        self.assertEqual(rows[0]["Валюта"], "RUB")

    def test_confirmed_group_calculation_matches_known_financial_result(
        self,
    ) -> None:
        profile = _confirmed_profile()
        row = {
            "reportId": "77",
            "rrdId": "1",
            "dateFrom": "2026-07-01",
            "dateTo": "2026-07-07",
            "currency": "RUB",
            "vendorCode": "KNOWN",
            "techSize": "M",
            "sku": "460000000001",
            "docTypeName": "Продажа",
            "sellerOperName": "Продажа",
            "quantity": "2",
            "retailAmount": "2000",
            "ppvzSalesCommission": "200",
            "forPay": "1680",
            "ppvzReward": "0",
            "acquiringFee": "0",
            "deliveryAmount": "1",
            "returnAmount": "0",
            "deliveryService": "100",
            "paidStorage": "20",
            "penalty": "0",
            "deduction": "0",
            "paidAcceptance": "0",
            "rebillLogisticCost": "0",
            "additionalPayment": "0",
            "orderDt": "2026-07-01",
            "saleDt": "2026-07-02",
            "srid": "sale-1",
        }
        result = calculate_by_group(
            detailed_rows=(row,),
            profile=profile,
            organization_id="tenant-home-local",
            source_id="dataset:test",
            source_sha256="b" * 64,
        )
        self.assertEqual(result.status, "CALCULATED")
        self.assertEqual(result.totals["net_sold_units"], "2.00")
        self.assertEqual(result.totals["product_cost_amount"], "800.00")
        self.assertEqual(result.totals["other_expense_amount"], "80.00")
        self.assertEqual(result.totals["tax_amount"], "120.00")
        self.assertEqual(result.totals["net_profit_amount"], "680.00")

    def test_unattributed_financial_rows_block_entire_calculation(
        self,
    ) -> None:
        result = calculate_by_group(
            detailed_rows=({"vendorCode": "UNKNOWN"},),
            profile=_confirmed_profile(),
            organization_id="tenant-home-local",
            source_id="dataset:test",
            source_sha256="a" * 64,
        )
        self.assertEqual(result.status, "CALCULATION_BLOCKED")
        self.assertEqual(
            result.missing_inputs,
            ("UNKNOWN_PRODUCT_FINANCIAL_ROWS:1",),
        )

    def test_offline_result_exports_are_created(self) -> None:
        result = FinanceRunResult(
            status="CALCULATED",
            group_results=(
                GroupCalculation(
                    group_name="Футболка",
                    state="VALID",
                    reason_codes=(),
                    calculation={
                        "results": {
                            "net_profit_amount": {"value": "1234.50"}
                        }
                    },
                    observed_metrics={},
                ),
            ),
            totals={
                "net_sold_units": "10.00",
                "net_marketplace_income_amount": "8000.00",
                "product_cost_amount": "4000.00",
                "other_expense_amount": "400.00",
                "tax_amount": "600.00",
                "net_profit_amount": "3000.00",
                "profit_per_sold_unit": "300.00",
            },
            missing_inputs=(),
        )
        with tempfile.TemporaryDirectory() as directory:
            xlsx = Path(directory) / "report.xlsx"
            dashboard = Path(directory) / "dashboard.html"
            write_run_result_xlsx(xlsx, result)
            write_run_dashboard(dashboard, result)
            with ZipFile(xlsx) as archive:
                names = set(archive.namelist())
            html = dashboard.read_text(encoding="utf-8")
        self.assertIn("xl/worksheets/sheet1.xml", names)
        self.assertIn("xl/worksheets/sheet2.xml", names)
        self.assertIn("Quantum · аналитика Wildberries", html)
        self.assertIn("запись на маркетплейс отключена", html)
        self.assertNotIn("https://", html)

    def test_color_ui_and_installed_launcher_contract(self) -> None:
        root = Path(__file__).resolve().parents[1]
        ui = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(
                (root / "src/quantum/application").glob(
                    "_finance_center_*.py"
                )
            )
        )
        for token in (
            "Центр решений",
            "Себестоимость и расходы",
            "Аналитика",
            "Рекомендации",
            "Контроль данных",
            "#1769AA",
            "#14866D",
            "#E97824",
        ):
            self.assertIn(token, ui)
        launcher = (
            root / "scripts/windows/one_click_home_local.ps1"
        ).read_text(encoding="ascii")
        self.assertIn("quantum.application.desktop_center", launcher)
        self.assertIn("$SkipInstall -and -not $NonInteractive", launcher)
        self.assertIn(
            'if ($File) { $importArguments["File"] = $File }',
            launcher,
        )
        self.assertNotIn("-AuthorityAttested -SchemaReviewed", launcher)
        self.assertNotIn("marketplace_write_enabled = True", ui)


if __name__ == "__main__":
    unittest.main()
