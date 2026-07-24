from __future__ import annotations

import base64
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock
from zipfile import ZIP_DEFLATED, ZipFile

from quantum.application._finance_center_calculation import (
    _write_finance_output_bundle,
)
from quantum.application._finance_center_shared import NAV_ITEMS
from quantum.application._finance_profile_outputs import write_run_result_xlsx
from quantum.application.finance_profile import (
    FinanceProfileError,
    ProductRecord,
    build_profile,
    calculate_by_group,
)
from quantum.ingestion import XlsxInspectionLimits
from quantum.ingestion._xlsx_contracts import XlsxInspectionError
from quantum.pilot.windows_runner import discover_schema
from quantum.reporting.runtime import ReportingError, _decode_cursor, _encode_cursor
from quantum.scripts.ci import scan_forbidden_markers


BASE_ROW = {
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
    "srid": "reaudit-sale",
}


def _profile(*, cost: str = "400", other: str = "40"):
    profile = build_profile(
        (ProductRecord("KNOWN", "Товар", "Футболка", "reaudit"),)
    )
    profile.tax_rate_percent = "6"
    profile.tax_base_metric_id = "gross_sales_amount"
    profile.other_expense_per_unit = other
    group = profile.groups["Футболка"]
    group.cost_per_unit = cost
    group.resalable_returned_units = "0"
    group.compensated_returned_units = "0"
    group.return_compensation_amount = "0"
    group.discounts_amount = "0"
    group.subsidies_amount = "0"
    group.advertising_amount = "0"
    return profile


def _calculate(rows=(BASE_ROW,), profile=None):
    return calculate_by_group(
        detailed_rows=rows,
        profile=profile or _profile(),
        organization_id="tenant-reaudit",
        source_id="reaudit:source",
        source_sha256="e" * 64,
    )


_LIMITS = XlsxInspectionLimits(
    max_file_bytes=104857600,
    max_archive_entries=10000,
    max_total_uncompressed_bytes=536870912,
    max_entry_uncompressed_bytes=134217728,
    max_compression_ratio=100,
    max_xml_bytes=134217728,
    max_rows=1000000,
    max_columns=500,
)


class QuantumReauditPlateauR1Tests(unittest.TestCase):
    def test_known_answer_and_missing_cost_fail_closed(self) -> None:
        result = _calculate()
        self.assertEqual(result.status, "CALCULATED")
        self.assertEqual(result.totals["net_profit_amount"], "680.00")
        self.assertEqual(result.totals["tax_amount"], "120.00")
        with self.assertRaises(FinanceProfileError):
            _calculate(profile=_profile(cost=""))

    def test_return_cost_restoration_and_compensation(self) -> None:
        sale = dict(
            BASE_ROW,
            rrdId="501",
            srid="return-sale",
            quantity="2",
            retailAmount="2000",
            ppvzSalesCommission="200",
            forPay="1800",
            deliveryAmount="0",
            deliveryService="0",
            paidStorage="0",
        )
        returned = dict(
            BASE_ROW,
            rrdId="502",
            srid="return-event",
            docTypeName="Возврат",
            sellerOperName="Возврат",
            quantity="1",
            retailAmount="1000",
            ppvzSalesCommission="100",
            forPay="900",
            deliveryAmount="0",
            returnAmount="0",
            deliveryService="0",
            paidStorage="0",
        )
        profile = _profile()
        profile.groups["Футболка"].resalable_returned_units = "1"
        result = _calculate((sale, returned), profile)
        self.assertEqual(result.totals["product_cost_amount"], "400.00")
        self.assertEqual(result.totals["net_profit_amount"], "400.00")

    def test_duplicate_and_unknown_product_block(self) -> None:
        duplicate = _calculate((BASE_ROW, dict(BASE_ROW)))
        self.assertEqual(duplicate.status, "CALCULATION_BLOCKED")
        self.assertIn(
            "Футболка: WB_DETAILED_EVENT_DUPLICATE",
            duplicate.missing_inputs,
        )
        unknown = _calculate(
            (dict(BASE_ROW, vendorCode="UNKNOWN", rrdId="9", srid="u"),)
        )
        self.assertEqual(
            unknown.missing_inputs,
            ("UNKNOWN_PRODUCT_FINANCIAL_ROWS:1",),
        )

    def test_primary_block_reason_is_actionable(self) -> None:
        profile = _profile()
        profile.groups["Футболка"].return_compensation_amount = "500"
        result = _calculate(profile=profile)
        self.assertIn(
            "Футболка: RETURN_COMPENSATION_SEMANTICS_INVALID",
            result.missing_inputs,
        )
        self.assertFalse(
            any(item.endswith("net_profit_amount") for item in result.missing_inputs)
        )

    def test_output_bundle_is_transactional_unique_and_governed(self) -> None:
        result = _calculate()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, _, _ = _write_finance_output_bundle(root, result)
            second, _, _ = _write_finance_output_bundle(root, result)
            self.assertNotEqual(first["JSON"].parent, second["JSON"].parent)
            for outputs in (first, second):
                self.assertEqual(
                    set(outputs),
                    {"JSON", "Recommendations", "Excel", "Dashboard"},
                )
                self.assertTrue(all(path.stat().st_size > 0 for path in outputs.values()))
                with ZipFile(outputs["Excel"]) as archive:
                    workbook = archive.read("xl/workbook.xml").decode("utf-8")
                    self.assertIn("Рекомендации", workbook)
            self.assertFalse(tuple(root.glob(".quantum-run-*.tmp")))

    def test_output_failure_leaves_no_published_partial_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch(
                "quantum.application._finance_center_calculation.write_run_dashboard",
                side_effect=OSError("forced"),
            ):
                with self.assertRaises(OSError):
                    _write_finance_output_bundle(root, _calculate())
            self.assertFalse(tuple(root.glob("Quantum_Run_*")))
            self.assertFalse(tuple(root.glob(".quantum-run-*.tmp")))

    def test_concurrent_output_names_do_not_collide(self) -> None:
        result = _calculate()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parents = []
            errors = []

            def worker() -> None:
                try:
                    outputs, _, _ = _write_finance_output_bundle(root, result)
                    parents.append(outputs["JSON"].parent)
                except Exception as exc:  # pragma: no cover
                    errors.append(type(exc).__name__)

            threads = [threading.Thread(target=worker) for _ in range(12)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(errors, [])
            self.assertEqual(len(set(parents)), 12)

    def test_noncanonical_cursor_alias_is_rejected(self) -> None:
        digest = "a" * 64
        cursor = _encode_cursor(1, digest)
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        noncanonical = base64.urlsafe_b64encode(raw).decode("ascii")
        with self.assertRaises(ReportingError):
            _decode_cursor(noncanonical, digest)
        self.assertEqual(_decode_cursor(cursor, digest), 1)

    def test_windows_schema_discovery_rejects_xml_comment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / "base.xlsx"
            modified = Path(directory) / "comment.xlsx"
            write_run_result_xlsx(base, _calculate())
            with ZipFile(base) as source, ZipFile(
                modified, "w", ZIP_DEFLATED
            ) as target:
                for info in source.infolist():
                    payload = source.read(info.filename)
                    if info.filename == "xl/workbook.xml":
                        payload = payload.replace(
                            b"<workbook ", b"<!--reaudit--><workbook ", 1
                        )
                    target.writestr(info, payload)
            with self.assertRaises(XlsxInspectionError) as context:
                discover_schema(payload=modified.read_bytes(), limits=_LIMITS)
            self.assertEqual(
                context.exception.code,
                "XLSX_XML_COMMENT_FORBIDDEN",
            )

    def test_marketplace_write_scanner_covers_powershell_and_json(self) -> None:
        for name, payload in (
            ("bad.ps1", "$env:MARKETPLACE_WRITE_ENABLED = $true"),
            ("bad.json", '{"marketplace_write_enabled": true}'),
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / name).write_text(payload, encoding="utf-8")
                with self.assertRaises(RuntimeError):
                    scan_forbidden_markers(root)

    def test_approved_navigation_contract(self) -> None:
        self.assertEqual(
            tuple(label for _key, label in NAV_ITEMS),
            (
                "Центр решений",
                "Аналитика",
                "Финансы",
                "Товары",
                "Реклама",
                "Склад и поставки",
                "Конкуренты",
                "SEO",
                "Аналитик AI",
                "Отчёты",
                "Настройки",
            ),
        )


if __name__ == "__main__":
    unittest.main()
