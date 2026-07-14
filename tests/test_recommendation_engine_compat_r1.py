import unittest

from quantum.insights import build_recommendations
from tests.test_recommendation_engine_r1 import policy, supplier_analysis


class RecommendationEngineCompatibilityTests(unittest.TestCase):
    def test_supplier_single_blocker_is_normalized(self):
        result = build_recommendations(supplier_analysis(), policy())
        actions = [item["action_code"] for item in result["recommendations"]]
        self.assertIn("COMPLETE_REQUIRED_INPUTS", actions)
        item = next(
            recommendation
            for recommendation in result["recommendations"]
            if recommendation["action_code"] == "COMPLETE_REQUIRED_INPUTS"
        )
        self.assertIn(
            "EVENT_LEVEL_FINANCIAL_SOURCE_REQUIRED_FOR_KERNEL",
            item["limitations"],
        )


if __name__ == "__main__":
    unittest.main()
