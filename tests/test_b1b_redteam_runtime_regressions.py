from __future__ import annotations

import unittest
from copy import deepcopy

from quantum.finance import FinanceError, calculate
from quantum.finance._runtime_legacy import calculate as calculate_underlying
from tests.test_b1b_rescue_smoke import policy, typed


def valid_request() -> dict:
    zero = typed("VALID", "0", "MONEY", "MONEY", "RUB")
    inputs = {
        "gross_sales_units": typed("VALID", "10", "INTEGER", "ITEM"),
        "returned_units": typed("VALID", "2", "INTEGER", "ITEM"),
        "resalable_returned_units": typed("VALID", "2", "INTEGER", "ITEM"),
        "compensated_returned_units": typed("VALID", "0", "INTEGER", "ITEM"),
        "return_compensation_amount": deepcopy(zero),
        "gross_sales_amount": typed("VALID", "10000", "MONEY", "MONEY", "RUB"),
        "discounts_amount": deepcopy(zero),
        "subsidies_excluding_return_compensation_amount": deepcopy(zero),
        "marketplace_commission_amount": typed(
            "VALID", "1000", "MONEY", "MONEY", "RUB"
        ),
        "forward_logistics_amount": typed(
            "VALID", "500", "MONEY", "MONEY", "RUB"
        ),
        "reverse_logistics_amount": typed(
            "VALID", "100", "MONEY", "MONEY", "RUB"
        ),
        "storage_amount": typed("VALID", "100", "MONEY", "MONEY", "RUB"),
        "advertising_amount": typed("VALID", "200", "MONEY", "MONEY", "RUB"),
        "fines_withholdings_amount": deepcopy(zero),
    }
    return {
        "calculation_id": "calc-redteam",
        "organization_id": "org-1",
        "mode": "ACTUAL",
        "scenario_id": None,
        "calculated_at": "2026-07-02T00:00:00Z",
        "profile_ref": {
            "id": "profile-1",
            "version": 1,
            "content_hash": "0" * 64,
        },
        "profile_status": "PILOT",
        "rounding_policy": policy(),
        "currency": "RUB",
        "inputs": inputs,
        "cost_per_unit": typed(
            "VALID", "400", "MONEY", "MONEY_PER_ITEM", "RUB"
        ),
        "other_expense_components": [
            {
                "component_id": "other-per-unit",
                "value": typed(
                    "VALID", "40", "MONEY", "MONEY_PER_ITEM", "RUB"
                ),
            }
        ],
        "tax_rate": typed("VALID", "0.06", "RATE", "RATE"),
        "tax_base_metric_id": "gross_sales_amount",
    }


class ExplodingCopy:
    def __deepcopy__(self, memo):
        raise AssertionError("deepcopy must not run before request admission")


class B1bRedTeamRuntimeRegressions(unittest.TestCase):
    def test_non_mapping_fails_before_deepcopy_on_all_calculation_boundaries(self) -> None:
        for target in (calculate, calculate_underlying):
            with self.subTest(target=target.__module__):
                with self.assertRaisesRegex(FinanceError, "KERNEL_REQUEST_INVALID"):
                    target(ExplodingCopy())  # type: ignore[arg-type]

    def test_malformed_mapping_fails_before_nested_deepcopy(self) -> None:
        malformed = {"extra": ExplodingCopy()}
        for target in (calculate, calculate_underlying):
            with self.subTest(target=target.__module__):
                with self.assertRaisesRegex(FinanceError, "KERNEL_REQUEST_INVALID"):
                    target(malformed)  # type: ignore[arg-type]

    def test_profit_per_unit_cites_complete_profit_expense_boundary(self) -> None:
        for target in (calculate, calculate_underlying):
            with self.subTest(target=target.__module__):
                payload = target(valid_request())
                results = payload["results"]
                self.assertEqual(
                    results["profit_per_sold_unit"]["expense_boundary"],
                    results["net_profit_amount"]["expense_boundary"],
                )
                self.assertIn(
                    "MARKETPLACE_COMMISSION",
                    results["profit_per_sold_unit"]["expense_boundary"],
                )
                self.assertNotIn(
                    "B2_RECONCILIATION_NOT_IMPLEMENTED", payload["limitations"]
                )
                self.assertIn("B2_RECONCILIATION_REQUIRED", payload["limitations"])


if __name__ == "__main__":
    unittest.main()
