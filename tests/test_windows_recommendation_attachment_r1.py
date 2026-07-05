import unittest
from pathlib import Path
from unittest.mock import patch

from quantum.ingestion import XlsxInspectionLimits
from quantum.pilot.windows_source_bridge import attach_reviewed_source_bridge
from tests.test_recommendation_engine_r1 import policy


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
        "status": "SOURCE_BRIDGE_COMPLETE",
        "source_type": "WB_SUPPLIER_GOODS",
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
        "raw_rows_in_report": False,
    }


class WindowsRecommendationAttachmentTests(unittest.TestCase):
    def _attach(self, config):
        with patch(
            "quantum.pilot.windows_source_bridge.bridge_reviewed_wb_source",
            return_value=supplier_result(),
        ):
            return attach_reviewed_source_bridge(
                report={
                    "dataset_id": "dataset-1",
                    "storage_zone_state": "ADMITTED",
                },
                payload=b"payload",
                schema_discovery={"headers": ["A"]},
                limits=limits(),
                config=config,
                source_path=Path("supplier-goods.xlsx"),
            )

    def test_missing_policy_attaches_blocked_bundle(self):
        result = self._attach({})
        recommendations = result["recommendations"]
        self.assertEqual(recommendations["status"], "BLOCKED")
        self.assertEqual(
            recommendations["reason_codes"],
            ["RECOMMENDATION_POLICY_REQUIRED"],
        )
        self.assertEqual(result["status"], "SOURCE_BRIDGE_COMPLETE")

    def test_valid_policy_attaches_ready_recommendations(self):
        result = self._attach({"recommendation_policy": policy()})
        recommendations = result["recommendations"]
        self.assertEqual(recommendations["status"], "READY")
        actions = [
            item["action_code"]
            for item in recommendations["recommendations"]
        ]
        self.assertIn("COMPLETE_REQUIRED_INPUTS", actions)
        self.assertIn("INVESTIGATE_LOW_BUYOUT", actions)

    def test_malformed_policy_does_not_damage_source_bridge(self):
        result = self._attach({"recommendation_policy": {"bad": "policy"}})
        self.assertEqual(result["status"], "SOURCE_BRIDGE_COMPLETE")
        self.assertEqual(result["recommendations"]["status"], "ERROR")
        self.assertEqual(
            result["recommendations"]["reason_codes"],
            ["RECOMMENDATION_POLICY_FIELDS_INVALID"],
        )


if __name__ == "__main__":
    unittest.main()
