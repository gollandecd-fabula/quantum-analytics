from __future__ import annotations

import unittest

from quantum.finance import (
    FinanceError,
    canonical_hash,
    evaluate_expression,
    evaluate_resolved_rule,
    resolve_rule,
    validate_rounding_policy,
)

from tests.b1b_helpers import context, policy, rule_document, typed


class B1bSecondReviewRegressionTests(unittest.TestCase):
    def test_schema_bound_rounding_scales_reject_29(self) -> None:
        for field in (
            "calculation_scale",
            "money_scale",
            "rate_scale",
            "presentation_scale",
        ):
            with self.subTest(field=field):
                document = policy()
                document[field] = 29
                document["content_hash"] = canonical_hash(
                    document, exclude=frozenset({"content_hash"})
                )
                with self.assertRaisesRegex(FinanceError, "ROUNDING_SCALE_INVALID"):
                    validate_rounding_policy(document)

    def test_nonvalid_dependency_does_not_hide_invalid_multiplier_signature(self) -> None:
        expression = {
            "kind": "OPERATION",
            "operator": "MULTIPLY",
            "value_type": "MONEY",
            "currency": "EUR",
            "unit": "MONEY",
            "arguments": [
                {
                    "kind": "VARIABLE",
                    "name": "gross_sales_amount",
                    "value_type": "MONEY",
                    "currency": "EUR",
                    "unit": "MONEY",
                },
                {
                    "kind": "VARIABLE",
                    "name": "item_factor",
                    "value_type": "DECIMAL",
                    "currency": None,
                    "unit": "ITEM",
                },
            ],
        }
        variables = {
            "gross_sales_amount": typed(
                "100", value_type="MONEY", unit="MONEY", currency="EUR"
            ),
            "item_factor": typed(
                None,
                value_type="DECIMAL",
                unit="ITEM",
                state="UNAVAILABLE",
                reason_code="FACTOR_SOURCE_MISSING",
            ),
        }
        with self.assertRaisesRegex(FinanceError, "EXPRESSION_UNIT_MISMATCH"):
            evaluate_expression(
                expression,
                variables,
                ["gross_sales_amount", "item_factor"],
                policy(),
            )

    def test_integer_division_returns_typed_finance_error(self) -> None:
        expression = {
            "kind": "OPERATION",
            "operator": "DIVIDE",
            "value_type": "DECIMAL",
            "currency": None,
            "unit": "DIMENSIONLESS",
            "arguments": [
                {
                    "kind": "LITERAL",
                    "value": "8",
                    "value_type": "INTEGER",
                    "currency": None,
                    "unit": "ITEM",
                },
                {
                    "kind": "LITERAL",
                    "value": "2",
                    "value_type": "INTEGER",
                    "currency": None,
                    "unit": "ITEM",
                },
            ],
        }
        with self.assertRaisesRegex(FinanceError, "EXPRESSION_TYPE_MISMATCH"):
            evaluate_expression(expression, {}, [], policy())

    def test_valid_resolution_rejects_non_null_diagnostic(self) -> None:
        rule = rule_document()
        resolution = resolve_rule([rule], context())
        resolution["diagnostic_code"] = "RULE_REQUIRED_MISSING"
        resolution["trace_id"] = canonical_hash(
            resolution, exclude=frozenset({"trace_id"})
        )
        with self.assertRaisesRegex(FinanceError, "RULE_RESOLUTION_INVALID"):
            evaluate_resolved_rule(resolution, [rule], {}, policy())

    def test_forged_valid_resolution_cannot_select_draft_rule(self) -> None:
        rule = rule_document(status="DRAFT")
        resolution = resolve_rule([rule], context())
        resolution["state"] = "VALID"
        resolution["diagnostic_code"] = None
        resolution["candidates"][0]["eligible"] = True
        resolution["candidates"][0]["selected"] = True
        resolution["candidates"][0]["exclusion_reasons"] = []
        resolution["trace_id"] = canonical_hash(
            resolution, exclude=frozenset({"trace_id"})
        )
        with self.assertRaisesRegex(FinanceError, "RULE_NOT_APPROVED"):
            evaluate_resolved_rule(resolution, [rule], {}, policy())

    def test_safe_expression_result_must_match_rule_signature(self) -> None:
        expression = {
            "kind": "LITERAL",
            "value": "0.10",
            "value_type": "RATE",
            "currency": None,
            "unit": "RATE",
        }
        rule = rule_document(method="SAFE_EXPRESSION", expression=expression)
        resolution = resolve_rule([rule], context())
        variables = {
            "gross_sales_amount": typed(
                "100", value_type="MONEY", unit="MONEY", currency="EUR"
            ),
            "tax_rate": typed("0.10", value_type="RATE", unit="RATE"),
        }
        with self.assertRaisesRegex(
            FinanceError, "RULE_EXPRESSION_SIGNATURE_MISMATCH"
        ):
            evaluate_resolved_rule(resolution, [rule], variables, policy())

    def test_safe_expression_missing_dependency_remains_unavailable(self) -> None:
        expression = {
            "kind": "VARIABLE",
            "name": "gross_sales_amount",
            "value_type": "MONEY",
            "currency": "EUR",
            "unit": "MONEY",
        }
        rule = rule_document(method="SAFE_EXPRESSION", expression=expression)
        resolution = resolve_rule([rule], context())
        variables = {
            "gross_sales_amount": typed(
                "100", value_type="MONEY", unit="MONEY", currency="EUR"
            )
        }
        result = evaluate_resolved_rule(resolution, [rule], variables, policy())
        self.assertEqual(result["state"], "UNAVAILABLE")
        self.assertEqual(
            result["reason_code"], "RULE_DEPENDENCY_UNAVAILABLE:tax_rate"
        )


if __name__ == "__main__":
    unittest.main()
