import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class B1aRoundingMappingTests(unittest.TestCase):
    def test_rounding_points_have_one_unambiguous_v1_mapping(self) -> None:
        schema = json.loads(
            (ROOT / "schemas/rounding-policy.schema.json").read_text(encoding="utf-8")
        )
        policy = (ROOT / "docs/finance/ROUNDING_POLICY.md").read_text(encoding="utf-8")
        properties = schema["properties"]

        self.assertIn("RULE_INPUT_NORMALIZATION", properties["calculation_mode"]["description"])
        self.assertIn("RULE_COMPONENT_RESULT", properties["calculation_mode"]["description"])
        self.assertIn("METRIC_FINAL_ACCOUNTING", properties["calculation_mode"]["description"])
        self.assertIn("REPORT_PRESENTATION", properties["presentation_mode"]["description"])
        self.assertIn("EXPORT_PRESENTATION", properties["presentation_mode"]["description"])
        self.assertIn("Array order has no semantic effect", properties["application_points"]["description"])

        self.assertIn("Different modes for individual application points", policy)
        self.assertIn("are not representable and are therefore forbidden in v1", policy)
        self.assertIn("RULE_INPUT_NORMALIZATION` | `calculation_mode`", policy)
        self.assertIn("REPORT_PRESENTATION` | `presentation_mode`", policy)
        self.assertIn("ROUNDING_POINT_MAPPING_VIOLATION", policy)


if __name__ == "__main__":
    unittest.main()
