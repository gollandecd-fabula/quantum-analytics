import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"
FINANCE = ROOT / "docs" / "finance"


def load_schema(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


class B1aReviewRegressionTests(unittest.TestCase):
    def test_metric_states_match_canonical_typed_value_contract(self) -> None:
        canonical = load_schema("typed-value.schema.json")["properties"]["state"]["enum"]
        metric_states = load_schema("metric-definition.schema.json")["properties"]["typed_states"]

        self.assertEqual(set(metric_states["items"]["enum"]), set(canonical))
        self.assertEqual(metric_states["minItems"], len(canonical))
        self.assertEqual(metric_states["maxItems"], len(canonical))
        self.assertNotIn("ZERO_VALID", metric_states["items"]["enum"])
        self.assertIn("INVALID", metric_states["items"]["enum"])
        self.assertIn("NOT_APPLICABLE", metric_states["items"]["enum"])

    def test_calculation_profile_refs_require_positive_integer_versions(self) -> None:
        version_schema = load_schema("calculation-profile.schema.json")["$defs"]["versionedRef"]["properties"]["version"]

        self.assertEqual(version_schema, {"type": "integer", "minimum": 1})
        self.assertNotIn("string", json.dumps(version_schema))

    def test_calculation_profile_reference_keys_match_contract(self) -> None:
        reference = load_schema("calculation-profile.schema.json")["$defs"]["versionedRef"]
        contract = (FINANCE / "CALCULATION_PROFILE_CONTRACT.md").read_text(encoding="utf-8")

        self.assertEqual(reference["required"], ["id", "version", "content_hash"])
        self.assertEqual(set(reference["properties"]), {"id", "version", "content_hash"})
        self.assertIn('"id": "stable-domain-identifier"', contract)
        self.assertIn("common key `id`", contract)
        self.assertIn("`rule_id`, `metric_id`, or `policy_id` are not valid", contract)
        self.assertIn("sorted by `id`, then positive integer `version`", contract)

    def test_eligible_candidates_require_reproducible_ordering_tuples(self) -> None:
        schema = load_schema("rule-resolution-result.schema.json")
        candidate = schema["properties"]["candidates"]["items"]
        condition = candidate["allOf"][0]
        contract = (FINANCE / "RULE_RESOLUTION_CONTRACT.md").read_text(encoding="utf-8")

        self.assertEqual(
            condition["if"],
            {
                "properties": {"eligible": {"const": True}},
                "required": ["eligible"],
            },
        )
        self.assertEqual(condition["then"]["properties"]["ordering_tuple"]["type"], "array")
        self.assertEqual(condition["then"]["properties"]["exclusion_reasons"]["maxItems"], 0)
        self.assertEqual(condition["else"]["properties"]["ordering_tuple"]["type"], "null")
        self.assertEqual(condition["else"]["properties"]["exclusion_reasons"]["minItems"], 1)
        self.assertIn("eligible candidate always records its complete ordering tuple", contract)
        self.assertIn("ineligible candidate records at least one exclusion reason", contract)


if __name__ == "__main__":
    unittest.main()
