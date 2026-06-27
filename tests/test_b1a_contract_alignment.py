from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


class B1aContractAlignmentTests(unittest.TestCase):
    def test_rule_method_payload_is_present_only_for_selected_method(self) -> None:
        schema = load_json(ROOT / "schemas/configuration-rule.schema.json")
        properties = schema["properties"]

        self.assertEqual(properties["value"]["type"], "string")
        self.assertEqual(properties["rate"]["type"], "string")
        self.assertEqual(properties["expression"]["$ref"], "safe-expression.schema.json")

        expected = {
            "FIXED_VALUE": ({"value"}, {"rate", "expression"}),
            "RATE": ({"rate"}, {"value", "expression"}),
            "SAFE_EXPRESSION": ({"expression"}, {"value", "rate"}),
        }
        observed: dict[str, tuple[set[str], set[str]]] = {}

        for branch in schema["allOf"][:3]:
            condition = branch["if"]["properties"]["method"]
            method = condition.get("const")
            if method is None:
                continue
            then = branch["then"]
            required = set(then["required"])
            forbidden: set[str] = set()
            for clause in then["not"]["anyOf"]:
                forbidden.update(set(clause.get("required", [])) & {"value", "rate", "expression"})
            observed[method] = (required, forbidden)

        self.assertEqual(observed, expected)

    def test_safe_expression_schema_enforces_operator_arities(self) -> None:
        schema = load_json(ROOT / "schemas/safe-expression.schema.json")
        branches = schema["$defs"]["operation"]["allOf"]
        arities: dict[str, tuple[int, int]] = {}

        for branch in branches:
            operator_rule = branch["if"]["properties"]["operator"]
            operators = operator_rule.get("enum") or [operator_rule["const"]]
            arguments = branch["then"]["properties"]["arguments"]
            for operator in operators:
                arities[operator] = (arguments["minItems"], arguments["maxItems"])

        self.assertEqual(arities["NEGATE"], (1, 1))
        self.assertEqual(arities["ABS"], (1, 1))
        self.assertEqual(arities["MULTIPLY"], (2, 2))
        self.assertEqual(arities["DIVIDE"], (2, 2))
        self.assertEqual(arities["IF"], (3, 3))
        self.assertEqual(arities["ADD"], (2, 16))
        self.assertEqual(arities["MIN"], (2, 16))
        self.assertEqual(arities["MAX"], (2, 16))

    def test_safe_expression_literals_are_bound_to_declared_types(self) -> None:
        schema = load_json(ROOT / "schemas/safe-expression.schema.json")
        literal = schema["$defs"]["literal"]
        branches = literal["allOf"]

        self.assertIn("integerString", schema["$defs"])
        self.assertEqual(schema["$defs"]["integerString"]["pattern"], "^-?(0|[1-9][0-9]*)$")
        self.assertEqual(
            literal["properties"]["value"]["oneOf"],
            [{"$ref": "#/$defs/decimalString"}, {"type": "boolean"}],
        )

        value_rules: dict[str, dict[str, Any]] = {}
        currency_rule: dict[str, Any] | None = None
        for branch in branches:
            value_type_rule = branch["if"]["properties"]["value_type"]
            labels = value_type_rule.get("enum") or [value_type_rule["const"]]
            then_properties = branch["then"]["properties"]
            if "value" in then_properties:
                for label in labels:
                    value_rules[label] = then_properties["value"]
            if labels == ["MONEY"] and "currency" in then_properties:
                currency_rule = branch

        self.assertEqual(value_rules["MONEY"]["$ref"], "#/$defs/decimalString")
        self.assertEqual(value_rules["DECIMAL"]["$ref"], "#/$defs/decimalString")
        self.assertEqual(value_rules["RATE"]["$ref"], "#/$defs/decimalString")
        self.assertEqual(value_rules["INTEGER"]["$ref"], "#/$defs/integerString")
        self.assertEqual(value_rules["BOOLEAN"]["type"], "boolean")
        self.assertIsNotNone(currency_rule)
        self.assertEqual(currency_rule["then"]["properties"]["currency"]["type"], "string")
        self.assertEqual(currency_rule["else"]["properties"]["currency"]["type"], "null")

    def test_metric_catalogue_has_explicit_purchase_flow_contracts(self) -> None:
        catalogue = (ROOT / "docs/finance/METRIC_CATALOGUE.md").read_text(encoding="utf-8")

        self.assertIn("| `purchased_units` | OPERATIONAL | INTEGER / ITEM |", catalogue)
        self.assertIn("| `purchase_amount` | OPERATIONAL | MONEY |", catalogue)
        self.assertIn("purchases are a separate inventory flow", catalogue)
        self.assertIn("cannot be inferred from orders, sales, inventory changes, payout", catalogue)
        self.assertIn("is not automatically included in `product_cost_amount`", catalogue)

    def test_financial_contract_docs_match_machine_readable_contracts(self) -> None:
        configuration = (ROOT / "docs/finance/CONFIGURATION_RULE_CONTRACT.md").read_text(encoding="utf-8")
        expression = (ROOT / "docs/finance/SAFE_EXPRESSION_CONTRACT.md").read_text(encoding="utf-8")

        self.assertIn("versioned lexicographic vector", configuration)
        self.assertIn("product_id,", configuration)
        self.assertIn("Priority is considered", configuration)
        self.assertIn("unused\npayload properties are omitted", configuration)

        self.assertIn('"kind": "LITERAL"', expression)
        self.assertIn('"currency": null', expression)
        self.assertIn('"unit": "DIMENSIONLESS"', expression)
        self.assertIn('"value": true', expression)
        self.assertIn('"value_type": "INTEGER"', expression)
        self.assertIn("machine-readable schema enforces these arities", expression)


if __name__ == "__main__":
    unittest.main()
