import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from quantum.ingestion import XlsxInspectionLimits
from quantum.pilot.windows_source_bridge import attach_reviewed_source_bridge
from tests.test_recommendation_engine_r1 import policy


SOURCE_SHA = "a" * 64


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


def supplier_result():
    return {
        "schema_version": "quantum-wb-source-bridge-v1",
        "status": "SOURCE_BRIDGE_COMPLETE",
        "source_type": "WB_SUPPLIER_GOODS",
        "source_sha256": SOURCE_SHA,
        "observed_metrics": {
            "ordered_units": {
                "state": "VALID",
                "value": "100",
                "value_type": "INTEGER",
                "unit": "ITEM",
                "authority": "SOURCE",
            },
            "bought_units": {
                "state": "VALID",
                "value": "40",
                "value_type": "INTEGER",
                "unit": "ITEM",
                "authority": "SOURCE",
            },
            "current_stock_units": {
                "state": "VALID",
                "value": "200",
                "value_type": "INTEGER",
                "unit": "ITEM",
                "authority": "SOURCE",
            },
        },
        "finance_request": None,
        "finance_request_state": "BLOCKED",
        "finance_request_reason_code": (
            "EVENT_LEVEL_FINANCIAL_SOURCE_REQUIRED_FOR_KERNEL"
        ),
        "limitations": ["AGGREGATED_SOURCE_NOT_EVENT_LEDGER"],
        "raw_rows_in_report": False,
    }


def admitted_report():
    return {
        "dataset_id": "dataset-output-1",
        "status": "ADMISSION_COMPLETE",
        "storage_zone_state": "ADMITTED",
        "file_sha256": SOURCE_SHA,
        "limitations": ["PILOT_READY_NOT_ASSERTED"],
    }


class WindowsOutputAttachmentTests(unittest.TestCase):
    def _attach(self, config):
        with patch(
            "quantum.pilot.windows_source_bridge.bridge_reviewed_wb_source",
            return_value=supplier_result(),
        ):
            return attach_reviewed_source_bridge(
                report=admitted_report(),
                payload=b"payload",
                schema_discovery={"headers": ["A"]},
                limits=limits(),
                config=config,
                source_path=Path("supplier-goods.xlsx"),
            )

    def test_default_localappdata_output_is_created_automatically(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"LOCALAPPDATA": directory}, clear=False):
                result = self._attach({"recommendation_policy": policy()})
            output = result["output_bundle"]
            self.assertEqual(output["status"], "OUTPUT_BUNDLE_COMPLETE")
            self.assertEqual(len(output["artifacts"]), 5)
            root = Path(directory) / "QuantumLocalProduction" / "output"
            for artifact in output["artifacts"]:
                path = Path(artifact["path"])
                self.assertTrue(path.is_file())
                self.assertTrue(path.is_relative_to(root))

    def test_explicit_absolute_output_root_is_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self._attach(
                {
                    "recommendation_policy": policy(),
                    "local_output_root": directory,
                }
            )
            self.assertEqual(
                result["output_bundle"]["status"],
                "OUTPUT_BUNDLE_COMPLETE",
            )
            self.assertTrue(
                Path(result["output_bundle"]["directory"]).is_relative_to(
                    Path(directory)
                )
            )

    def test_relative_output_root_is_blocked_without_damaging_analysis(self):
        result = self._attach(
            {
                "recommendation_policy": policy(),
                "local_output_root": "relative-output",
            }
        )
        self.assertEqual(result["status"], "SOURCE_BRIDGE_COMPLETE")
        self.assertEqual(result["output_bundle"]["status"], "OUTPUT_BUNDLE_ERROR")
        self.assertEqual(
            result["output_bundle"]["reason_code"],
            "WINDOWS_LOCAL_OUTPUT_ROOT_MUST_BE_ABSOLUTE",
        )

    def test_output_writer_failure_is_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch(
                "quantum.pilot.windows_source_bridge.attach_local_output_bundle",
                side_effect=RuntimeError("sensitive detail"),
            ):
                result = self._attach(
                    {
                        "recommendation_policy": policy(),
                        "local_output_root": directory,
                    }
                )
        self.assertEqual(result["status"], "SOURCE_BRIDGE_COMPLETE")
        self.assertEqual(result["output_bundle"]["status"], "OUTPUT_BUNDLE_ERROR")
        self.assertEqual(result["output_bundle"]["detail"], "RuntimeError")
        self.assertNotIn("sensitive detail", str(result))


if __name__ == "__main__":
    unittest.main()
