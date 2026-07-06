from __future__ import annotations

import http.client
import json
import os
import tempfile
import threading
import unittest
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path

from quantum.api.local_pilot import (
    analyze_uploaded_report,
    analysis_to_xlsx_bytes,
    calculate_unit,
    local_pilot_health,
    save_analysis_export,
    save_cost_table,
    upload_local_file,
)
from quantum.api.local_pilot_server import LocalPilotHandler
from scripts.build_local_pilot_package import build_package


class LocalPilotOneClickTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.old_runtime = os.environ.get("QUANTUM_RUNTIME_DIR")
        os.environ["QUANTUM_RUNTIME_DIR"] = self.tempdir.name

    def tearDown(self) -> None:
        if self.old_runtime is None:
            os.environ.pop("QUANTUM_RUNTIME_DIR", None)
        else:
            os.environ["QUANTUM_RUNTIME_DIR"] = self.old_runtime
        self.tempdir.cleanup()

    def calculation_payload(self) -> dict[str, str]:
        return {
            "sale_price": "1000.00",
            "product_cost": "400.00",
            "commission_amount": "100.00",
            "forward_logistics": "50.00",
            "reverse_logistics": "0.00",
            "paid_storage": "10.00",
            "advertising": "0.00",
            "fines": "0.00",
            "tax": "60.00",
            "software": "5.00",
            "defects": "0.00",
            "loss_damage": "0.00",
            "other_expense": "40.00",
        }

    def analysis_settings(self) -> dict[str, str]:
        return {
            "tax_rate_percent": "6",
            "other_expense": "40",
            "commission_amount": "100",
            "forward_logistics": "50",
            "reverse_logistics": "0",
            "paid_storage": "10",
            "advertising": "0",
            "fines": "0",
            "software": "5",
            "defects": "0",
            "loss_damage": "0",
        }

    def test_calculation_requires_explicit_fields(self) -> None:
        status, payload = calculate_unit({"sale_price": "1000.00"})
        self.assertEqual(status, 400)
        self.assertEqual(payload["status"], "blocked")
        self.assertTrue(payload["no_hidden_defaults"])
        self.assertIn("product_cost", payload["missing_fields"])

    def test_calculation_uses_decimal_inputs_without_defaults(self) -> None:
        status, payload = calculate_unit(self.calculation_payload())
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "calculated")
        self.assertEqual(payload["net_profit"], "335.00")
        self.assertTrue(payload["no_hidden_defaults"])
        self.assertFalse(payload["marketplace_write_enabled"])

    def test_upload_receipt_and_duplicate_detection(self) -> None:
        body = b"barcode,price\n123,1000\n"
        first_status, first = upload_local_file("wb-report.csv", body, "text/csv")
        second_status, second = upload_local_file("wb-report.csv", body, "text/csv")
        self.assertEqual(first_status, 201)
        self.assertEqual(second_status, 200)
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(first["sha256"], second["sha256"])
        self.assertEqual(first["data_status"], "UPLOADED")

    def test_wb_analysis_uses_uploaded_cost_table_dashboard_and_recommendations(self) -> None:
        cost_status, cost_payload = save_cost_table(
            "costs.csv",
            "article,product_cost\nA-1,400\nB-2,950\n".encode(),
            "text/csv",
        )
        self.assertEqual(cost_status, 201)
        self.assertEqual(cost_payload["accepted_rows"], 2)

        report = "\n".join(
            [
                "article,quantity,sale_price",
                "A-1,1,1000",
                "B-2,1,900",
            ]
        ).encode()
        upload_status, upload_payload = upload_local_file("wb.csv", report, "text/csv")
        self.assertEqual(upload_status, 201)

        status, analysis = analyze_uploaded_report(upload_payload["sha256"], self.analysis_settings())
        self.assertEqual(status, 200)
        self.assertEqual(analysis["status"], "analyzed")
        self.assertEqual(analysis["dashboard"]["rows_calculated"], 2)
        self.assertEqual(analysis["dashboard"]["rows_blocked"], 0)
        self.assertEqual(analysis["dashboard"]["negative_items"], 1)
        self.assertEqual(analysis["rows"][0]["net_profit"], "335.00")
        self.assertEqual(analysis["rows"][0]["recommendation"], "PROMOTE_CANDIDATE")
        self.assertEqual(analysis["rows"][1]["recommendation"], "STOP_LOSS_REVIEW")
        self.assertFalse(analysis["marketplace_write_enabled"])

    def test_wb_analysis_blocks_missing_required_settings(self) -> None:
        report = "article,quantity,sale_price\nA-1,1,1000\n".encode()
        _, upload_payload = upload_local_file("wb.csv", report, "text/csv")
        status, analysis = analyze_uploaded_report(upload_payload["sha256"], {})
        self.assertEqual(status, 400)
        self.assertEqual(analysis["status"], "blocked")
        self.assertEqual(analysis["reason"], "missing_required_settings")
        self.assertTrue(analysis["no_hidden_defaults"])

    def test_xlsx_export_is_real_zip_package(self) -> None:
        analysis = {
            "status": "analyzed",
            "dashboard": {"rows_calculated": 1, "net_profit": "335.00"},
            "rows": [{"article": "A-1", "quantity": "1.00", "revenue": "1000.00", "product_cost_total": "400.00", "tax": "60.00", "other_expense": "40.00", "total_expense": "665.00", "net_profit": "335.00", "recommendation": "PROMOTE_CANDIDATE"}],
        }
        data = analysis_to_xlsx_bytes(analysis)
        with zipfile.ZipFile(__import__("io").BytesIO(data)) as archive:
            names = set(archive.namelist())
        self.assertIn("xl/workbook.xml", names)
        self.assertIn("xl/worksheets/sheet1.xml", names)

        status, payload = save_analysis_export(analysis)
        self.assertEqual(status, 201)
        self.assertEqual(payload["status"], "exported")
        self.assertTrue(Path(payload["path"]).exists())

    def test_health_declares_ready_capabilities(self) -> None:
        health = local_pilot_health()
        self.assertEqual(health["status"], "READY")
        self.assertIn("dashboard", health["ready_capabilities"])
        self.assertIn("xlsx_export", health["ready_capabilities"])
        self.assertFalse(health["marketplace_write_enabled"])

    def test_http_smoke_upload_cost_table_analyze_export_and_calculate(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), LocalPilotHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        try:
            conn = http.client.HTTPConnection(host, port, timeout=5)
            conn.request("GET", "/api/local-pilot/health")
            health = conn.getresponse()
            self.assertEqual(health.status, 200)
            health_payload = json.loads(health.read())
            self.assertEqual(health_payload["status"], "READY")
            self.assertFalse(health_payload["marketplace_write_enabled"])

            conn.request("POST", "/api/local-pilot/cost-table?filename=costs.csv", body=b"article,product_cost\nA-1,400\n")
            cost_uploaded = conn.getresponse()
            self.assertEqual(cost_uploaded.status, 201)
            self.assertEqual(json.loads(cost_uploaded.read())["status"], "accepted")

            conn.request("POST", "/api/local-pilot/upload?filename=wb.csv", body=b"article,quantity,sale_price\nA-1,1,1000\n")
            uploaded = conn.getresponse()
            self.assertEqual(uploaded.status, 201)
            upload_payload = json.loads(uploaded.read())
            self.assertEqual(upload_payload["status"], "accepted")

            analyze_payload = dict(self.analysis_settings())
            analyze_payload["sha256"] = upload_payload["sha256"]
            conn.request(
                "POST",
                "/api/local-pilot/analyze",
                body=json.dumps(analyze_payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            analyzed = conn.getresponse()
            self.assertEqual(analyzed.status, 200)
            analysis = json.loads(analyzed.read())
            self.assertEqual(analysis["dashboard"]["net_profit"], "335.00")

            conn.request(
                "POST",
                "/api/local-pilot/export",
                body=json.dumps(analysis).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            exported = conn.getresponse()
            self.assertEqual(exported.status, 201)
            self.assertEqual(json.loads(exported.read())["status"], "exported")

            body = json.dumps(self.calculation_payload()).encode("utf-8")
            conn.request("POST", "/api/local-pilot/calculate", body=body, headers={"Content-Type": "application/json"})
            calculated = conn.getresponse()
            self.assertEqual(calculated.status, 200)
            self.assertEqual(json.loads(calculated.read())["net_profit"], "335.00")
        finally:
            server.shutdown()
            server.server_close()

    def test_package_builder_creates_one_click_zip(self) -> None:
        summary = build_package()
        package = Path(summary["package"])
        self.assertTrue(package.exists())
        self.assertGreater(summary["entry_count"], 0)
        with zipfile.ZipFile(package) as archive:
            names = set(archive.namelist())
        self.assertIn("scripts/Quantum_ONE_CLICK_STABLE_RELEASE.cmd", names)
        self.assertIn("scripts/Install_Quantum_WB_Release.cmd", names)
        self.assertIn("scripts/Install_Quantum_WB_Release.ps1", names)
        self.assertIn("src/quantum/api/local_pilot_server.py", names)
        self.assertIn("PACKAGE_MANIFEST.json", names)


if __name__ == "__main__":
    unittest.main()
