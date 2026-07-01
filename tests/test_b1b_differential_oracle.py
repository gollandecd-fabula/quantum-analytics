from __future__ import annotations

import inspect
import unittest
from decimal import Decimal

from quantum.finance import calculate
from quantum.finance.oracle import reference_calculate

from tests.b1b_helpers import (
    load_baseline,
    request_from_case,
    result_projection,
)


class B1bDifferentialOracleTests(unittest.TestCase):
    def test_oracle_does_not_import_runtime(self) -> None:
        source = inspect.getsource(reference_calculate)
        module_source = inspect.getsource(
            __import__("quantum.finance.oracle", fromlist=["reference_calculate"])
        )
        self.assertNotIn("quantum.finance.runtime", module_source)
        self.assertNotIn("from .runtime", module_source)

    def test_candidate_fixture_expected_values_match_oracle(self) -> None:
        baseline = load_baseline()
        for case in baseline["cases"]:
            with self.subTest(case=case["case_id"]):
                self.assertEqual(reference_calculate(case), case["expected"])

    def test_production_kernel_matches_independent_oracle(self) -> None:
        baseline = load_baseline()
        for case in baseline["cases"]:
            with self.subTest(case=case["case_id"]):
                production = result_projection(calculate(request_from_case(case)))
                independent = reference_calculate(case)
                self.assertEqual(production, independent)

    def test_profit_conservation_identity(self) -> None:
        baseline = load_baseline()
        for case in baseline["cases"]:
            result = calculate(request_from_case(case))["results"]
            if result["net_profit_amount"]["state"] != "VALID":
                continue
            lhs = Decimal(result["net_profit_amount"]["value"])
            rhs = (
                Decimal(result["net_marketplace_income_amount"]["value"])
                - Decimal(result["product_cost_amount"]["value"])
                - Decimal(result["other_expense_amount"]["value"])
                - Decimal(result["tax_amount"]["value"])
            )
            self.assertEqual(lhs, rhs)

    def test_monotonic_cost_increase_lowers_profit(self) -> None:
        case = load_baseline()["cases"][0]
        request = request_from_case(case)
        baseline_profit = Decimal(
            calculate(request)["results"]["net_profit_amount"]["value"]
        )
        for increase in ("1", "2.5", "10"):
            modified = request_from_case(case)
            modified["cost_per_unit"]["value"] = str(
                Decimal(modified["cost_per_unit"]["value"]) + Decimal(increase)
            )
            profit = Decimal(
                calculate(modified)["results"]["net_profit_amount"]["value"]
            )
            self.assertLess(profit, baseline_profit)

    def test_monotonic_sales_increase_with_gross_tax_base(self) -> None:
        case = load_baseline()["cases"][0]
        baseline_profit = Decimal(
            calculate(request_from_case(case))["results"]["net_profit_amount"]["value"]
        )
        for increase in ("10", "100", "250"):
            modified = request_from_case(case)
            modified["inputs"]["gross_sales_amount"]["value"] = str(
                Decimal(modified["inputs"]["gross_sales_amount"]["value"])
                + Decimal(increase)
            )
            profit = Decimal(
                calculate(modified)["results"]["net_profit_amount"]["value"]
            )
            self.assertGreater(profit, baseline_profit)


if __name__ == "__main__":
    unittest.main()
