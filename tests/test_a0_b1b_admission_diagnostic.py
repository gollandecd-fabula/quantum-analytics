from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from quantum.finance import FinanceError, evaluate_expression, resolve_rule
from tests.b1b_helpers import context, policy, rule_document


class A0B1bAdmissionDiagnosticTests(unittest.TestCase):
    def test_01_schema_pattern_and_units(self) -> None:
        schema = json.loads(
            (Path(__file__).resolve().parents[1] / "schemas/safe-expression.schema.json")
            .read_text(encoding="utf-8")
        )
        pattern = schema["$defs"]["variable"]["properties"]["name"]["pattern"]
        self.assertIsNotNone(re.fullmatch(pattern, "metric:actual"))
        for node_kind in ("literal", "variable", "operation"):
            self.assertEqual(
                schema["$defs"][node_kind]["properties"]["unit"]["type"],
                "string",
            )

    def test_02_colon_dependency_resolves(self) -> None:
        rule = rule_document(
            method="SAFE_EXPRESSION",
            expression={
                "kind": "VARIABLE",
                "name": "metric:actual",
                "value_type": "MONEY",
                "currency": "EUR",
                "unit": "MONEY",
            },
            dependencies=("metric:actual",),
        )
        try:
            resolution = resolve_rule([rule], context())
        except Exception as exc:
            print(
                "COLON_DEPENDENCY_EXCEPTION="
                f"{type(exc).__name__}:{getattr(exc, 'code', repr(exc))}",
                flush=True,
            )
            raise
        self.assertEqual(resolution["state"], "VALID")

    def test_03_malformed_payloads_reject(self) -> None:
        with self.assertRaisesRegex(FinanceError, "RULE_RATE_INVALID"):
            resolve_rule(
                [rule_document(method="RATE", rate="not-a-decimal")],
                context(),
            )
        with self.assertRaisesRegex(FinanceError, "EXPRESSION_SCHEMA_INVALID"):
            resolve_rule(
                [rule_document(method="SAFE_EXPRESSION", expression={})],
                context(),
            )

    def test_04_argument_limit_rejects(self) -> None:
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
        with self.assertRaisesRegex(FinanceError, "EXPRESSION_LIMIT_EXCEEDED"):
            resolve_rule(
                [rule_document(method="SAFE_EXPRESSION", expression=expression)],
                context(),
            )


if __name__ == "__main__":
    unittest.main()
