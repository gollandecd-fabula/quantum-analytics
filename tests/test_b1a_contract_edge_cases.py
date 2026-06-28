import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


class B1aContractEdgeCaseTests(unittest.TestCase):
    def test_metric_schema_represents_money_per_item(self) -> None:
        schema = load_json("schemas/metric-definition.schema.json")
        catalogue = (ROOT / "docs/finance/METRIC_CATALOGUE.md").read_text(encoding="utf-8")

        self.assertIn("MONEY_PER_ITEM", schema["properties"]["unit"]["enum"])
        self.assertIn("| `profit_per_sold_unit` | SETTLEMENT | MONEY / ITEM |", catalogue)

    def test_all_calculation_profile_versions_require_complete_references(self) -> None:
        schema = load_json("schemas/calculation-profile.schema.json")
        contract = (ROOT / "docs/finance/CALCULATION_PROFILE_CONTRACT.md").read_text(encoding="utf-8")
        required = set(schema["required"])

        self.assertTrue(
            {
                "rule_refs",
                "metric_definition_refs",
                "rounding_policy_ref",
                "source_authority_ref",
                "resolver_contract_version",
                "safe_expression_contract_version",
                "accounting_view_vocabulary_version",
            }.issubset(required)
        )
        self.assertIn("including `DRAFT` and `SHADOW`, is a complete", contract)
        self.assertIn("unfinished references is not a Calculation Profile", contract)
        self.assertNotIn("with incomplete references", contract)

    def test_comparison_operations_return_boolean(self) -> None:
        schema = load_json("schemas/safe-expression.schema.json")
        operation = schema["$defs"]["operation"]
        comparisons = {
            "EQUAL",
            "LESS_THAN",
            "LESS_OR_EQUAL",
            "GREATER_THAN",
            "GREATER_OR_EQUAL",
        }
        comparison_matches = []
        unary_matches = []
        for branch in operation["allOf"]:
            operator_rule = branch["if"].get("properties", {}).get("operator", {})
            operators = set(operator_rule.get("enum", []))
            if operators == comparisons:
                comparison_matches.append(branch)
            if operators == {"NEGATE", "ABS"}:
                unary_matches.append(branch)

        self.assertEqual(len(comparison_matches), 1)
        comparison_result = comparison_matches[0]["then"]["properties"]
        self.assertEqual(comparison_result["value_type"], {"const": "BOOLEAN"})
        self.assertEqual(comparison_result["currency"], {"type": "null"})
        self.assertEqual(comparison_result["unit"], {"const": "BOOLEAN"})

        numeric_types = ["MONEY", "DECIMAL", "RATE", "INTEGER"]
        self.assertEqual(len(unary_matches), 1)
        unary_result = unary_matches[0]["then"]["properties"]
        self.assertEqual(unary_result["value_type"], {"enum": numeric_types})
        unary_arguments = unary_result["arguments"]
        self.assertEqual(unary_arguments["minItems"], 1)
        self.assertEqual(unary_arguments["maxItems"], 1)
        operand_type = unary_arguments["items"]["allOf"][1]
        self.assertEqual(
            operand_type["properties"]["value_type"],
            {"enum": numeric_types},
        )
        self.assertEqual(operand_type["required"], ["value_type"])


if __name__ == "__main__":
    unittest.main()
