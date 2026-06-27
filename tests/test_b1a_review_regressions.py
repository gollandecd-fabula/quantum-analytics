import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"


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


if __name__ == "__main__":
    unittest.main()
