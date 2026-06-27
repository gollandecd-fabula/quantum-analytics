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
        matches = []
        for branch in operation["allOf"]:
            operator_rule = branch["if"].get("properties", {}).get("operator", {})
            if set(operator_rule.get("enum", [])) == comparisons:
                matches.append(branch)

        self.assertEqual(len(matches), 1)
        result = matches[0]["then"]["properties"]
        self.assertEqual(result["value_type"], {"const": "BOOLEAN"})
        self.assertEqual(result["currency"], {"type": "null"})
        self.assertEqual(result["unit"], {"const": "BOOLEAN"})


if __name__ == "__main__":
    unittest.main()
