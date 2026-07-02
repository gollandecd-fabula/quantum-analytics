import unittest

from quantum.finance import FinanceError, calculate, evaluate_expression
from tests.test_b1b_rescue_input_boundaries import request
from tests.test_b1b_rescue_smoke import policy, typed


POLICY_OVERSIZED_NUMBER = "1" * 29
HARD_OVERSIZED_NUMBER = "1" + ("0" * 1000)


class B1bPolicyInputLimitTests(unittest.TestCase):
    def test_kernel_rejects_typed_decimal_above_policy_precision(self):
        candidate = request()
        candidate["inputs"]["gross_sales_amount"] = typed(
            "VALID", POLICY_OVERSIZED_NUMBER, "MONEY", "MONEY", "RUB"
        )
        with self.assertRaises(FinanceError) as error:
            calculate(candidate)
        self.assertEqual(error.exception.code, "ROUNDING_INPUT_PRECISION_EXCEEDED")

    def test_kernel_rejects_integer_unit_count_above_policy_precision(self):
        candidate = request()
        candidate["inputs"]["gross_sales_units"] = typed(
            "VALID", POLICY_OVERSIZED_NUMBER, "INTEGER", "ITEM"
        )
        with self.assertRaises(FinanceError) as error:
            calculate(candidate)
        self.assertEqual(error.exception.code, "ROUNDING_INPUT_PRECISION_EXCEEDED")

    def test_expression_rejects_typed_variable_above_policy_precision(self):
        expression = {
            "kind": "VARIABLE",
            "name": "gross_sales_amount",
            "value_type": "MONEY",
            "currency": "RUB",
            "unit": "MONEY",
        }
        variables = {
            "gross_sales_amount": typed(
                "VALID", POLICY_OVERSIZED_NUMBER, "MONEY", "MONEY", "RUB"
            )
        }
        with self.assertRaises(FinanceError) as error:
            evaluate_expression(
                expression,
                variables,
                ["gross_sales_amount"],
                policy(),
            )
        self.assertEqual(error.exception.code, "ROUNDING_INPUT_PRECISION_EXCEEDED")

    def test_typed_decimal_rejects_global_oversize_before_normalization(self):
        candidate = request()
        candidate["inputs"]["gross_sales_amount"] = typed(
            "VALID", HARD_OVERSIZED_NUMBER, "MONEY", "MONEY", "RUB"
        )
        with self.assertRaises(FinanceError) as error:
            calculate(candidate)
        self.assertEqual(error.exception.code, "ROUNDING_INPUT_PRECISION_EXCEEDED")

    def test_typed_integer_rejects_global_oversize_before_conversion(self):
        candidate = request()
        candidate["inputs"]["gross_sales_units"] = typed(
            "VALID", HARD_OVERSIZED_NUMBER, "INTEGER", "ITEM"
        )
        with self.assertRaises(FinanceError) as error:
            calculate(candidate)
        self.assertEqual(error.exception.code, "ROUNDING_INPUT_PRECISION_EXCEEDED")


if __name__ == "__main__":
    unittest.main()
