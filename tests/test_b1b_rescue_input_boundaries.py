import unittest
from copy import deepcopy
from decimal import Decimal

from quantum.finance import (
    FinanceError,
    calculate,
    canonical_hash,
    evaluate_resolved_rule,
    resolve_rule,
    validate_rounding_policy,
)
from quantum.finance._rounding import _input_decimal
from tests.test_b1b_rescue_smoke import context, money_rule, policy, typed


def request():
    zero_money = typed("VALID", "0", "MONEY", "MONEY", "RUB")
    zero_items = typed("VALID", "0", "INTEGER", "ITEM")
    inputs = {
        "gross_sales_units": typed("VALID", "1", "INTEGER", "ITEM"),
        "returned_units": deepcopy(zero_items),
        "resalable_returned_units": deepcopy(zero_items),
        "compensated_returned_units": deepcopy(zero_items),
        "return_compensation_amount": deepcopy(zero_money),
        "gross_sales_amount": typed(
            "VALID", "1000", "MONEY", "MONEY", "RUB"
        ),
        "discounts_amount": deepcopy(zero_money),
        "subsidies_excluding_return_compensation_amount": deepcopy(zero_money),
        "marketplace_commission_amount": deepcopy(zero_money),
        "forward_logistics_amount": deepcopy(zero_money),
        "reverse_logistics_amount": deepcopy(zero_money),
        "storage_amount": deepcopy(zero_money),
        "advertising_amount": deepcopy(zero_money),
        "fines_withholdings_amount": deepcopy(zero_money),
    }
    return {
        "calculation_id": "b",
        "organization_id": "org-1",
        "mode": "ACTUAL",
        "scenario_id": None,
        "calculated_at": "2026-07-01T00:00:00Z",
        "profile_ref": {
            "id": "p",
            "version": 1,
            "content_hash": "0" * 64,
        },
        "profile_status": "PILOT",
        "rounding_policy": policy(),
        "currency": "RUB",
        "inputs": inputs,
        "cost_per_unit": typed(
            "VALID", "0", "MONEY", "MONEY_PER_ITEM", "RUB"
        ),
        "other_expense_components": [
            {
                "component_id": "o",
                "value": typed(
                    "VALID", "0", "MONEY", "MONEY_PER_ITEM", "RUB"
                ),
            }
        ],
        "tax_rate": typed("VALID", "0", "RATE", "RATE"),
        "tax_base_metric_id": "gross_sales_amount",
    }


class B1bInputBoundaryTests(unittest.TestCase):
    def test_malformed_expense(self):
        candidate = request()
        candidate["other_expense_components"] = [{"component_id": "x"}]
        with self.assertRaises(FinanceError) as error:
            calculate(candidate)
        self.assertEqual(error.exception.code, "OTHER_EXPENSE_COMPONENTS_INVALID")

    def test_duplicate_expense(self):
        candidate = request()
        component = candidate["other_expense_components"][0]
        candidate["other_expense_components"] = [component, deepcopy(component)]
        with self.assertRaises(FinanceError) as error:
            calculate(candidate)
        self.assertEqual(error.exception.code, "OTHER_EXPENSE_COMPONENTS_INVALID")

    def test_unknown_inputs_cannot_expand_decimal_budget(self):
        candidate = request()
        for index in range(1000):
            candidate["inputs"][f"unused_{index}"] = typed(
                "VALID", "1", "MONEY", "MONEY", "RUB"
            )
        with self.assertRaises(FinanceError) as error:
            calculate(candidate)
        self.assertEqual(error.exception.code, "KERNEL_INPUTS_INVALID")

    def test_expense_components_are_bounded_before_decimal_budget(self):
        candidate = request()
        candidate["other_expense_components"] = [
            {
                "component_id": f"expense-{index}",
                "value": typed("VALID", "0", "MONEY", "MONEY", "RUB"),
            }
            for index in range(65)
        ]
        with self.assertRaises(FinanceError) as error:
            calculate(candidate)
        self.assertEqual(error.exception.code, "OTHER_EXPENSE_COMPONENTS_INVALID")

    def test_zero_is_valid(self):
        value = calculate(request())["results"]["other_expense_amount"]
        self.assertEqual((value["state"], value["value"]), ("VALID", "0.00"))

    def test_high_precision_input_uses_policy_context(self):
        rounding_policy = policy()
        rounding_policy["max_input_precision"] = 40
        rounding_policy["content_hash"] = canonical_hash(
            rounding_policy,
            exclude=frozenset({"content_hash"}),
        )
        validate_rounding_policy(rounding_policy)
        value = "12345678901234567890123456789"
        self.assertEqual(
            _input_decimal(value, rounding_policy, code="BOUNDARY"),
            Decimal(value + ".000000"),
        )

    def test_mode_isolation(self):
        candidate = request()
        candidate["scenario_id"] = "s"
        with self.assertRaises(FinanceError) as error:
            calculate(candidate)
        self.assertEqual(error.exception.code, "PROFILE_MODE_CONTAMINATION")
        candidate = request()
        candidate["mode"] = "SCENARIO"
        with self.assertRaises(FinanceError) as error:
            calculate(candidate)
        self.assertEqual(error.exception.code, "PROFILE_MODE_CONTAMINATION")

    def test_changed_ruleset_rejects_replay(self):
        rule = money_rule()
        resolution = resolve_rule([rule], context())
        changed = deepcopy(rule)
        changed["priority"] = 2
        changed["content_hash"] = canonical_hash(
            changed,
            exclude=frozenset({"content_hash"}),
        )
        with self.assertRaises(FinanceError) as error:
            evaluate_resolved_rule(resolution, [changed], {}, policy())
        self.assertEqual(error.exception.code, "RULE_RESOLUTION_REPLAY_MISMATCH")
