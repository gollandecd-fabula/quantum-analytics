from __future__ import annotations

from io import BytesIO
import bz2
import gzip
import json
import lzma
import stat
from pathlib import Path
import tarfile
import tempfile
import unittest
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from quantum.application._finance_generic_tabular import (
    MetricGroupEvidence,
    extract_metric_groups,
    merge_metric_groups,
)
from quantum.application.finance_profile import (
    FinanceProfile,
    GroupInput,
    calculate_metric_groups,
    detect_products_from_any_file,
    load_profile,
    save_profile,
    save_run_result,
    write_run_dashboard,
    write_run_result_xlsx,
    write_cost_template,
)
from quantum.application._finance_profile_financial_rows import _typed
from quantum.pilot.universal_intake import classify_payload, register_file
from quantum.pilot.universal_tables import ExtractedTable, extract_tables


def _table(name: str, rows: list[dict[str, str]]) -> ExtractedTable:
    headers = tuple(rows[0])
    return ExtractedTable(
        source_name=name,
        member_path=name,
        detected_format="TEST",
        headers=headers,
        rows=tuple(rows),
        source_sha256=("a" * 64 if name == "one" else "b" * 64),
    )


def _money(value: str | None, reason: str = "MISSING") -> dict:
    return _typed(
        "VALID" if value is not None else "BLOCKED",
        value,
        "MONEY",
        "MONEY",
        "RUB",
        reason_code=None if value is not None else reason,
        source_ids=("test",),
    )


def _integer(value: str | None, reason: str = "MISSING") -> dict:
    return _typed(
        "VALID" if value is not None else "BLOCKED",
        value,
        "INTEGER",
        "ITEM",
        reason_code=None if value is not None else reason,
        source_ids=("test",),
    )


def _kernel_inputs(*, sales: str = "1000", units: str = "2") -> dict:
    return {
        "gross_sales_units": _integer(units),
        "returned_units": _integer("0"),
        "resalable_returned_units": _integer("0"),
        "compensated_returned_units": _integer("0"),
        "return_compensation_amount": _money("0"),
        "gross_sales_amount": _money(sales),
        "discounts_amount": _money("0"),
        "subsidies_excluding_return_compensation_amount": _money("0"),
        "marketplace_commission_amount": _money("100"),
        "forward_logistics_amount": _money("20"),
        "reverse_logistics_amount": _money("0"),
        "storage_amount": _money("10"),
        "advertising_amount": _money("0"),
        "fines_withholdings_amount": _money("0"),
    }


class UniversalPartialR1Tests(unittest.TestCase):
    def test_governance_records_universal_partial_contract_and_boundaries(self) -> None:
        root = Path(__file__).resolve().parents[1]
        rtm = json.loads(
            (root / "docs/evidence/UNIVERSAL_PARTIAL_R1_RTM.json").read_text(
                encoding="utf-8"
            )
        )
        defects = json.loads(
            (
                root
                / "docs/evidence/UNIVERSAL_PARTIAL_R1_DEFECT_REGISTER.json"
            ).read_text(encoding="utf-8")
        )
        state = (
            root / "docs/evidence/WB_RELEASE_R2_EXECUTION_STATE.yaml"
        ).read_text(encoding="utf-8")
        current = (root / "docs/governance/CURRENT_STATE.md").read_text(
            encoding="utf-8"
        )
        self.assertEqual(rtm["rtm_id"], "QUANTUM-UNIVERSAL-PARTIAL-R1")
        self.assertEqual(rtm["capability_gate"]["marketplace_writes"], "FORBIDDEN")
        self.assertEqual(defects["summary"]["open_p0"], 0)
        self.assertEqual(defects["summary"]["open_p1"], 0)
        self.assertEqual(defects["summary"]["open_reproducible_p2_correctness"], 0)
        for marker in (
            "id: QUANTUM-UNIVERSAL-PARTIAL-R1",
            "intake_contract: ACCEPT_EVERY_FILE_REGISTER_EVERY_RESULT",
            "calculation_contract: MAXIMUM_AVAILABLE_DEPENDENCY_SCOPED",
            "marketplace_writes: DISABLED",
            "physical_user_path_l5: UNVERIFIED",
        ):
            self.assertIn(marker, state)
        self.assertIn("every uploaded file receives an auditable per-file result", current)
        self.assertIn("partial totals expose coverage", current)
        self.assertIn("`RELEASE_BLOCKED`", current)

    def test_direct_csv_json_and_xml_tables(self) -> None:
        csv_result = extract_tables(
            "Артикул;Продажи;Комиссия\nA;1000;100\n".encode(),
            source_name="report.csv",
        )
        self.assertEqual(csv_result.status, "COMPLETE")
        self.assertEqual(len(csv_result.tables), 1)

        json_result = extract_tables(
            json.dumps([{"Артикул": "A", "Продажи": 1000}]).encode(),
            source_name="report.json",
        )
        self.assertEqual(json_result.tables[0].row_count, 1)

        xml_result = extract_tables(
            b"<root><row><sku>A</sku><sales>1000</sales></row><row><sku>B</sku><sales>500</sales></row></root>",
            source_name="report.xml",
        )
        self.assertEqual(xml_result.tables[0].row_count, 2)

    def test_mixed_zip_keeps_good_sibling_and_reports_bad_member(self) -> None:
        payload = BytesIO()
        with ZipFile(payload, "w", ZIP_DEFLATED) as archive:
            archive.writestr("good.csv", "Артикул;Продажи\nA;1000\n")
            archive.writestr("bad.json", "{not-json")
            archive.writestr("image.png", b"\x89PNG\r\n\x1a\n")
        result = extract_tables(payload.getvalue(), source_name="mixed.zip")
        self.assertEqual(result.status, "PARTIAL")
        self.assertEqual(len(result.tables), 1)
        member_states = {item.member_path: item.status for item in result.members}
        self.assertIn("mixed.zip/good.csv", member_states)
        self.assertEqual(member_states["mixed.zip/bad.json"], "UNSUPPORTED")

    def test_tar_gz_table_is_processed(self) -> None:
        raw = b"sku,sales\nA,1000\n"
        payload = BytesIO()
        with tarfile.open(fileobj=payload, mode="w:gz") as archive:
            info = tarfile.TarInfo("inside.csv")
            info.size = len(raw)
            archive.addfile(info, BytesIO(raw))
        result = extract_tables(payload.getvalue(), source_name="data.tar.gz")
        self.assertEqual(len(result.tables), 1)
        self.assertEqual(result.tables[0].member_path, "data.tar/inside.csv")

    def test_zip_slip_blocks_container(self) -> None:
        payload = BytesIO()
        with ZipFile(payload, "w", ZIP_DEFLATED) as archive:
            archive.writestr("../escape.csv", "a,b\n1,2\n")
        result = extract_tables(payload.getvalue(), source_name="bad.zip")
        self.assertEqual(result.status, "QUARANTINED_SECURITY")
        self.assertIn("ARCHIVE_PATH_INVALID", result.reason_codes)

    def test_register_any_file_does_not_error_for_unknown_binary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "unknown.bin"
            source.write_bytes(b"\x00\x01\x02opaque")
            report = register_file(
                file_path=source,
                storage_root=Path(directory) / "data",
            )
        self.assertIn(report["status"], {"ACCEPTED_UNPARSED", "ACCEPTED_PARTIAL"})
        self.assertFalse(report["marketplace_write_enabled"])
        self.assertIn("universal_extraction", report)

    def test_generic_table_maps_known_columns_without_fixed_report_hash(self) -> None:
        table = _table(
            "one",
            [
                {
                    "Артикул": "A",
                    "Обоснование": "Продажа",
                    "Кол-во": "2",
                    "Продажи/возвраты, ₽": "1000",
                    "Комиссия WB, ₽": "100",
                    "Логистика, ₽": "20",
                    "Хранение, ₽": "10",
                    "Штрафы, ₽": "0",
                }
            ],
        )
        groups = extract_metric_groups(table and (table,), product_to_group={"A": "Футболка"})
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].profile_group_name, "Футболка")
        self.assertEqual(groups[0].kernel_inputs["gross_sales_amount"]["value"], "1000.00")


    def test_generic_csv_can_create_editable_product_group(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "products.csv"
            path.write_text(
                "Артикул продавца;Наименование;Категория;Продажи\n"
                "SKU-1;Футболка 1;Футболки;1000\n",
                encoding="utf-8",
            )
            products = detect_products_from_any_file(path)
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0].product_id, "SKU-1")
        self.assertEqual(products[0].detected_group, "Футболки")

    def test_missing_tax_keeps_pre_tax_and_marketplace_income(self) -> None:
        profile = FinanceProfile(
            tax_rate_percent=None,
            tax_base_metric_id=None,
            other_expense_per_unit="10",
            groups={"Футболка": GroupInput("Футболка", ["A"], "100", "0", "0", "0", "0", "0", "0")},
            product_to_group={"A": "Футболка"},
        )
        evidence = MetricGroupEvidence(
            display_name="Футболка · one",
            profile_group_name="Футболка",
            source_name="one",
            source_sha256="a" * 64,
            member_path="one.csv",
            kernel_inputs=_kernel_inputs(),
            observed_metrics=_kernel_inputs(),
            reason_codes=(),
            row_count=1,
            excluded_row_count=0,
        )
        result = calculate_metric_groups(
            evidence_groups=(evidence,),
            profile=profile,
            organization_id="tenant",
        )
        self.assertEqual(result.status, "CALCULATED_PARTIAL")
        self.assertEqual(result.totals["net_marketplace_income_amount"], "870.00")
        self.assertEqual(result.totals["pre_tax_profit_amount"], "650.00")
        self.assertNotIn("net_profit_amount", result.totals)
        self.assertEqual(result.metric_states["tax_amount"]["state"], "BLOCKED")
        self.assertIn("Налог периода: TAX_RATE_REQUIRED", result.missing_inputs)

    def test_one_missing_group_cost_does_not_abort_complete_group(self) -> None:
        profile = FinanceProfile(
            tax_rate_percent="6",
            tax_base_metric_id="gross_sales_amount",
            other_expense_per_unit="10",
            groups={
                "A": GroupInput("A", ["A"], "100", "0", "0", "0", "0", "0", "0"),
                "B": GroupInput("B", ["B"], None, "0", "0", "0", "0", "0", "0"),
            },
            product_to_group={"A": "A", "B": "B"},
        )
        evidence = tuple(
            MetricGroupEvidence(
                display_name=f"{name} · one",
                profile_group_name=name,
                source_name="one",
                source_sha256=("a" if name == "A" else "b") * 64,
                member_path=f"{name}.csv",
                kernel_inputs=_kernel_inputs(sales="1000" if name == "A" else "500", units="2" if name == "A" else "1"),
                observed_metrics={},
                reason_codes=(),
                row_count=1,
                excluded_row_count=0,
            )
            for name in ("A", "B")
        )
        result = calculate_metric_groups(
            evidence_groups=evidence,
            profile=profile,
            organization_id="tenant",
        )
        self.assertEqual(result.status, "CALCULATED_PARTIAL")
        self.assertEqual(result.metric_states["product_cost_amount"]["state"], "PARTIAL")
        self.assertEqual(result.totals["product_cost_amount"], "200.00")
        self.assertTrue(any("COST_REQUIRED:B" in item for item in result.missing_inputs))
        self.assertTrue(any(item.state == "VALID" for item in result.group_results))

    def test_unknown_scope_does_not_abort_known_scope(self) -> None:
        profile = FinanceProfile(
            tax_rate_percent="6",
            tax_base_metric_id="gross_sales_amount",
            other_expense_per_unit="0",
            groups={"Known": GroupInput("Known", ["A"], "100", "0", "0", "0", "0", "0", "0")},
            product_to_group={"A": "Known"},
        )
        known = MetricGroupEvidence("Known · one", "Known", "one", "a" * 64, "known.csv", _kernel_inputs(), {}, (), 1, 0)
        unknown = MetricGroupEvidence("Не определено · two", None, "two", "b" * 64, "unknown.csv", _kernel_inputs(sales="300", units="1"), {}, ("UNKNOWN_PRODUCT_MAPPING_REQUIRED",), 1, 0)
        result = calculate_metric_groups(evidence_groups=(known, unknown), profile=profile, organization_id="tenant")
        self.assertEqual(result.status, "CALCULATED_PARTIAL")
        self.assertIn("net_marketplace_income_amount", result.totals)
        self.assertTrue(any(scope["scope"].startswith("Не определено") for scope in result.unresolved_scopes))


    def test_safe_xlsx_uses_universal_intake_without_specific_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "arbitrary-workbook.xlsx"
            write_cost_template(source, ["Футболка"])
            decision = classify_payload(source.read_bytes(), source.suffix)
            report = register_file(
                file_path=source,
                storage_root=Path(directory) / "data",
            )
        self.assertEqual(decision.status, "ACCEPTED_PARTIAL")
        self.assertEqual(decision.route, "UNIVERSAL_TABLES")
        self.assertEqual(report["status"], "ACCEPTED_PARTIAL")
        self.assertIsNotNone(report["stored_path"])
        self.assertGreater(
            report["universal_extraction"]["table_count"],
            0,
        )

    def test_content_not_extension_selects_delimited_table(self) -> None:
        result = extract_tables(
            b"sku;sales\nA;1000\n",
            source_name="renamed.json",
        )
        self.assertEqual(result.status, "COMPLETE")
        self.assertEqual(result.detected_format, "DELIMITED_TEXT")

    def test_single_stream_compressions_are_processed(self) -> None:
        raw = b"sku,sales\nA,1000\n"
        for name, payload in (
            ("report.csv.gz", gzip.compress(raw)),
            ("report.csv.bz2", bz2.compress(raw)),
            ("report.csv.xz", lzma.compress(raw)),
        ):
            with self.subTest(name=name):
                result = extract_tables(payload, source_name=name)
                self.assertEqual(result.status, "COMPLETE")
                self.assertEqual(result.tables[0].row_count, 1)

    def test_active_member_is_skipped_without_losing_safe_sibling(self) -> None:
        payload = BytesIO()
        with ZipFile(payload, "w", ZIP_DEFLATED) as archive:
            archive.writestr("good.csv", "sku,sales\nA,1000\n")
            archive.writestr("run.ps1", "Write-Host unsafe")
        result = extract_tables(payload.getvalue(), source_name="mixed.zip")
        self.assertEqual(result.status, "PARTIAL")
        self.assertEqual(len(result.tables), 1)
        self.assertTrue(
            any(
                item.status == "QUARANTINED_SECURITY"
                for item in result.members
            )
        )

    def test_symlink_and_compression_bomb_block_archive(self) -> None:
        symlink = BytesIO()
        with ZipFile(symlink, "w", ZIP_DEFLATED) as archive:
            info = ZipInfo("link.csv")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, "target.csv")
        linked = extract_tables(symlink.getvalue(), source_name="link.zip")
        self.assertEqual(linked.status, "QUARANTINED_SECURITY")
        self.assertIn("ARCHIVE_SYMLINK_FORBIDDEN", linked.reason_codes)

        bomb = BytesIO()
        with ZipFile(bomb, "w", ZIP_DEFLATED) as archive:
            archive.writestr("huge.csv", b"A" * 2_000_000)
        compressed = extract_tables(bomb.getvalue(), source_name="bomb.zip")
        self.assertEqual(compressed.status, "QUARANTINED_SECURITY")
        self.assertIn(
            "ARCHIVE_COMPRESSION_RATIO_EXCEEDED",
            compressed.reason_codes,
        )

    def test_rar_and_7z_are_registered_without_guessed_extraction(self) -> None:
        for name, payload in (
            ("report.7z", b"7z\xbc\xaf\x27\x1c" + b"0" * 32),
            ("report.rar", b"Rar!\x1a\x07\x01\x00" + b"0" * 32),
        ):
            result = extract_tables(payload, source_name=name)
            self.assertEqual(result.status, "UNSUPPORTED")
            self.assertIn(
                "ARCHIVE_FORMAT_REQUIRES_OPTIONAL_ADAPTER",
                result.reason_codes,
            )

    def test_complementary_sources_merge_but_overlap_conflicts(self) -> None:
        base = MetricGroupEvidence(
            "A · one",
            "A",
            "one",
            "a" * 64,
            "one.csv",
            {
                "gross_sales_amount": _money("1000"),
                "gross_sales_units": _integer("2"),
            },
            {"gross_sales_amount": _money("1000")},
            (),
            1,
            0,
        )
        complement = MetricGroupEvidence(
            "A · two",
            "A",
            "two",
            "b" * 64,
            "two.csv",
            {
                "marketplace_commission_amount": _money("100"),
            },
            {"marketplace_commission_amount": _money("100")},
            (),
            1,
            0,
        )
        merged = merge_metric_groups((base, complement))[0]
        self.assertEqual(
            merged.kernel_inputs["gross_sales_amount"]["state"],
            "VALID",
        )
        self.assertEqual(
            merged.kernel_inputs["marketplace_commission_amount"]["state"],
            "VALID",
        )
        conflict = merge_metric_groups(
            (
                base,
                MetricGroupEvidence(
                    "A · three",
                    "A",
                    "three",
                    "c" * 64,
                    "three.csv",
                    {"gross_sales_amount": _money("900")},
                    {"gross_sales_amount": _money("900")},
                    (),
                    1,
                    0,
                ),
            )
        )[0]
        self.assertEqual(
            conflict.kernel_inputs["gross_sales_amount"]["state"],
            "CONFLICT",
        )
        self.assertEqual(
            conflict.observed_metrics["gross_sales_amount"]["state"],
            "CONFLICT",
        )

    def test_profit_is_not_mixed_across_incompatible_coverage(self) -> None:
        profile = FinanceProfile(
            tax_rate_percent="6",
            tax_base_metric_id="gross_sales_amount",
            other_expense_per_unit="0",
            groups={
                "A": GroupInput("A", ["A"], "100", "0", "0", "0", "0", "0", "0"),
                "B": GroupInput("B", ["B"], None, "0", "0", "0", "0", "0", "0"),
            },
            product_to_group={"A": "A", "B": "B"},
        )
        evidence = tuple(
            MetricGroupEvidence(
                f"{name} · source",
                name,
                "source",
                ("a" if name == "A" else "b") * 64,
                f"{name}.csv",
                _kernel_inputs(sales="1000", units="2"),
                {"gross_sales_amount": _money("1000")},
                (),
                1,
                0,
            )
            for name in ("A", "B")
        )
        result = calculate_metric_groups(
            evidence_groups=evidence,
            profile=profile,
            organization_id="tenant",
        )
        self.assertEqual(result.metric_states["tax_amount"]["state"], "VALID")
        self.assertEqual(
            result.metric_states["pre_tax_profit_amount"]["state"],
            "PARTIAL",
        )
        self.assertNotIn("net_profit_amount", result.totals)
        self.assertIn(
            "COVERAGE_MISMATCH_PRE_TAX_VS_TAX",
            result.metric_states["net_profit_amount"]["reason_codes"],
        )

    def test_partial_profile_is_saved_and_reused_without_defaults(self) -> None:
        profile = FinanceProfile(
            tax_rate_percent="7,5",
            tax_base_metric_id=None,
            other_expense_per_unit=None,
            groups={
                "A": GroupInput("A", ["A"], None),
            },
            product_to_group={"A": "A"},
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "finance-profile.json"
            save_profile(path, profile)
            loaded = load_profile(path)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.tax_rate_percent, "7.5")
        self.assertIsNone(loaded.other_expense_per_unit)
        self.assertIsNone(loaded.groups["A"].cost_per_unit)
        self.assertFalse(loaded.confirmed)

    def test_partial_outputs_reconcile_and_show_missing_data(self) -> None:
        profile = FinanceProfile(
            tax_rate_percent=None,
            tax_base_metric_id="gross_sales_amount",
            other_expense_per_unit="0",
            groups={
                "A": GroupInput("A", ["A"], "100", "0", "0", "0", "0", "0", "0"),
            },
            product_to_group={"A": "A"},
        )
        evidence = MetricGroupEvidence(
            "A · source",
            "A",
            "source",
            "a" * 64,
            "source.csv",
            _kernel_inputs(),
            {"gross_sales_amount": _money("1000")},
            (),
            1,
            0,
        )
        result = calculate_metric_groups(
            evidence_groups=(evidence,),
            profile=profile,
            organization_id="tenant",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            json_path = root / "result.json"
            xlsx_path = root / "result.xlsx"
            html_path = root / "result.html"
            save_run_result(json_path, result)
            write_run_result_xlsx(xlsx_path, result)
            write_run_dashboard(html_path, result)
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            html = html_path.read_text(encoding="utf-8")
            with ZipFile(xlsx_path) as archive:
                summary = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
                needed = archive.read("xl/worksheets/sheet4.xml").decode("utf-8")
        self.assertEqual(
            payload["totals"]["net_marketplace_income_amount"],
            result.totals["net_marketplace_income_amount"],
        )
        self.assertIn(result.totals["net_marketplace_income_amount"], summary)
        self.assertIn("TAX_RATE_REQUIRED", needed)
        self.assertIn("TAX_RATE_REQUIRED", html)
        self.assertIn("CALCULATED_PARTIAL", html)



if __name__ == "__main__":
    unittest.main()
