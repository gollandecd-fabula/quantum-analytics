from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from quantum.finance import (
    FinanceError,
    canonical_hash,
    evaluate_expression,
    resolve_rule,
)

from tests.b1b_helpers import context, policy, rule_document


class B1bRuleAdmissionValidationTests(unittest.TestCase):
    def test_malformed_rate_payload_is_rejected_before_resolution(self) -> None:
        rule = rule_document(method="RATE", rate="not-a-decimal")
        with self.assertRaisesRegex(FinanceError, "RULE_RATE_INVALID"):
            resolve_rule([rule], context())

    def test_malformed_safe_expression_is_rejected_before_resolution(self) -> None:
        for expression, code in (
            ({}, "EXPRESSION_SCHEMA_INVALID"),
            (
                {
                    "kind": "OPERATION",
                    "operator": "SYSTEM_CALL",
                    "value_type": "MONEY",
                    "currency": "EUR",
                    "unit": "MONEY",
                    "arguments": [],
                },
                "EXPRESSION_OPERATOR_FORBIDDEN",
            ),
        ):
            with self.subTest(code=code):
                rule = rule_document(
                    method="SAFE_EXPRESSION",
                    expression=expression,
                )
                with self.assertRaisesRegex(FinanceError, code):
                    resolve_rule([rule], context())

    def test_expression_argument_limit_matches_public_schema(self) -> None:
        literal = {
            "kind": "LITERAL",
            "value": "1",
            "value_type": "DECIMAL",
            "currency": None,
            "unit": "DIMENSIONLESS",
        }
        expression = {
            "kind": "OPERATION",
            "operator": "ADD",
            "value_type": "DECIMAL",
            "currency": None,
            "unit": "DIMENSIONLESS",
            "arguments": [dict(literal) for _ in range(17)],
        }
        with self.assertRaisesRegex(FinanceError, "EXPRESSION_LIMIT_EXCEEDED"):
            evaluate_expression(expression, {}, [], policy())

        rule = rule_document(
            method="SAFE_EXPRESSION",
            expression=expression,
        )
        with self.assertRaisesRegex(FinanceError, "EXPRESSION_LIMIT_EXCEEDED"):
            resolve_rule([rule], context())

    def test_safe_expression_schema_matches_runtime_identifier_and_unit_contract(self) -> None:
        schema_path = (
            Path(__file__).resolve().parents[1]
            / "schemas/safe-expression.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        variable_pattern = schema["$defs"]["variable"]["properties"]["name"]["pattern"]
        self.assertIsNotNone(re.fullmatch(variable_pattern, "metric:actual"))
        for node_kind in ("literal", "variable", "operation"):
            with self.subTest(node_kind=node_kind):
                self.assertEqual(
                    schema["$defs"][node_kind]["properties"]["unit"]["type"],
                    "string",
                )

        expression = {
            "kind": "VARIABLE",
            "name": "metric:actual",
            "value_type": "MONEY",
            "currency": "EUR",
            "unit": "MONEY",
        }
        rule = rule_document(
            method="SAFE_EXPRESSION",
            expression=expression,
        )
        rule["dependencies"] = ["metric:actual"]
        rule["content_hash"] = canonical_hash(
            rule, exclude=frozenset({"content_hash"})
        )
        resolution = resolve_rule([rule], context())
        self.assertEqual(resolution["state"], "VALID")


if __name__ == "__main__":
    unittest.main()
