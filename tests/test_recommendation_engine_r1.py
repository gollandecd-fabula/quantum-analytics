import copy
import unittest

from quantum.insights import (
    RecommendationError,
    build_recommendations,
    validate_recommendation_policy,
)


def policy():
    return {
        "schema_version": "quantum-recommendation-policy-v1",
        "policy_id": "laranna-operational-v1",
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


def metric(value, *, unit, currency=None):
    return {
        "state": "VALID",
        "value": str(value),
        "value_type": "MONEY" if currency else "INTEGER",
        "unit": unit,
        "currency": currency,
    }


def supplier_analysis():
    return {
        "status": "SOURCE_BRIDGE_COMPLETE",
        "source_type": "WB_SUPPLIER_GOODS",
        "observed_metrics": {
            "ordered_units": metric(100, unit="ITEM"),
            "bought_units": metric(40, unit="ITEM"),
            "current_stock_units": metric(200, unit="ITEM"),
        },
        "finance_request_state": "BLOCKED",
        "finance_request_reason_code": (
            "EVENT_LEVEL_FINANCIAL_SOURCE_REQUIRED_FOR_KERNEL"
        ),
    }


def detailed_analysis():
    return {
        "status": "SOURCE_BRIDGE_COMPLETE",
        "source_type": "WB_DETAILED_FINANCIAL",
        "observed_metrics": {
            "gross_sales_units": metric(100, unit="ITEM"),
            "returned_units": metric(45, unit="ITEM"),
            "gross_sales_amount": metric(10000, unit="MONEY", currency="RUB"),
            "marketplace_commission_amount": metric(
                2500, unit="MONEY", currency="RUB"
            ),
            "forward_logistics_amount": metric(
                1200, unit="MONEY", currency="RUB"
            ),
            "reverse_logistics_amount": metric(
                1000, unit="MONEY", currency="RUB"
            ),
            "storage_amount": metric(600, unit="MONEY", currency="RUB"),
            "fines_withholdings_amount": metric(
                100, unit="MONEY", currency="RUB"
            ),
            "payout_amount": metric(4000, unit="MONEY", currency="RUB"),
        },
        "finance_request_state": "BLOCKED",
        "finance_request_reason_codes": [
            "RETURN_TREATMENT_INPUT_REQUIRED",
            "CALCULATION_PROFILE_REQUIRED",
        ],
    }


class RecommendationEngineTests(unittest.TestCase):
    def test_policy_is_required_without_hidden_defaults(self):
        result = build_recommendations(supplier_analysis(), None)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(
            result["reason_codes"],
            ["RECOMMENDATION_POLICY_REQUIRED"],
        )
        self.assertEqual(result["recommendation_count"], 0)

    def test_policy_threshold_order_is_fail_closed(self):
        invalid = policy()
        invalid["thresholds"]["buyout_rate_critical"] = "0.90"
        with self.assertRaises(RecommendationError) as error:
            validate_recommendation_policy(invalid)
        self.assertEqual(
            error.exception.code,
            "RECOMMENDATION_BUYOUT_THRESHOLDS_INVALID",
        )

    def test_supplier_goods_generates_buyout_and_stock_recommendations(self):
        result = build_recommendations(supplier_analysis(), policy())
        self.assertEqual(result["status"], "READY")
        actions = [item["action_code"] for item in result["recommendations"]]
        self.assertIn("INVESTIGATE_LOW_BUYOUT", actions)
        self.assertIn("REVIEW_HIGH_STOCK_TO_BUYOUT_RATIO", actions)
        buyout = next(
            item
            for item in result["recommendations"]
            if item["action_code"] == "INVESTIGATE_LOW_BUYOUT"
        )
        self.assertEqual(buyout["severity"], "CRITICAL")
        self.assertEqual(buyout["parameters"]["observed_rate"], "0.4000")
        self.assertEqual(buyout["forecast_effect"]["state"], "BLOCKED")

    def test_detailed_financial_generates_bounded_cost_forecasts(self):
        result = build_recommendations(detailed_analysis(), policy())
        actions = {item["action_code"]: item for item in result["recommendations"]}
        self.assertIn("COMPLETE_REQUIRED_INPUTS", actions)
        self.assertIn("INVESTIGATE_HIGH_RETURN_RATE", actions)
        self.assertIn("REVIEW_COMMISSION_AND_PRICE_STRUCTURE", actions)
        self.assertIn("REVIEW_FORWARD_LOGISTICS_COST", actions)
        self.assertIn("REVIEW_REVERSE_LOGISTICS_COST", actions)
        self.assertIn("REVIEW_STORAGE_COST", actions)
        self.assertIn("RECONCILE_SETTLEMENT_GAP", actions)
        self.assertEqual(
            actions["REVIEW_COMMISSION_AND_PRICE_STRUCTURE"]["forecast_effect"][
                "amount_max"
            ],
            "250.00",
        )
        self.assertTrue(
            actions["REVIEW_COMMISSION_AND_PRICE_STRUCTURE"]["forecast_effect"][
                "upper_bound_not_expected_savings"
            ]
        )
        self.assertEqual(
            actions["INVESTIGATE_HIGH_RETURN_RATE"]["severity"],
            "CRITICAL",
        )

    def test_recommendations_are_deterministic(self):
        first = build_recommendations(detailed_analysis(), policy())
        second = build_recommendations(
            copy.deepcopy(detailed_analysis()),
            copy.deepcopy(policy()),
        )
        self.assertEqual(first, second)
        self.assertEqual(len(first["bundle_hash"]), 64)
        identifiers = [
            item["recommendation_id"] for item in first["recommendations"]
        ]
        self.assertEqual(len(identifiers), len(set(identifiers)))

    def test_incomplete_bridge_does_not_publish_recommendations(self):
        analysis = supplier_analysis()
        analysis["status"] = "SOURCE_BRIDGE_BLOCKED"
        result = build_recommendations(analysis, policy())
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["recommendation_count"], 0)
        self.assertEqual(result["reason_codes"], ["SOURCE_BRIDGE_NOT_COMPLETE"])

    def test_metric_missing_state_is_not_coerced_to_zero(self):
        analysis = supplier_analysis()
        analysis["observed_metrics"]["bought_units"] = {
            "state": "BLOCKED",
            "value": None,
            "value_type": "INTEGER",
            "unit": "ITEM",
            "currency": None,
            "reason_code": "SOURCE_REQUIRED",
        }
        with self.assertRaises(RecommendationError) as error:
            build_recommendations(analysis, policy())
        self.assertEqual(
            error.exception.code,
            "RECOMMENDATION_METRIC_NOT_VALID:bought_units",
        )


if __name__ == "__main__":
    unittest.main()
