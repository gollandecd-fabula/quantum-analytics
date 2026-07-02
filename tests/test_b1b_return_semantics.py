from copy import deepcopy
import unittest

from quantum.finance import calculate
from tests.test_b1b_redteam_runtime_regressions import valid_request
from tests.test_b1b_rescue_smoke import typed


class B1bReturnSemanticsTests(unittest.TestCase):
    def test_resalable_returns_restore_product_cost(self) -> None:
        results = calculate(valid_request())["results"]
        self.assertEqual(results["net_sold_units"]["value"], "8")
        self.assertEqual(results["product_cost_amount"]["value"], "3200.00")
        self.assertEqual(results["net_marketplace_income_amount"]["value"], "8100.00")
        self.assertEqual(results["net_profit_amount"]["value"], "3980.00")

    def test_non_resalable_uncompensated_return_keeps_product_cost(self) -> None:
        request = valid_request()
        request["inputs"]["resalable_returned_units"] = typed(
            "VALID", "0", "INTEGER", "ITEM"
        )
        results = calculate(request)["results"]
        self.assertEqual(results["net_sold_units"]["value"], "8")
        self.assertEqual(results["product_cost_amount"]["value"], "4000.00")
        self.assertEqual(results["net_profit_amount"]["value"], "3180.00")

    def test_compensated_return_keeps_cost_and_adds_compensation_income(self) -> None:
        request = valid_request()
        request["inputs"]["resalable_returned_units"] = typed(
            "VALID", "1", "INTEGER", "ITEM"
        )
        request["inputs"]["compensated_returned_units"] = typed(
            "VALID", "1", "INTEGER", "ITEM"
        )
        request["inputs"]["return_compensation_amount"] = typed(
            "VALID", "500", "MONEY", "MONEY", "RUB"
        )
        results = calculate(request)["results"]
        self.assertEqual(results["product_cost_amount"]["value"], "3600.00")
        self.assertEqual(results["net_marketplace_income_amount"]["value"], "8600.00")
        self.assertEqual(results["net_profit_amount"]["value"], "4080.00")

    def test_missing_return_disposition_blocks_cost_and_profit(self) -> None:
        request = valid_request()
        request["inputs"].pop("resalable_returned_units")
        results = calculate(request)["results"]
        self.assertEqual(results["net_sold_units"]["state"], "VALID")
        self.assertEqual(results["product_cost_amount"]["state"], "BLOCKED")
        self.assertEqual(
            results["product_cost_amount"]["reason_code"],
            "INPUT_REQUIRED_MISSING:resalable_returned_units",
        )
        self.assertEqual(results["net_profit_amount"]["state"], "BLOCKED")

    def test_return_categories_cannot_exceed_total_returns(self) -> None:
        request = valid_request()
        request["inputs"]["compensated_returned_units"] = typed(
            "VALID", "1", "INTEGER", "ITEM"
        )
        request["inputs"]["return_compensation_amount"] = typed(
            "VALID", "100", "MONEY", "MONEY", "RUB"
        )
        results = calculate(request)["results"]
        self.assertEqual(results["product_cost_amount"]["state"], "BLOCKED")
        self.assertEqual(
            results["product_cost_amount"]["reason_code"],
            "RETURN_UNIT_SEMANTICS_INVALID",
        )

    def test_compensation_without_compensated_unit_is_blocked(self) -> None:
        request = valid_request()
        request["inputs"]["return_compensation_amount"] = typed(
            "VALID", "100", "MONEY", "MONEY", "RUB"
        )
        results = calculate(request)["results"]
        self.assertEqual(results["net_marketplace_income_amount"]["state"], "BLOCKED")
        self.assertEqual(
            results["net_marketplace_income_amount"]["reason_code"],
            "RETURN_COMPENSATION_SEMANTICS_INVALID",
        )
        self.assertEqual(results["net_profit_amount"]["state"], "BLOCKED")

    def test_negative_return_count_is_blocked(self) -> None:
        request = deepcopy(valid_request())
        request["inputs"]["returned_units"] = typed(
            "VALID", "-1", "INTEGER", "ITEM"
        )
        results = calculate(request)["results"]
        self.assertEqual(results["net_sold_units"]["state"], "BLOCKED")
        self.assertEqual(
            results["net_sold_units"]["reason_code"],
            "RETURN_UNIT_SEMANTICS_INVALID",
        )
        self.assertEqual(results["product_cost_amount"]["state"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
