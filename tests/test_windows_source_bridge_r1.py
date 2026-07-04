import unittest
from pathlib import Path
from unittest.mock import patch

from quantum.ingestion import XlsxInspectionLimits
from quantum.pilot.windows_source_bridge import (
    attach_reviewed_source_bridge,
    build_source_context,
)


def limits():
    return XlsxInspectionLimits(
        max_file_bytes=10_000,
        max_archive_entries=20,
        max_total_uncompressed_bytes=20_000,
        max_entry_uncompressed_bytes=10_000,
        max_compression_ratio=100,
        max_xml_bytes=10_000,
        max_rows=1_000,
        max_columns=100,
    )


class WindowsSourceBridgeTests(unittest.TestCase):
    def test_filename_and_reviewed_config_build_source_context(self):
        context = build_source_context(
            {
                "reporting_period_start": "2026-04-27",
                "reporting_period_end": "2026-05-03",
                "source_currency": "rub",
            },
            Path("Еженедельный отчёт №706623362.xlsx"),
        )
        self.assertEqual(
            context,
            {
                "report_id": "706623362",
                "date_from": "2026-04-27",
                "date_to": "2026-05-03",
                "currency": "RUB",
            },
        )

    def test_explicit_report_id_overrides_filename(self):
        context = build_source_context(
            {"report_id": 123456789},
            Path("report-999999999.xlsx"),
        )
        self.assertEqual(context, {"report_id": "123456789"})

    def test_not_admitted_source_is_not_dispatched(self):
        with patch(
            "quantum.pilot.windows_source_bridge.bridge_reviewed_wb_source"
        ) as dispatcher:
            result = attach_reviewed_source_bridge(
                report={
                    "dataset_id": "dataset-1",
                    "storage_zone_state": "QUARANTINED",
                },
                payload=b"payload",
                schema_discovery={"headers": ["A"]},
                limits=limits(),
                config={},
                source_path=Path("report.xlsx"),
            )
        dispatcher.assert_not_called()
        self.assertEqual(result["status"], "SOURCE_BRIDGE_SKIPPED")
        self.assertEqual(
            result["finance_request_reason_codes"],
            ["SOURCE_NOT_ADMITTED"],
        )

    def test_admitted_source_is_dispatched_with_dataset_scope(self):
        dispatch_result = {
            "status": "SOURCE_BRIDGE_UNSUPPORTED",
            "finance_request": None,
            "finance_request_state": "BLOCKED",
            "finance_request_reason_codes": ["WB_SCHEMA_NOT_MAPPED"],
            "raw_rows_in_report": False,
        }
        with patch(
            "quantum.pilot.windows_source_bridge.bridge_reviewed_wb_source",
            return_value=dispatch_result,
        ) as dispatcher:
            result = attach_reviewed_source_bridge(
                report={
                    "dataset_id": "dataset-1",
                    "storage_zone_state": "ADMITTED",
                },
                payload=b"payload",
                schema_discovery={"headers": ["A"]},
                limits=limits(),
                config={"source_currency": "RUB"},
                source_path=Path("report-706623362.xlsx"),
            )
        dispatcher.assert_called_once()
        call = dispatcher.call_args.kwargs
        self.assertEqual(call["source_id"], "dataset:dataset-1")
        self.assertEqual(call["source_context"]["report_id"], "706623362")
        self.assertEqual(call["source_context"]["currency"], "RUB")
        self.assertEqual(
            result["windows_integration_schema_version"],
            "quantum-windows-source-bridge-v1",
        )

    def test_unexpected_bridge_error_is_isolated_from_admission(self):
        with patch(
            "quantum.pilot.windows_source_bridge.bridge_reviewed_wb_source",
            side_effect=RuntimeError("sensitive detail"),
        ):
            result = attach_reviewed_source_bridge(
                report={
                    "dataset_id": "dataset-1",
                    "storage_zone_state": "ADMITTED",
                },
                payload=b"payload",
                schema_discovery={"headers": ["A"]},
                limits=limits(),
                config={},
                source_path=Path("report.xlsx"),
            )
        self.assertEqual(result["status"], "SOURCE_BRIDGE_ERROR")
        self.assertEqual(result["detail"], "RuntimeError")
        self.assertNotIn("sensitive detail", str(result))
        self.assertEqual(result["finance_request_state"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
