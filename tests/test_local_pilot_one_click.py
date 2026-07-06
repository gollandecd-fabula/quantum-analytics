from __future__ import annotations

import http.client
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

from quantum.api.local_pilot import calculate_unit, upload_local_file
from quantum.api.local_pilot_server import LocalPilotHandler


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
        self.assertEqual(first["data_status"], "QUARANTINED")

    def test_http_smoke_upload_and_calculate(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), LocalPilotHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        try:
            conn = http.client.HTTPConnection(host, port, timeout=5)
            conn.request("GET", "/api/local-pilot/health")
            health = conn.getresponse()
            self.assertEqual(health.status, 200)
            self.assertFalse(json.loads(health.read())["marketplace_write_enabled"])

            conn.request("POST", "/api/local-pilot/upload?filename=wb.csv", body=b"a,b\n1,2\n")
            uploaded = conn.getresponse()
            self.assertEqual(uploaded.status, 201)
            self.assertEqual(json.loads(uploaded.read())["status"], "accepted")

            body = json.dumps(self.calculation_payload()).encode("utf-8")
            conn.request("POST", "/api/local-pilot/calculate", body=body, headers={"Content-Type": "application/json"})
            calculated = conn.getresponse()
            self.assertEqual(calculated.status, 200)
            self.assertEqual(json.loads(calculated.read())["net_profit"], "335.00")
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
