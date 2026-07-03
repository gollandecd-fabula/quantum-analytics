import unittest

from quantum.finance import calculate
from tests.test_b1b_rescue_input_boundaries import request
from tests.test_b1b_rescue_smoke import typed


class B1bR16FinancialDomainContractTests(unittest.TestCase):
    def test_negative_marketplace_magnitude_is_blocked(self):
        candidate = request()
        candidate["inputs"]["marketplace_commission_amount"] = typed(
            "VALID",
            "-1",
            "MONEY",
            "MONEY",
            "RUB",
        )
        result = calculate(candidate)["results"]["net_marketplace_income_amount"]
        self.assertEqual(result["state"], "BLOCKED")
        self.assertIn(
            "NEGATIVE_FINANCIAL_MAGNITUDE:marketplace_commission_amount",
            result["reason_code"],
        )

    def test_negative_cost_per_unit_is_blocked(self):
        candidate = request()
        candidate["cost_per_unit"] = typed(
            "VALID",
            "-1",
            "MONEY",
            "MONEY_PER_ITEM",
            "RUB",
        )
        result = calculate(candidate)["results"]["product_cost_amount"]
        self.assertEqual(result["state"], "BLOCKED")
        self.assertEqual(
            result["reason_code"],
            "COST_PER_UNIT_NEGATIVE_FORBIDDEN",
        )

    def test_negative_other_expense_is_blocked(self):
        candidate = request()
        candidate["other_expense_components"][0]["value"] = typed(
            "VALID",
            "-1",
            "MONEY",
            "MONEY_PER_ITEM",
            "RUB",
        )
        result = calculate(candidate)["results"]["other_expense_amount"]
        self.assertEqual(result["state"], "BLOCKED")
        self.assertEqual(
            result["reason_code"],
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
                result = calculate(candidate)["results"]["tax_amount"]
                self.assertEqual(result["state"], "BLOCKED")
                self.assertEqual(
                    result["reason_code"],
                    "TAX_RATE_OUT_OF_RANGE",
                )

    def test_negative_tax_base_requires_an_approved_policy(self):
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
        candidate["tax_base_metric_id"] = "net_marketplace_income_amount"
        result = calculate(candidate)["results"]["tax_amount"]
        self.assertEqual(result["state"], "BLOCKED")
        self.assertEqual(
            result["reason_code"],
            "TAX_BASE_NEGATIVE_POLICY_REQUIRED",
        )


if __name__ == "__main__":
    unittest.main()
