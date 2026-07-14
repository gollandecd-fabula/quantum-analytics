from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree
from zipfile import ZipFile

from quantum.insights import build_recommendations
from quantum.outputs import (
    EXPECTED_XLSX_SHEETS,
    OutputBundleError,
    build_local_output_bundle,
    render_dashboard_html,
    render_xlsx_report,
    validate_local_output_bundle,
    verify_local_output_directory,
    write_local_output_bundle,
)
import quantum.outputs.writer as writer_module


GENERATED_AT = "2026-07-05T00:00:00Z"
SOURCE_SHA = "a" * 64


def _metric(value, *, unit="MONEY", currency="RUB", source_ids=None):
    return {
        "state": "VALID",
        "value": str(value),
        "value_type": "MONEY" if currency else "INTEGER",
        "unit": unit,
        "currency": currency,
        "authority": "SOURCE",
        "source_ids": source_ids or ["row:1"],
    }


def _policy():
    return {
        "schema_version": "quantum-recommendation-policy-v1",
        "policy_id": "test-policy",
        "version": 1,
        "thresholds": {
            "buyout_rate_warning": "0.75",
            "buyout_rate_critical": "0.50",
            "return_rate_warning": "0.20",
            "return_rate_critical": "0.40",
            "commission_ratio_warning": "0.20",
            "logistics_ratio_warning": "0.10",
            "storage_ratio_warning": "0.05",
            "stock_to_bought_warning": "4.00",
            "reconciliation_gap_amount_warning": "50.00",
        },
        "effect_bounds": {
            "commission_cost_reduction_max": "0.10",
            "logistics_cost_reduction_max": "0.15",
            "storage_cost_reduction_max": "0.30",
            "return_related_cost_reduction_max": "0.20",
        },
    }


def report():
    analysis = {
        "schema_version": "quantum-wb-source-bridge-v1",
        "status": "SOURCE_BRIDGE_COMPLETE",
        "source_type": "WB_DETAILED_FINANCIAL",
        "source_id": "dataset:dataset-123",
        "source_sha256": SOURCE_SHA,
        "canonical_rows_sha256": "b" * 64,
        "canonical_ledger_sha256": "c" * 64,
        "raw_rows_in_report": False,
        "observed_metrics": {
            "gross_sales_units": _metric(100, unit="ITEM", currency=None),
            "returned_units": _metric(25, unit="ITEM", currency=None),
            "gross_sales_amount": _metric("10000.00"),
            "marketplace_commission_amount": _metric("2500.00"),
            "forward_logistics_amount": _metric("1200.00"),
            "reverse_logistics_amount": _metric("800.00"),
            "storage_amount": _metric("600.00"),
            "advertising_amount": _metric("300.00"),
            "fines_withholdings_amount": _metric("100.00"),
            "payout_amount": _metric("4000.00"),
            "current_stock_units": _metric(150, unit="ITEM", currency=None),
        },
        "finance_request_state": "READY",
        "finance_request_reason_codes": [],
        "limitations": ["AGGREGATE_SCOPE_ONLY"],
    }
    calculation = {
        "schema_version": "quantum-finance-kernel-v1",
        "calculation_id": "calc-1",
        "organization_id": "tenant-1",
        "mode": "ACTUAL",
        "scenario_id": None,
        "profile_ref": {
            "id": "profile-1",
            "version": 1,
            "content_hash": "d" * 64,
        },
        "rounding_policy_ref": {
            "id": "round-1",
            "version": 1,
            "content_hash": "e" * 64,
        },
        "publication_state": "PILOT",
        "calculated_at": GENERATED_AT,
        "input_hash": "f" * 64,
        "result_hash": "1" * 64,
        "limitations": ["PRODUCTION_RELEASE_BLOCKED"],
        "results": {
            "net_sold_units": _metric(75, unit="ITEM", currency=None, source_ids=[]),
            "product_cost_amount": _metric("6000.00", source_ids=[]),
            "other_expense_amount": _metric("300.00", source_ids=[]),
            "tax_amount": _metric("600.00", source_ids=[]),
            "net_marketplace_income_amount": _metric("4500.00", source_ids=[]),
            "net_profit_amount": _metric("-2400.00", source_ids=[]),
            "profit_per_sold_unit": _metric(
                "-32.00", unit="MONEY_PER_ITEM", source_ids=[]
            ),
            "profitability_of_costs": _metric(
                "-0.347826", unit="RATIO", currency=None, source_ids=[]
            ),
        },
    }
    reconciliation = {"state": "RECONCILED", "differences": []}
    recommendations = build_recommendations(
        analysis,
        _policy(),
        calculation=calculation,
        reconciliation=reconciliation,
        scope={"marketplace": "WILDBERRIES"},
    )
    analysis["recommendations"] = recommendations
    return {
        "runner_version": "LOCAL_PILOT_RUNNER_R1",
        "dataset_id": "dataset-123",
        "status": "PILOT_RUN_COMPLETE",
        "file_sha256": SOURCE_SHA,
        "source_bridge": analysis,
        "recommendations": recommendations,
        "calculation": calculation,
        "reconciliation": reconciliation,
        "blocked_metrics": [],
        "admission_state": "ADMITTED",
        "admission_diagnostics": [],
        "storage_zone_state": "ADMITTED",
        "marketplace_write_enabled": False,
        "raw_rows_in_report": False,
        "runtime_profile": "HOME_LOCAL",
        "storage_encryption_required": False,
        "policy": {
            "id": "admission-1",
            "version": 1,
            "content_hash": "2" * 64,
        },
        "inspection": {"diagnostics": [], "matched_schema_id": "WB"},
        "schema_discovery": {
            "header_sha256": "3" * 64,
            "data_row_count": 100,
        },
        "limitations": ["HOME_LOCAL_UNENCRYPTED_STORAGE"],
    }


class LocalOutputBundleTests(unittest.TestCase):
    def test_bundle_is_deterministic_complete_and_valid(self):
        first = build_local_output_bundle(report(), generated_at=GENERATED_AT)
        second = build_local_output_bundle(report(), generated_at=GENERATED_AT)
        self.assertEqual(first, second)
        validate_local_output_bundle(first)
        self.assertEqual(len(first["bundle_hash"]), 64)
        self.assertNotIn("recommendations", first["analysis"])
        self.assertEqual(first["calculation"]["calculation_id"], "calc-1")
        self.assertEqual(first["reconciliation"]["state"], "RECONCILED")
        self.assertEqual(
            first["parameters"]["calculation_profile_ref"]["id"],
            "profile-1",
        )
        self.assertEqual(
            first["provenance"]["source"]["canonical_ledger_sha256"],
            "c" * 64,
        )
        self.assertEqual(
            first["recommendations"]["recommendation_count"],
            len(first["recommendations"]["recommendations"]),
        )
        self.assertEqual(
            first["limitations"],
            [
                "HOME_LOCAL_UNENCRYPTED_STORAGE",
                "AGGREGATE_SCOPE_ONLY",
                "PRODUCTION_RELEASE_BLOCKED",
            ],
        )

    def test_missing_reconciliation_is_explicit_not_available(self):
        payload = report()
        payload.pop("reconciliation")
        bundle = build_local_output_bundle(payload, generated_at=GENERATED_AT)
        self.assertEqual(bundle["reconciliation"], {
            "state": "NOT_AVAILABLE",
            "differences": [],
        })

    def test_raw_payload_is_rejected_recursively(self):
        unsafe = report()
        unsafe["source_bridge"]["nested"] = {"raw_payload": {"secret": "value"}}
        with self.assertRaises(OutputBundleError) as error:
            build_local_output_bundle(unsafe, generated_at=GENERATED_AT)
        self.assertTrue(error.exception.code.startswith("OUTPUT_RAW_DATA_FORBIDDEN:"))

    def test_top_level_recommendation_mismatch_is_rejected(self):
        unsafe = report()
        unsafe["recommendations"] = copy.deepcopy(unsafe["recommendations"])
        unsafe["recommendations"]["bundle_hash"] = "9" * 64
        with self.assertRaises(OutputBundleError) as error:
            build_local_output_bundle(unsafe, generated_at=GENERATED_AT)
        self.assertEqual(error.exception.code, "OUTPUT_RECOMMENDATION_BUNDLE_MISMATCH")

    def test_xlsx_is_deterministic_valid_and_has_exact_sheet_contract(self):
        bundle = build_local_output_bundle(report(), generated_at=GENERATED_AT)
        first = render_xlsx_report(bundle)
        second = render_xlsx_report(bundle)
        self.assertEqual(first, second)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.xlsx"
            path.write_bytes(first)
            with ZipFile(path) as archive:
                workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
                sheets = workbook.find(
                    "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheets"
                )
                self.assertIsNotNone(sheets)
                self.assertEqual(
                    tuple(item.get("name") for item in list(sheets)),
                    EXPECTED_XLSX_SHEETS,
                )
                namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
                for name in archive.namelist():
                    if name.endswith(".xml"):
                        root = ElementTree.fromstring(archive.read(name))
                        if name.startswith("xl/worksheets/sheet"):
                            self.assertEqual(root.findall(f".//{namespace}f"), [])
                self.assertIn("xl/charts/chart1.xml", archive.namelist())
                self.assertIn("xl/drawings/drawing1.xml", archive.namelist())
                chart = ElementTree.fromstring(archive.read("xl/charts/chart1.xml"))
                chart_namespace = "{http://schemas.openxmlformats.org/drawingml/2006/chart}"
                self.assertEqual(chart.findall(f".//{chart_namespace}f"), [])
                self.assertIsNotNone(chart.find(f".//{chart_namespace}strLit"))
                self.assertIsNotNone(chart.find(f".//{chart_namespace}numLit"))
                styles = ElementTree.fromstring(archive.read("xl/styles.xml"))
                self.assertIsNotNone(styles.find(f"{namespace}numFmts"))
                self.assertIsNotNone(styles.find(f"{namespace}dxfs"))
                summary = ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
                self.assertIsNotNone(summary.find(f"{namespace}mergeCells"))
                self.assertIsNotNone(summary.find(f"{namespace}conditionalFormatting"))
                self.assertIsNotNone(summary.find(f"{namespace}hyperlinks"))
                self.assertIsNotNone(summary.find(f"{namespace}drawing"))
                recommendations = ElementTree.fromstring(archive.read("xl/worksheets/sheet2.xml"))
                self.assertIsNotNone(recommendations.find(f"{namespace}autoFilter"))
                pane = recommendations.find(f".//{namespace}pane")
                self.assertIsNotNone(pane)
                self.assertEqual(pane.get("xSplit"), "4")
                self.assertEqual(pane.get("ySplit"), "5")

    def test_dashboard_is_offline_and_bound_to_bundle(self):
        bundle = build_local_output_bundle(report(), generated_at=GENERATED_AT)
        html = render_dashboard_html(bundle).decode("utf-8")
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)
        self.assertIn('id="severity"', html)
        self.assertIn('id="priority"', html)
        self.assertIn('id="category"', html)
        self.assertIn('id="financial-chart"', html)
        self.assertIn(bundle["bundle_hash"], html)
        self.assertIn("Внешние библиотеки и сетевые запросы отсутствуют", html)

    def test_writer_is_transactional_verified_and_idempotent(self):
        bundle = build_local_output_bundle(report(), generated_at=GENERATED_AT)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = write_local_output_bundle(
                report(),
                output_root=root,
                generated_at=GENERATED_AT,
            )
            self.assertEqual(result["status"], "OUTPUT_BUNDLE_COMPLETE")
            self.assertEqual(result["artifact_count"], 5)
            target = Path(result["directory"])
            self.assertTrue(target.name.endswith(bundle["bundle_hash"][:16]))
            verified = verify_local_output_directory(target)
            self.assertEqual(verified["bundle_hash"], bundle["bundle_hash"])
            by_name = {item["name"]: item for item in result["artifacts"]}
            self.assertEqual(
                set(by_name),
                {
                    "quantum_result.json",
                    "recommendations.json",
                    "Quantum_Report.xlsx",
                    "dashboard.html",
                    "evidence_manifest.json",
                },
            )
            for item in result["artifacts"]:
                payload = Path(item["path"]).read_bytes()
                self.assertEqual(len(payload), item["size_bytes"])
                self.assertEqual(hashlib.sha256(payload).hexdigest(), item["sha256"])
            reused = write_local_output_bundle(
                report(),
                output_root=root,
                generated_at=GENERATED_AT,
            )
            self.assertEqual(reused["status"], "OUTPUT_BUNDLE_REUSED")
            self.assertEqual(reused["directory"], result["directory"])

    def test_writer_detects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            result = write_local_output_bundle(
                report(),
                output_root=Path(directory),
                generated_at=GENERATED_AT,
            )
            dashboard = Path(result["directory"]) / "dashboard.html"
            dashboard.write_bytes(dashboard.read_bytes() + b"x")
            with self.assertRaises(OutputBundleError) as error:
                verify_local_output_directory(Path(result["directory"]))
            self.assertEqual(
                error.exception.code,
                "OUTPUT_ARTIFACT_SIZE_MISMATCH:dashboard.html",
            )

    def test_writer_rolls_back_staging_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = writer_module._write_payload
            calls = {"count": 0}

            def fail_second(path, payload):
                calls["count"] += 1
                if calls["count"] == 2:
                    raise OSError("simulated")
                return original(path, payload)

            with patch.object(
                writer_module,
                "_write_payload",
                side_effect=fail_second,
            ):
                with self.assertRaises(OSError):
                    write_local_output_bundle(
                        report(),
                        output_root=root,
                        generated_at=GENERATED_AT,
                    )
            self.assertEqual(list(root.glob("quantum_*")), [])
            self.assertEqual(list(root.glob(".*.staging-*")), [])


if __name__ == "__main__":
    unittest.main()
