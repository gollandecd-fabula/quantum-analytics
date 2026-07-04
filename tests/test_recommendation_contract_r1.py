import copy
import unittest
from pathlib import Path
from unittest.mock import patch

from quantum.insights import build_recommendations
from quantum.pilot.windows_source_bridge import attach_reviewed_source_bridge
from tests.test_recommendation_engine_r1 import (
    detailed_analysis,
    policy,
    supplier_analysis,
)
from tests.test_windows_recommendation_attachment_r1 import limits, supplier_result


def calculation(*, net_profit="-500.00", net_units="10", profit_per_unit="-50.00"):
    return {
        "results": {
            "net_profit_amount": {"state": "VALID", "value": net_profit},
            "net_sold_units": {"state": "VALID", "value": net_units},
            "profit_per_sold_unit": {
                "state": "VALID",
                "value": profit_per_unit,
            },
        }
    }


class RecommendationContractTests(unittest.TestCase):
    def test_source_rule_contains_complete_user_contract(self):
        analysis = supplier_analysis()
        analysis.update(
            {
                "source_id": "dataset:one",
                "source_sha256": "a" * 64,
                "canonical_rows_sha256": "b" * 64,
            }
        )
        result = build_recommendations(
            analysis,
            policy(),
            scope={"marketplace": "WILDBERRIES"},
        )
        item = next(
            row
            for row in result["recommendations"]
            if row["action_code"] == "INVESTIGATE_LOW_BUYOUT"
        )
        self.assertTrue(item["action"])
        self.assertTrue(item["reason"])
        self.assertIn("forecast_effect_min", item)
        self.assertIn("forecast_effect_max", item)
        self.assertEqual(item["confidence_level"], "HIGH")
        self.assertEqual(item["priority_dimension"], "SUSTAINABLE_GROWTH")
        self.assertEqual(item["scope"]["marketplace"], "WILDBERRIES")
        self.assertIn("source-sha256:" + "a" * 64, item["evidence_refs"])
        self.assertIn("rows-sha256:" + "b" * 64, item["evidence_refs"])
        self.assertEqual(
            result["priority_order"],
            ["PROFIT", "SUSTAINABLE_GROWTH", "TURNOVER"],
        )

    def test_negative_profit_generates_exact_break_even_requirement(self):
        analysis = detailed_analysis()
        analysis.update(
            {
                "source_id": "dataset:financial",
                "source_sha256": "c" * 64,
                "canonical_ledger_sha256": "d" * 64,
            }
        )
        result = build_recommendations(
            analysis,
            policy(),
            calculation=calculation(),
            reconciliation={"state": "RECONCILED", "differences": []},
        )
        item = next(
            row
            for row in result["recommendations"]
            if row["action_code"] == "RESTORE_BREAK_EVEN"
        )
        self.assertEqual(item["severity"], "CRITICAL")
        self.assertEqual(item["current_effect"]["amount"], "-500.00")
        self.assertEqual(item["forecast_effect_min"]["value"], "500.00")
        self.assertEqual(item["forecast_effect_max"]["value"], "500.00")
        self.assertEqual(
            item["parameters"]["required_uplift_per_sold_unit"],
            "50.00",
        )
        self.assertEqual(item["confidence_level"], "HIGH")
        self.assertEqual(item["priority_dimension"], "PROFIT")

    def test_reconciliation_conflict_suppresses_break_even_action(self):
        result = build_recommendations(
            detailed_analysis(),
            policy(),
            calculation=calculation(),
            reconciliation={
                "state": "CONFLICT",
                "differences": [{"metric_id": "net_profit_amount"}],
            },
        )
        actions = {row["action_code"] for row in result["recommendations"]}
        self.assertIn("RESOLVE_RECONCILIATION_CONFLICT", actions)
        self.assertNotIn("RESTORE_BREAK_EVEN", actions)

    def test_old_two_argument_call_remains_deterministic(self):
        first = build_recommendations(supplier_analysis(), policy())
        second = build_recommendations(
            copy.deepcopy(supplier_analysis()),
            copy.deepcopy(policy()),
        )
        self.assertEqual(first, second)
        self.assertEqual(len(first["bundle_hash"]), 64)

    def test_windows_bridge_attaches_same_bundle_to_top_level_report(self):
        report = {
            "dataset_id": "dataset-1",
            "storage_zone_state": "ADMITTED",
        }
        bridged = supplier_result()
        bridged["source_id"] = "dataset:dataset-1"
        bridged["source_sha256"] = "e" * 64
        with patch(
            "quantum.pilot.windows_source_bridge.bridge_reviewed_wb_source",
            return_value=bridged,
        ):
            result = attach_reviewed_source_bridge(
                report=report,
                payload=b"payload",
                schema_discovery={"headers": ["A"]},
                limits=limits(),
                config={
                    "recommendation_policy": policy(),
                    "tenant_id": "tenant-one",
                    "marketplace": "WILDBERRIES",
                    "source_internal_id": "source-one",
                },
                source_path=Path("supplier-goods.xlsx"),
            )
        self.assertIs(report["recommendations"], result["recommendations"])
        self.assertEqual(
            report["recommendations"]["priority_order"],
            ["PROFIT", "SUSTAINABLE_GROWTH", "TURNOVER"],
        )


if __name__ == "__main__":
    unittest.main()
