from __future__ import annotations

import copy
import unittest

from quantum.finance import (
    FinanceError,
    evaluate_expression,
    evaluate_resolved_rule,
    resolve_rule,
)

from tests.b1b_helpers import context, policy, rule_document, typed


class B1bRuleResolutionTests(unittest.TestCase):
    def test_product_scope_beats_account_scope(self) -> None:
        account_rule = rule_document(
            rule_id="cost.account",
            scope={
                "organization_id": "org-synthetic",
                "marketplace_account_id": "acct-1",
            },
        )
        product_rule = rule_document(
            rule_id="cost.product",
            scope={
                "organization_id": "org-synthetic",
                "product_id": "product-1",
            },
        )
        result = resolve_rule(
            [account_rule, product_rule],
            context(marketplace_account_id="acct-1", product_id="product-1"),
        )
        selected = [c for c in result["candidates"] if c["selected"]]
        self.assertEqual(result["state"], "VALID")
        self.assertEqual(selected[0]["rule"]["rule_id"], "cost.product")

    def test_priority_breaks_equal_specificity(self) -> None:
        low = rule_document(rule_id="cost.low", priority=1)
        high = rule_document(rule_id="cost.high", priority=2)
        result = resolve_rule([low, high], context())
        selected = [c for c in result["candidates"] if c["selected"]]
        self.assertEqual(selected[0]["rule"]["rule_id"], "cost.high")

    def test_later_validity_breaks_equal_priority(self) -> None:
        old = rule_document(rule_id="cost.old", valid_from="2026-01-01T00:00:00Z")
        new = rule_document(rule_id="cost.new", valid_from="2026-06-01T00:00:00Z")
        result = resolve_rule([old, new], context())
        selected = [c for c in result["candidates"] if c["selected"]]
        self.assertEqual(selected[0]["rule"]["rule_id"], "cost.new")

    def test_version_breaks_equal_validity(self) -> None:
        v1 = rule_document(rule_id="cost.versioned", version=1)
        v2 = rule_document(rule_id="cost.versioned", version=2)
        result = resolve_rule([v1, v2], context())
        selected = [c for c in result["candidates"] if c["selected"]]
        self.assertEqual(selected[0]["rule"]["version"], 2)

    def test_complete_tie_returns_conflict(self) -> None:
        a = rule_document(rule_id="cost.a")
        b = rule_document(rule_id="cost.b")
        result = resolve_rule([a, b], context())
        self.assertEqual(result["state"], "CONFLICT")
        self.assertEqual(result["diagnostic_code"], "RULE_RESOLUTION_TIE")
        self.assertFalse(any(c["selected"] for c in result["candidates"]))

    def test_exclusivity_overlap_cannot_be_resolved_by_priority(self) -> None:
        a = rule_document(
            rule_id="cost.a", priority=1, exclusivity_group="cost-exclusive"
        )
        b = rule_document(
            rule_id="cost.b", priority=99, exclusivity_group="cost-exclusive"
        )
        result = resolve_rule([a, b], context())
        self.assertEqual(result["state"], "CONFLICT")
        self.assertEqual(result["diagnostic_code"], "RULE_EXCLUSIVITY_OVERLAP")

    def test_draft_only_candidates_return_not_approved(self) -> None:
        draft = rule_document(status="DRAFT")
        result = resolve_rule([draft], context())
        self.assertEqual(result["state"], "BLOCKED")
        self.assertEqual(result["diagnostic_code"], "RULE_NOT_APPROVED")

    def test_actual_ignores_scenario_rule(self) -> None:
        actual = rule_document(rule_id="cost.actual")
        scenario = rule_document(
            rule_id="cost.scenario",
            scope={"organization_id": "org-synthetic", "scenario_id": "scenario-1"},
        )
        result = resolve_rule([scenario, actual], context())
        selected = [c for c in result["candidates"] if c["selected"]]
        self.assertEqual(selected[0]["rule"]["rule_id"], "cost.actual")

    def test_scenario_override_beats_inherited_actual(self) -> None:
        actual = rule_document(rule_id="cost.actual")
        scenario = rule_document(
            rule_id="cost.scenario",
            scope={"organization_id": "org-synthetic", "scenario_id": "scenario-1"},
        )
        result = resolve_rule(
            [actual, scenario],
            context(
                mode="SCENARIO",
                scenario_id="scenario-1",
                calculation_profile_id="profile-scenario",
            ),
        )
        selected = [c for c in result["candidates"] if c["selected"]]
        self.assertEqual(selected[0]["rule"]["rule_id"], "cost.scenario")

    def test_cross_organization_rule_is_excluded(self) -> None:
        rule = rule_document(scope={"organization_id": "other-org"})
        result = resolve_rule([rule], context())
        self.assertEqual(result["state"], "BLOCKED")
        self.assertIn(
            "ORGANIZATION_MISMATCH",
            result["candidates"][0]["exclusion_reasons"],
        )

    def test_candidate_order_is_stable_across_input_order(self) -> None:
        a = rule_document(rule_id="cost.a", priority=1)
        b = rule_document(rule_id="cost.b", priority=2)
        first = resolve_rule([a, b], context())
        second = resolve_rule([b, a], context())
        self.assertEqual(first, second)

    def test_fixed_rule_evaluation(self) -> None:
        rule = rule_document(value="40.125")
        resolution = resolve_rule([rule], context())
        result = evaluate_resolved_rule(resolution, [rule], {}, policy())
        self.assertEqual(result["state"], "VALID")
        self.assertEqual(result["value"], "40.125000")
        self.assertEqual(result["unit"], "MONEY_PER_ITEM")

    def test_rate_rule_evaluation_returns_rate_not_amount(self) -> None:
        rule = rule_document(method="RATE", rate="0.075")
        resolution = resolve_rule([rule], context())
        variables = {
            "gross_sales_amount": typed(
                "1000", value_type="MONEY", unit="MONEY", currency="EUR"
            )
        }
        result = evaluate_resolved_rule(
            resolution, [rule], variables, policy()
        )
        self.assertEqual(result["state"], "VALID")
        self.assertEqual(result["value_type"], "RATE")
        self.assertEqual(result["value"], "0.075000")

    def test_missing_rate_dependency_is_unavailable(self) -> None:
        rule = rule_document(method="RATE")
        resolution = resolve_rule([rule], context())
        result = evaluate_resolved_rule(resolution, [rule], {}, policy())
        self.assertEqual(result["state"], "UNAVAILABLE")

    def test_rule_hash_tampering_rejected(self) -> None:
        rule = rule_document()
        rule["value"] = "999"
        with self.assertRaisesRegex(FinanceError, "RULE_HASH_MISMATCH"):
            resolve_rule([rule], context())

    def test_resolution_is_not_allowed_to_duplicate_selection_authority(self) -> None:
        rule = rule_document()
        resolution = resolve_rule([rule], context())
        resolution["selected_rule"] = resolution["candidates"][0]["rule"]
        with self.assertRaisesRegex(FinanceError, "RULE_RESOLUTION_INVALID"):
            evaluate_resolved_rule(resolution, [rule], {}, policy())


class B1bSafeExpressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = policy()
        self.money = typed(
            "100.00", value_type="MONEY", unit="MONEY", currency="EUR"
        )
        self.rate = typed("0.10", value_type="RATE", unit="RATE")

    def multiply_expression(self) -> dict:
        return {
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
                    "name": "tax_rate",
                    "value_type": "RATE",
                    "currency": None,
                    "unit": "RATE",
                },
            ],
        }

    def test_money_times_rate(self) -> None:
        result = evaluate_expression(
            self.multiply_expression(),
            {"gross_sales_amount": self.money, "tax_rate": self.rate},
            ["gross_sales_amount", "tax_rate"],
            self.policy,
        )
        self.assertEqual(result["state"], "VALID")
        self.assertEqual(result["value"], "10.000000")

    def test_unknown_operator_rejected(self) -> None:
        expression = self.multiply_expression()
        expression["operator"] = "PYTHON_EVAL"
        with self.assertRaisesRegex(FinanceError, "EXPRESSION_OPERATOR_FORBIDDEN"):
            evaluate_expression(
                expression,
                {"gross_sales_amount": self.money, "tax_rate": self.rate},
                ["gross_sales_amount", "tax_rate"],
                self.policy,
            )

    def test_undeclared_variable_rejected(self) -> None:
        with self.assertRaisesRegex(FinanceError, "EXPRESSION_DEPENDENCY_UNDECLARED"):
            evaluate_expression(
                self.multiply_expression(),
                {"gross_sales_amount": self.money, "tax_rate": self.rate},
                ["gross_sales_amount"],
                self.policy,
            )

    def test_currency_mismatch_rejected(self) -> None:
        expression = self.multiply_expression()
        variables = {
            "gross_sales_amount": typed(
                "100", value_type="MONEY", unit="MONEY", currency="RUB"
            ),
            "tax_rate": self.rate,
        }
        with self.assertRaisesRegex(FinanceError, "EXPRESSION_CURRENCY_MISMATCH"):
            evaluate_expression(
                expression,
                variables,
                ["gross_sales_amount", "tax_rate"],
                self.policy,
            )

    def test_division_by_zero_is_blocked(self) -> None:
        expression = {
            "kind": "OPERATION",
            "operator": "DIVIDE",
            "value_type": "DECIMAL",
            "currency": None,
            "unit": "DIMENSIONLESS",
            "arguments": [
                {
                    "kind": "LITERAL",
                    "value": "1",
                    "value_type": "DECIMAL",
                    "currency": None,
                    "unit": "DIMENSIONLESS",
                },
                {
                    "kind": "LITERAL",
                    "value": "0",
                    "value_type": "DECIMAL",
                    "currency": None,
                    "unit": "DIMENSIONLESS",
                },
            ],
        }
        result = evaluate_expression(expression, {}, [], self.policy)
        self.assertEqual(result["state"], "BLOCKED")
        self.assertEqual(result["reason_code"], "EXPRESSION_DIVISION_BY_ZERO")

    def test_typed_state_propagation_does_not_coerce_to_zero(self) -> None:
        variables = {
            "gross_sales_amount": typed(
                None,
                value_type="MONEY",
                unit="MONEY",
                currency="EUR",
                state="UNAVAILABLE",
                reason_code="SOURCE_MISSING",
            ),
            "tax_rate": self.rate,
        }
        result = evaluate_expression(
            self.multiply_expression(),
            variables,
            ["gross_sales_amount", "tax_rate"],
            self.policy,
        )
        self.assertEqual(result["state"], "UNAVAILABLE")
        self.assertIsNone(result["value"])

    def test_valid_zero_participates_normally(self) -> None:
        variables = {
            "gross_sales_amount": typed(
                "0", value_type="MONEY", unit="MONEY", currency="EUR"
            ),
            "tax_rate": self.rate,
        }
        result = evaluate_expression(
            self.multiply_expression(),
            variables,
            ["gross_sales_amount", "tax_rate"],
            self.policy,
        )
        self.assertEqual(result["state"], "VALID")
        self.assertEqual(result["value"], "0.000000")

    def test_if_requires_boolean_condition(self) -> None:
        expression = {
            "kind": "OPERATION",
            "operator": "IF",
            "value_type": "DECIMAL",
            "currency": None,
            "unit": "DIMENSIONLESS",
            "arguments": [
                {
                    "kind": "LITERAL",
                    "value": "1",
                    "value_type": "DECIMAL",
                    "currency": None,
                    "unit": "DIMENSIONLESS",
                },
                {
                    "kind": "LITERAL",
                    "value": "1",
                    "value_type": "DECIMAL",
                    "currency": None,
                    "unit": "DIMENSIONLESS",
                },
                {
                    "kind": "LITERAL",
                    "value": "2",
                    "value_type": "DECIMAL",
                    "currency": None,
                    "unit": "DIMENSIONLESS",
                },
            ],
        }
        with self.assertRaisesRegex(FinanceError, "EXPRESSION_TYPE_MISMATCH"):
            evaluate_expression(expression, {}, [], self.policy)

    def test_expression_limit_is_enforced(self) -> None:
        expression = {
            "kind": "OPERATION",
            "operator": "ADD",
            "value_type": "DECIMAL",
            "currency": None,
            "unit": "DIMENSIONLESS",
            "arguments": [
                {
                    "kind": "LITERAL",
                    "value": "1",
                    "value_type": "DECIMAL",
                    "currency": None,
                    "unit": "DIMENSIONLESS",
                }
                for _ in range(33)
            ],
        }
        with self.assertRaisesRegex(FinanceError, "EXPRESSION_LIMIT_EXCEEDED"):
            evaluate_expression(expression, {}, [], self.policy)


if __name__ == "__main__":
    unittest.main()
