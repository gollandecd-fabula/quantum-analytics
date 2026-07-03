import unittest

from quantum.finance import FinanceError, calculate
from tests.test_b1b_rescue_input_boundaries import request
from tests.test_b1b_rescue_smoke import typed


FULL_PROFIT_BOUNDARY = [
    "MARKETPLACE_COMMISSION",
    "FORWARD_LOGISTICS",
    "REVERSE_LOGISTICS",
    "STORAGE",
    "ADVERTISING",
    "FINES_WITHHOLDINGS",
    "PRODUCT_COST",
    "OTHER_EXPENSE",
    "TAX",
]


class B1bFinancialDomainContractTests(unittest.TestCase):
    def assert_finance_error(self, candidate, code):
        with self.assertRaises(FinanceError) as error:
            calculate(candidate)
        self.assertEqual(error.exception.code, code)

    def test_negative_kernel_amount_is_rejected(self):
        candidate = request()
        candidate["inputs"]["marketplace_commission_amount"] = typed(
            "VALID",
            "-1",
            "MONEY",
            "MONEY",
            "RUB",
        )
        self.assert_finance_error(
            candidate,
            "KERNEL_INPUT_NEGATIVE_FORBIDDEN:"
            "marketplace_commission_amount",
        )

    def test_negative_unit_input_is_rejected(self):
        candidate = request()
        candidate["inputs"]["returned_units"] = typed(
            "VALID",
            "-1",
            "INTEGER",
            "ITEM",
        )
        self.assert_finance_error(
            candidate,
            "KERNEL_INPUT_NEGATIVE_FORBIDDEN:returned_units",
        )

    def test_negative_cost_per_unit_is_rejected(self):
        candidate = request()
        candidate["cost_per_unit"] = typed(
            "VALID",
            "-1",
            "MONEY",
            "MONEY_PER_ITEM",
            "RUB",
        )
        self.assert_finance_error(
            candidate,
            "COST_PER_UNIT_NEGATIVE_FORBIDDEN",
        )

    def test_negative_other_expense_is_rejected(self):
        candidate = request()
        candidate["other_expense_components"][0]["value"] = typed(
            "VALID",
            "-1",
            "MONEY",
            "MONEY_PER_ITEM",
            "RUB",
        )
        self.assert_finance_error(
            candidate,
            "OTHER_EXPENSE_NEGATIVE_FORBIDDEN:o",
        )

    def test_tax_rate_must_be_between_zero_and_one(self):
        for value in ("-0.01", "1.01"):
            with self.subTest(value=value):
                candidate = request()
                candidate["tax_rate"] = typed(
                    "VALID",
                    value,
                    "RATE",
                    "RATE",
                )
                self.assert_finance_error(
                    candidate,
                    "TAX_RATE_OUT_OF_RANGE",
                )

    def test_negative_tax_base_is_blocked(self):
        candidate = request()
        candidate["inputs"]["gross_sales_amount"] = typed(
            "VALID",
            "0",
            "MONEY",
            "MONEY",
            "RUB",
        )
        candidate["inputs"]["marketplace_commission_amount"] = typed(
            "VALID",
            "1",
            "MONEY",
            "MONEY",
            "RUB",
        )
        candidate["tax_base_metric_id"] = (
            "net_marketplace_income_amount"
        )
        result = calculate(candidate)["results"]["tax_amount"]
        self.assertEqual(result["state"], "BLOCKED")
        self.assertEqual(
            result["reason_code"],
            "TAX_BASE_NEGATIVE_POLICY_REQUIRED",
        )

    def test_negative_net_units_do_not_restore_cost_implicitly(self):
        candidate = request()
        candidate["inputs"]["gross_sales_units"] = typed(
            "VALID",
            "0",
            "INTEGER",
            "ITEM",
        )
        candidate["inputs"]["returned_units"] = typed(
            "VALID",
            "1",
            "INTEGER",
            "ITEM",
        )
        payload = calculate(candidate)
        results = payload["results"]
        self.assertEqual(
            (
                results["net_sold_units"]["state"],
                results["net_sold_units"]["value"],
            ),
            ("VALID", "-1"),
        )
        self.assertEqual(
            results["product_cost_amount"]["reason_code"],
            "RETURN_COST_RESTORATION_POLICY_REQUIRED",
        )
        self.assertEqual(
            results["other_expense_amount"]["reason_code"],
            "DEPENDENCY_BLOCKED:NEGATIVE_NET_UNITS_EXPENSE_POLICY_REQUIRED",
        )
        self.assertIn(
            "RETURN_COST_RESTORATION_POLICY_NOT_APPROVED",
            payload["limitations"],
        )

    def test_profit_per_unit_declares_full_profit_boundary(self):
        results = calculate(request())["results"]
        self.assertEqual(
            results["profit_per_sold_unit"]["expense_boundary"],
            FULL_PROFIT_BOUNDARY,
        )
        self.assertEqual(
            results["net_profit_amount"]["expense_boundary"],
            FULL_PROFIT_BOUNDARY,
        )


if __name__ == "__main__":
    unittest.main()
