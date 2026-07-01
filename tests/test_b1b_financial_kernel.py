from __future__ import annotations

import copy
import unittest
from decimal import Decimal

from quantum.finance import FinanceError, calculate

from tests.b1b_helpers import (
    load_baseline,
    request_from_case,
    result_projection,
    typed,
)


class B1bFinancialKernelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.baseline = load_baseline()

    def test_all_golden_cases_match_candidate_baseline(self) -> None:
        for case in self.baseline["cases"]:
            with self.subTest(case=case["case_id"]):
                result = calculate(request_from_case(case))
                self.assertEqual(result_projection(result), case["expected"])

    def test_replay_is_deterministic(self) -> None:
        request = request_from_case(self.baseline["cases"][0])
        self.assertEqual(calculate(request), calculate(copy.deepcopy(request)))

    def test_kernel_does_not_mutate_input(self) -> None:
        request = request_from_case(self.baseline["cases"][0])
        before = copy.deepcopy(request)
        calculate(request)
        self.assertEqual(request, before)

    def test_publication_is_preview_only(self) -> None:
        result = calculate(request_from_case(self.baseline["cases"][0]))
        self.assertEqual(result["publication_state"], "PREVIEW_ONLY")
        self.assertIn("PRODUCTION_RELEASE_BLOCKED", result["limitations"])

    def test_actual_rejects_scenario_id(self) -> None:
        request = request_from_case(self.baseline["cases"][0])
        request["scenario_id"] = "forbidden"
        with self.assertRaisesRegex(FinanceError, "PROFILE_MODE_CONTAMINATION"):
            calculate(request)

    def test_scenario_requires_scenario_id(self) -> None:
        request = request_from_case(self.baseline["cases"][1])
        request["scenario_id"] = None
        with self.assertRaisesRegex(FinanceError, "PROFILE_MODE_CONTAMINATION"):
            calculate(request)

    def test_active_profile_is_not_used_by_preview_kernel(self) -> None:
        request = request_from_case(self.baseline["cases"][0])
        request["profile_status"] = "ACTIVE"
        with self.assertRaisesRegex(FinanceError, "PROFILE_PUBLICATION_BLOCKED"):
            calculate(request)

    def test_missing_return_blocks_only_dependent_profit_path(self) -> None:
        request = request_from_case(self.baseline["cases"][0])
        request["inputs"]["returned_units"] = typed(
            None,
            value_type="INTEGER",
            unit="ITEM",
            state="UNAVAILABLE",
            reason_code="RETURN_SOURCE_UNAVAILABLE",
        )
        result = calculate(request)["results"]
        self.assertEqual(result["net_sold_units"]["state"], "UNAVAILABLE")
        self.assertEqual(result["product_cost_amount"]["state"], "UNAVAILABLE")
        self.assertEqual(result["net_profit_amount"]["state"], "UNAVAILABLE")
        self.assertEqual(result["net_marketplace_income_amount"]["state"], "VALID")

    def test_empty_other_expense_list_is_blocked_not_zero(self) -> None:
        request = request_from_case(self.baseline["cases"][0])
        request["other_expense_components"] = []
        result = calculate(request)["results"]
        self.assertEqual(result["other_expense_amount"]["state"], "BLOCKED")
        self.assertEqual(
            result["other_expense_amount"]["reason_code"],
            "OTHER_EXPENSE_RULE_REQUIRED_MISSING",
        )
        self.assertEqual(result["net_marketplace_income_amount"]["state"], "VALID")
        self.assertEqual(result["net_profit_amount"]["state"], "BLOCKED")

    def test_explicit_zero_other_expense_is_valid_zero(self) -> None:
        case = self.baseline["cases"][2]
        result = calculate(request_from_case(case))["results"]
        self.assertEqual(result["other_expense_amount"]["state"], "VALID")
        self.assertEqual(result["other_expense_amount"]["value"], "0.00")

    def test_zero_denominator_blocks_profit_per_unit(self) -> None:
        result = calculate(request_from_case(self.baseline["cases"][2]))["results"]
        self.assertEqual(result["profit_per_sold_unit"]["state"], "BLOCKED")
        self.assertEqual(result["profit_per_sold_unit"]["reason_code"], "ZERO_DENOMINATOR")

    def test_profitability_remains_blocked_without_denominator(self) -> None:
        result = calculate(request_from_case(self.baseline["cases"][0]))["results"]
        self.assertEqual(result["profitability_of_costs"]["state"], "BLOCKED")
        self.assertEqual(
            result["profitability_of_costs"]["reason_code"],
            "COST_DENOMINATOR_NOT_APPROVED",
        )

    def test_cross_currency_input_blocks_dependent_settlement(self) -> None:
        request = request_from_case(self.baseline["cases"][0])
        request["inputs"]["storage_amount"]["currency"] = "RUB"
        result = calculate(request)["results"]
        self.assertEqual(result["net_marketplace_income_amount"]["state"], "BLOCKED")
        self.assertEqual(result["net_profit_amount"]["state"], "BLOCKED")
        self.assertEqual(result["product_cost_amount"]["state"], "VALID")

    def test_unknown_tax_base_blocks_tax_and_profit(self) -> None:
        request = request_from_case(self.baseline["cases"][0])
        request["tax_base_metric_id"] = "unknown_tax_base"
        result = calculate(request)["results"]
        self.assertEqual(result["tax_amount"]["state"], "BLOCKED")
        self.assertTrue(result["tax_amount"]["reason_code"].startswith("TAX_BASE_MISSING"))
        self.assertEqual(result["net_profit_amount"]["state"], "BLOCKED")
        self.assertEqual(result["net_marketplace_income_amount"]["state"], "VALID")

    def test_duplicate_other_expense_component_rejected(self) -> None:
        request = request_from_case(self.baseline["cases"][0])
        request["other_expense_components"].append(
            copy.deepcopy(request["other_expense_components"][0])
        )
        with self.assertRaisesRegex(FinanceError, "OTHER_EXPENSE_COMPONENTS_INVALID"):
            calculate(request)

    def test_missing_settlement_input_does_not_become_zero(self) -> None:
        request = request_from_case(self.baseline["cases"][0])
        del request["inputs"]["storage_amount"]
        result = calculate(request)["results"]
        self.assertEqual(result["net_marketplace_income_amount"]["state"], "BLOCKED")
        self.assertIn(
            "INPUT_REQUIRED_MISSING:storage_amount",
            result["net_marketplace_income_amount"]["reason_code"],
        )

    def test_conflict_state_has_priority_over_blocked(self) -> None:
        request = request_from_case(self.baseline["cases"][0])
        request["inputs"]["gross_sales_amount"] = typed(
            None,
            value_type="MONEY",
            unit="MONEY",
            currency="EUR",
            state="BLOCKED",
            reason_code="GROSS_BLOCKED",
        )
        request["inputs"]["storage_amount"] = typed(
            None,
            value_type="MONEY",
            unit="MONEY",
            currency="EUR",
            state="CONFLICT",
            reason_code="STORAGE_CONFLICT",
        )
        result = calculate(request)["results"]["net_marketplace_income_amount"]
        self.assertEqual(result["state"], "CONFLICT")
        self.assertIn("STORAGE_CONFLICT", result["reason_code"])

    def test_accounting_views_and_expense_boundaries_are_explicit(self) -> None:
        result = calculate(request_from_case(self.baseline["cases"][0]))["results"]
        self.assertEqual(result["tax_amount"]["accounting_view"], "TAX_RECOGNITION")
        self.assertEqual(result["net_sold_units"]["accounting_view"], "OPERATIONAL")
        self.assertEqual(result["net_profit_amount"]["accounting_view"], "SETTLEMENT")
        self.assertIn("PRODUCT_COST", result["net_profit_amount"]["expense_boundary"])
        self.assertNotIn(
            "PRODUCT_COST",
            result["net_marketplace_income_amount"]["expense_boundary"],
        )
        self.assertIsNone(result["net_sold_units"]["rounding"])
        self.assertIsNone(result["profitability_of_costs"]["rounding"])
        rounding = result["net_profit_amount"]["rounding"]
        self.assertIsInstance(rounding, dict)
        self.assertEqual(rounding["application_point"], "METRIC_FINAL_ACCOUNTING")
        self.assertEqual(rounding["resolved_mode"], "HALF_EVEN")
        self.assertEqual(rounding["resolved_scale"], 2)

    def test_hashes_change_when_input_changes(self) -> None:
        request = request_from_case(self.baseline["cases"][0])
        first = calculate(request)
        request["cost_per_unit"]["value"] = "41"
        second = calculate(request)
        self.assertNotEqual(first["input_hash"], second["input_hash"])
        self.assertNotEqual(first["result_hash"], second["result_hash"])

    def test_negative_correction_blocks_profit_per_unit(self) -> None:
        result = calculate(request_from_case(self.baseline["cases"][3]))["results"]
        self.assertEqual(result["net_sold_units"]["value"], "-1")
        self.assertEqual(result["net_profit_amount"]["value"], "-44.00")
        self.assertEqual(result["profit_per_sold_unit"]["state"], "BLOCKED")
        self.assertIsNone(result["profit_per_sold_unit"]["value"])
        self.assertEqual(
            result["profit_per_sold_unit"]["reason_code"],
            "NON_POSITIVE_DENOMINATOR",
        )


if __name__ == "__main__":
    unittest.main()
