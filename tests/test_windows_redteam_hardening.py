import base64
import json
import sys
import tempfile
import unittest
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from unittest import mock

from quantum.pilot import LocalPilotError, run_local_pilot
from quantum.pilot.windows_runner import discover_schema, main
from tests import test_xlsx_real_office_compat
from tests.p16_fixtures import build_xlsx, policy
from tests.test_b1b_rescue_input_boundaries import request


class DiscoveryRedTeamTests(unittest.TestCase):
    def test_keyword_header_beats_wide_decorative_title_row(self):
        workbook = build_xlsx(
            headers=tuple(f"Title {index}" for index in range(1, 13)),
            rows=(
                ("Артикул", "Количество продаж", "Сумма продаж"),
                ("SKU-1", "1", "100.00"),
            ),
        )
        candidate = discover_schema(
            payload=workbook,
            limits=policy().limits,
        )
        self.assertEqual(candidate.header_row_index, 2)
        self.assertEqual(candidate.column_count, 3)
        self.assertEqual(candidate.headers[0], "Артикул")

    def test_discover_only_emits_reviewable_hash_bound_preview(self):
        workbook = build_xlsx(
            headers=("Артикул", "Количество продаж", "Сумма продаж"),
        )
        config = {
            "inspection_policy": json.loads(json.dumps(asdict(policy()))),
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "report.xlsx"
            source.write_bytes(workbook)
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            output = root / "preview.json"
            argv = [
                "windows_runner",
                "--file",
                str(source),
                "--config",
                str(config_path),
                "--storage-root",
                str(root / "storage"),
                "--output",
                str(output),
                "--home-local",
                "--discover-only",
                "--authority-attested",
            ]
            with mock.patch.object(sys, "argv", argv), mock.patch(
                "quantum.pilot.windows_runner._engine.run_local_pilot"
            ) as run_pilot:
                self.assertEqual(main(), 0)
                run_pilot.assert_not_called()
            preview = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(preview["status"], "SCHEMA_DISCOVERED")
            self.assertEqual(preview["file_sha256"], sha256(workbook).hexdigest())
            self.assertEqual(preview["schema_discovery"]["header_row_index"], 1)
            self.assertEqual(preview["schema_discovery"]["headers"][0], "Артикул")


class WindowsPowerShellCompatibilityTests(unittest.TestCase):
    def test_configurator_is_ascii_safe_and_matches_limit_contract(self):
        repository_root = Path(__file__).resolve().parents[1]
        payload = (
            repository_root / "scripts" / "windows" / "configure_home_local.ps1"
        ).read_bytes()
        script = payload.decode("ascii")
        self.assertFalse(payload.startswith(b"\xef\xbb\xbf"))

        limits_block = script.split("limits = [ordered]@{", 1)[1].split(
            "schemas = @(", 1
        )[0]
        required_limit_keys = {
            "max_file_bytes",
            "max_archive_entries",
            "max_total_uncompressed_bytes",
            "max_entry_uncompressed_bytes",
            "max_compression_ratio",
            "max_xml_bytes",
            "max_rows",
            "max_columns",
        }
        obsolete_limit_keys = {
            "max_package_entries",
            "max_package_uncompressed_bytes",
            "max_single_part_bytes",
            "max_xml_nodes_per_part",
            "max_sheets",
            "max_cell_text_length",
            "max_shared_strings",
            "max_shared_string_characters",
        }
        for key in required_limit_keys:
            self.assertIn(key, limits_block)
        for key in obsolete_limit_keys:
            self.assertNotIn(key, limits_block)

        encoded_tokens = {
            "электронная почта": "0Y3Qu9C10LrRgtGA0L7QvdC90LDRjyDQv9C+0YfRgtCw",
            "телефон": "0YLQtdC70LXRhNC+0L0=",
            "адрес": "0LDQtNGA0LXRgQ==",
            "фио": "0YTQuNC+",
            "фамилия": "0YTQsNC80LjQu9C40Y8=",
            "паспорт": "0L/QsNGB0L/QvtGA0YI=",
            "снилс": "0YHQvdC40LvRgQ==",
            "инн": "0LjQvdC9",
        }
        for expected, encoded in encoded_tokens.items():
            self.assertIn(encoded, script)
            self.assertEqual(base64.b64decode(encoded).decode("utf-8"), expected)

    def test_importer_consumes_schema_discovery_preview_contract(self):
        repository_root = Path(__file__).resolve().parents[1]
        importer = (
            repository_root / "scripts" / "windows" / "import_source.ps1"
        ).read_text(encoding="utf-8")
        producer = (
            repository_root / "src" / "quantum" / "pilot" / "windows_runner.py"
        ).read_text(encoding="utf-8")

        self.assertIn('"schema_discovery": candidate.report()', producer)
        self.assertIn(
            '$preview.PSObject.Properties["schema_discovery"]',
            importer,
        )
        self.assertIn(
            'throw "Schema preview does not contain schema_discovery."',
            importer,
        )
        self.assertNotIn("$preview.schema.", importer)

    def test_real_office_namespace_regression_suite(self):
        suite = unittest.defaultTestLoader.loadTestsFromModule(
            test_xlsx_real_office_compat
        )
        result = unittest.TestResult()
        suite.run(result)
        self.assertGreaterEqual(result.testsRun, 6)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.failures, [])


class AdmissionOnlyRedTeamTests(unittest.TestCase):
    def config(self):
        tenant_id = "tenant-admission-only"
        return {
            "execution_mode": "ADMISSION_ONLY",
            "tenant_id": tenant_id,
            "account_id": "operator-local",
            "verifier_account_id": "verifier-local",
            "source_internal_id": "wb-report-admission-only",
            "marketplace": "WILDBERRIES",
            "report_type": "SALES_REPORT",
            "reporting_period_start": "2026-07-01",
            "reporting_period_end": "2026-07-02",
            "timezone": "Europe/Moscow",
            "expected_row_count": 1,
            "control_totals_sha256": None,
            "data_categories": ["FINANCIAL", "SALES"],
            "owner_authority_reference": "OWNER-ADMISSION-ONLY",
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
            "finance_request": None,
            "reconciliation": None,
        }

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

    def test_admission_only_is_successful_without_finance_request(self):
        report = self.run_candidate(self.config())
        self.assertEqual(report["status"], "ADMISSION_COMPLETE")
        self.assertEqual(report["admission_state"], "ADMITTED")
        self.assertIsNone(report["calculation"])
        self.assertEqual(report["reconciliation"]["state"], "NOT_REQUESTED")
        self.assertIn("FINANCE_CONFIGURATION_REQUIRED", report["limitations"])
        self.assertFalse(report["marketplace_write_enabled"])
        self.assertFalse(report["raw_rows_in_report"])

    def test_unknown_execution_mode_fails_closed(self):
        config = self.config()
        config["execution_mode"] = "UNSAFE"
        with self.assertRaises(LocalPilotError) as error:
            self.run_candidate(config)
        self.assertEqual(
            error.exception.code,
            "LOCAL_PILOT_EXECUTION_MODE_INVALID",
        )

    def test_full_mode_still_requires_finance_request(self):
        config = self.config()
        config["execution_mode"] = "FULL"
        config["finance_request"] = request()
        config["finance_request"]["organization_id"] = config["tenant_id"]
        report = self.run_candidate(config)
        self.assertEqual(report["status"], "CALCULATED_RECONCILIATION_PENDING")


if __name__ == "__main__":
    unittest.main()
