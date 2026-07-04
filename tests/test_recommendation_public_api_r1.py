import copy
import unittest

from quantum.recommendations import (
    RecommendationError,
    build_blocked_recommendation_bundle,
    build_recommendation_bundle,
    validate_recommendation_bundle,
)
from tests.test_recommendation_engine_r1 import detailed_analysis, policy


class RecommendationPublicApiTests(unittest.TestCase):
    def test_ready_bundle_is_built_and_validated(self):
        bundle = build_recommendation_bundle(detailed_analysis(), policy())
        validate_recommendation_bundle(bundle)
        self.assertEqual(bundle["status"], "READY")
        self.assertGreater(bundle["recommendation_count"], 0)

    def test_blocked_bundle_is_built_and_validated(self):
        bundle = build_blocked_recommendation_bundle(
            source_type="WB_SUPPLIER_GOODS",
            reason_code="RECOMMENDATION_POLICY_REQUIRED",
        )
        validate_recommendation_bundle(bundle)
        self.assertEqual(bundle["status"], "BLOCKED")
        self.assertEqual(bundle["recommendation_count"], 0)

    def test_bundle_hash_tampering_is_blocked(self):
        bundle = build_recommendation_bundle(detailed_analysis(), policy())
        changed = copy.deepcopy(bundle)
        changed["recommendation_count"] += 1
        with self.assertRaises(RecommendationError) as error:
            validate_recommendation_bundle(changed)
        self.assertEqual(
            error.exception.code,
            "RECOMMENDATION_BUNDLE_COUNT_INVALID",
        )


if __name__ == "__main__":
    unittest.main()
