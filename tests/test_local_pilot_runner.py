import json
import tempfile
import unittest
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path

from quantum.pilot import LocalPilotError, run_local_pilot
from tests.p16_fixtures import build_xlsx, policy
from tests.test_b1b_rescue_input_boundaries import request


def control_totals_sha256(expected_metrics):
    payload = json.dumps(
        expected_metrics,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(payload).hexdigest()


class LocalPilotRunnerTests(unittest.TestCase):
    def config(self):
        tenant_id = "tenant-local-pilot"
        finance_request = request()
        finance_request["organization_id"] = tenant_id
        return {
            "tenant_id": tenant_id,
            "account_id": "operator-local",
            "verifier_account_id": "verifier-local",
            "source_internal_id": "wb-report-2026-07",
            "marketplace": "WILDBERRIES",
            "report_type": "SALES_REPORT",
            "reporting_period_start": "2026-07-01",
            "reporting_period_end": "2026-07-02",
            "timezone": "Europe/Moscow",
            "expected_row_count": 1,
            "control_totals_sha256": None,
            "data_categories": ["FINANCIAL", "SALES"],
            "owner_authority_reference": "OWNER-LOCAL-PILOT-1",
            "lawful_authority_attested": True,
            "retention_deadline": "2030-01-01T00:00:00Z",
            "inspection_policy": json.loads(json.dumps(asdict(policy()))),
            "malware_scan_evidence_sha256": "a" * 64,
            "attestations": {
                "source_authority_verified": True,
                "report_period_verified": True,
                "control_totals_verified": True,
                "direct_identifiers_absent_or_approved": True,
                "malware_scan_clean": True,
            },
            "finance_request": finance_request,
        }

    def expected_metrics(self):
        return {
            "net_sold_units": "1",
            "product_cost_amount": "0.00",
            "other_expense_amount": "0.00",
            "tax_amount": "0.00",
            "net_marketplace_income_amount": "1000.00",
            "net_profit_amount": "1000.00",
            "profit_per_sold_unit": "1000.00",
        }

    def bind_reconciliation(self, config, expected_metrics):
        config["reconciliation"] = {"expected_metrics": expected_metrics}
        config["control_totals_sha256"] = control_totals_sha256(
            expected_metrics
        )

    def run_candidate(self, config):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "report.xlsx"
            source.write_bytes(build_xlsx())
            return run_local_pilot(
                file_path=source,
                config=config,
                storage_root=root / "storage",
            )

    def test_admitted_calculation_without_expected_totals_is_pending(self):
        report = self.run_candidate(self.config())
        self.assertEqual(report["status"], "CALCULATED_RECONCILIATION_PENDING")
        self.assertEqual(report["admission_state"], "ADMITTED")
        self.assertEqual(report["storage_zone_state"], "ADMITTED")
        self.assertEqual(report["blocked_metrics"], [])
        self.assertFalse(report["raw_rows_in_report"])
        self.assertFalse(report["marketplace_write_enabled"])
        self.assertEqual(report["reconciliation"]["state"], "PENDING")

    def test_payload_is_promoted_out_of_quarantine(self):
        config = self.config()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            storage_root = root / "storage"
            source = root / "report.xlsx"
            payload = build_xlsx()
            source.write_bytes(payload)
            report = run_local_pilot(
                file_path=source,
                config=config,
                storage_root=storage_root,
            )
            tenant_token = sha256(config["tenant_id"].encode("utf-8")).hexdigest()
            zone_root = storage_root / "pilot-zones" / tenant_token
            admitted = (
                zone_root
                / "admitted"
                / report["dataset_id"]
                / report["file_sha256"]
            )
            quarantined = (
                zone_root
                / "quarantine"
                / report["dataset_id"]
                / report["file_sha256"]
            )
            self.assertEqual(admitted.read_bytes(), payload)
            self.assertFalse(quarantined.exists())

    def test_matching_expected_metrics_completes_run(self):
        config = self.config()
        expected = self.expected_metrics()
        self.bind_reconciliation(config, expected)
        report = self.run_candidate(config)
        self.assertEqual(report["status"], "PILOT_RUN_COMPLETE")
        self.assertEqual(report["reconciliation"]["state"], "RECONCILED")
        self.assertTrue(report["reconciliation"]["control_totals_bound"])

    def test_matching_expected_metrics_without_hash_remain_pending(self):
        config = self.config()
        config["reconciliation"] = {
            "expected_metrics": self.expected_metrics()
        }
        report = self.run_candidate(config)
        self.assertEqual(report["status"], "CALCULATED_RECONCILIATION_PENDING")
        self.assertEqual(report["reconciliation"]["state"], "PENDING")
        self.assertEqual(
            report["reconciliation"]["reason_code"],
            "CONTROL_TOTALS_HASH_REQUIRED",
        )

    def test_partial_matching_expected_metrics_fail_closed(self):
        config = self.config()
        expected = {"net_profit_amount": "1000.00"}
        self.bind_reconciliation(config, expected)
        report = self.run_candidate(config)
        self.assertEqual(report["status"], "RECONCILIATION_CONFLICT")
        self.assertEqual(report["reconciliation"]["state"], "CONFLICT")
        self.assertEqual(
            report["reconciliation"]["reason_code"],
            "RECONCILIATION_METRIC_SET_MISMATCH",
        )

    def test_reconciliation_difference_fails_closed(self):
        config = self.config()
        expected = self.expected_metrics()
        expected["net_profit_amount"] = "999.00"
        self.bind_reconciliation(config, expected)
        report = self.run_candidate(config)
        self.assertEqual(report["status"], "RECONCILIATION_CONFLICT")
        self.assertEqual(report["reconciliation"]["state"], "CONFLICT")
        self.assertEqual(
            report["reconciliation"]["differences"][0]["metric_id"],
            "net_profit_amount",
        )

    def test_tampered_control_totals_hash_fails_closed(self):
        config = self.config()
        config["reconciliation"] = {
            "expected_metrics": self.expected_metrics()
        }
        config["control_totals_sha256"] = "0" * 64
        report = self.run_candidate(config)
        self.assertEqual(report["status"], "RECONCILIATION_CONFLICT")
        self.assertEqual(
            report["reconciliation"]["reason_code"],
            "CONTROL_TOTALS_HASH_MISMATCH",
        )

    def test_independent_verifier_is_required(self):
        config = self.config()
        config["verifier_account_id"] = config["account_id"]
        with self.assertRaises(LocalPilotError) as error:
            self.run_candidate(config)
        self.assertEqual(
            error.exception.code,
            "LOCAL_PILOT_INDEPENDENT_VERIFIER_REQUIRED",
        )

    def test_finance_request_must_match_tenant(self):
        config = self.config()
        config["finance_request"]["organization_id"] = "different-tenant"
        with self.assertRaises(LocalPilotError) as error:
            self.run_candidate(config)
        self.assertEqual(
            error.exception.code,
            "LOCAL_PILOT_FINANCE_TENANT_MISMATCH",
        )


if __name__ == "__main__":
    unittest.main()
