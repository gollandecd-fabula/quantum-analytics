from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
import json
import unittest

from quantum.finance import FinanceError, calculate, canonical_hash
from quantum.pilot.local_runner import _reconcile


REQUIRED_METRICS = {
    "net_sold_units": "8",
    "product_cost_amount": "3600.00",
    "other_expense_amount": "420.00",
    "tax_amount": "600.00",
    "net_marketplace_income_amount": "7750.00",
    "net_profit_amount": "3130.00",
    "profit_per_sold_unit": "391.25",
}


def typed(
    state: str,
    value: str | None,
    value_type: str,
    unit: str,
    currency: str | None = None,
    reason_code: str | None = None,
) -> dict[str, object]:
    return {
        "state": state,
        "value": value,
        "value_type": value_type,
        "unit": unit,
        "currency": currency,
        "reason_code": reason_code,
        "source_ids": [],
    }


def rounding_policy() -> dict[str, object]:
    value: dict[str, object] = {
        "policy_id": "m4-financial-correctness",
        "version": 1,
        "content_hash": "",
        "status": "PILOT",
        "calculation_mode": "HALF_EVEN",
        "calculation_scale": 6,
        "money_scale": 2,
        "rate_scale": 6,
        "presentation_mode": "HALF_EVEN",
        "presentation_scale": 2,
        "currency_presentation_scales": {"RUB": 2},
        "application_points": [
            "RULE_INPUT_NORMALIZATION",
            "RULE_COMPONENT_RESULT",
            "METRIC_FINAL_ACCOUNTING",
        ],
        "max_input_precision": 28,
        "max_input_scale": 8,
        "actor": "m4-red-team",
        "created_at": "2026-07-12T00:00:00Z",
        "source": "m4-red-team",
        "change_reason": "financial and data correctness",
        "approval_reference": "owner",
        "supersedes": None,
    }
    value["content_hash"] = canonical_hash(
        value,
        exclude=frozenset({"content_hash"}),
    )
    return value


def request() -> dict[str, object]:
    zero_money = typed("VALID", "0", "MONEY", "MONEY", "RUB")
    return {
        "calculation_id": "m4-calc-1",
        "organization_id": "tenant-m4",
        "mode": "ACTUAL",
        "scenario_id": None,
        "calculated_at": "2026-07-12T00:00:00Z",
        "profile_ref": {
            "id": "m4-profile",
            "version": 1,
            "content_hash": "0" * 64,
        },
        "profile_status": "PILOT",
        "rounding_policy": rounding_policy(),
        "currency": "RUB",
        "inputs": {
            "gross_sales_units": typed("VALID", "10", "INTEGER", "ITEM"),
            "returned_units": typed("VALID", "2", "INTEGER", "ITEM"),
            "resalable_returned_units": typed(
                "VALID", "1", "INTEGER", "ITEM"
            ),
            "compensated_returned_units": typed(
                "VALID", "1", "INTEGER", "ITEM"
            ),
            "return_compensation_amount": typed(
                "VALID", "300", "MONEY", "MONEY", "RUB"
            ),
            "gross_sales_amount": typed(
                "VALID", "10000", "MONEY", "MONEY", "RUB"
            ),
            "discounts_amount": typed(
                "VALID", "500", "MONEY", "MONEY", "RUB"
            ),
            "subsidies_excluding_return_compensation_amount": typed(
                "VALID", "100", "MONEY", "MONEY", "RUB"
            ),
            "marketplace_commission_amount": typed(
                "VALID", "1000", "MONEY", "MONEY", "RUB"
            ),
            "forward_logistics_amount": typed(
                "VALID", "500", "MONEY", "MONEY", "RUB"
            ),
            "reverse_logistics_amount": typed(
                "VALID", "200", "MONEY", "MONEY", "RUB"
            ),
            "storage_amount": typed(
                "VALID", "100", "MONEY", "MONEY", "RUB"
            ),
            "advertising_amount": typed(
                "VALID", "300", "MONEY", "MONEY", "RUB"
            ),
            "fines_withholdings_amount": typed(
                "VALID", "50", "MONEY", "MONEY", "RUB"
            ),
        },
        "cost_per_unit": typed(
            "VALID", "400", "MONEY", "MONEY_PER_ITEM", "RUB"
        ),
        "other_expense_components": [
            {
                "component_id": "per-sold-unit",
                "value": typed(
                    "VALID", "40", "MONEY", "MONEY_PER_ITEM", "RUB"
                ),
            },
            {
                "component_id": "period-fixed",
                "value": typed(
                    "VALID", "100", "MONEY", "MONEY", "RUB"
                ),
            },
        ],
        "tax_rate": typed("VALID", "0.06", "RATE", "RATE"),
        "tax_base_metric_id": "gross_sales_amount",
    }


def control_totals_sha(expected: dict[str, str]) -> str:
    payload = json.dumps(
        expected,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(payload).hexdigest()


class M4FinancialDataCorrectnessTests(unittest.TestCase):
    def test_reconciliation_guard_is_installed_on_engine_module(self) -> None:
        import quantum.pilot.local_runner as engine

        self.assertTrue(engine._m4_reconciliation_guard_installed)
        self.assertEqual(
            "quantum.pilot.reconciliation_guard",
            engine._reconcile.__module__,
        )

    def test_full_financial_formula_and_return_treatment(self) -> None:
        calculation = calculate(request())
        results = calculation["results"]
        for metric_id, expected in REQUIRED_METRICS.items():
            self.assertEqual("VALID", results[metric_id]["state"], metric_id)
            self.assertEqual(expected, results[metric_id]["value"], metric_id)
        self.assertEqual("PREVIEW_ONLY", calculation["publication_state"])

    def test_required_financial_inputs_fail_closed(self) -> None:
        cases = (
            ("cost_per_unit", "KERNEL_REQUEST_INVALID"),
            ("tax_rate", "KERNEL_REQUEST_INVALID"),
            ("other_expense_components", "KERNEL_REQUEST_INVALID"),
        )
        for field, code in cases:
            with self.subTest(field=field):
                candidate = request()
                candidate.pop(field)
                with self.assertRaises(FinanceError) as error:
                    calculate(candidate)
                self.assertEqual(code, error.exception.code)

    def test_negative_cost_tax_and_expenses_are_blocked(self) -> None:
        candidate = request()
        candidate["cost_per_unit"]["value"] = "-1"
        self.assertEqual(
            "COST_PER_UNIT_NEGATIVE_FORBIDDEN",
            calculate(candidate)["results"]["product_cost_amount"]["reason_code"],
        )

        candidate = request()
        candidate["tax_rate"]["value"] = "1.01"
        self.assertEqual(
            "TAX_RATE_OUT_OF_RANGE",
            calculate(candidate)["results"]["tax_amount"]["reason_code"],
        )

        candidate = request()
        candidate["other_expense_components"][0]["value"]["value"] = "-1"
        self.assertTrue(
            calculate(candidate)["results"]["other_expense_amount"][
                "reason_code"
            ].startswith("OTHER_EXPENSE_NEGATIVE_FORBIDDEN:")
        )

    def test_negative_tax_base_requires_policy_in_kernel_and_oracle(self) -> None:
        candidate = request()
        candidate["tax_base_metric_id"] = "net_marketplace_income_amount"
        candidate["inputs"]["marketplace_commission_amount"]["value"] = "20000"
        actual = calculate(candidate)["results"]
        self.assertEqual("BLOCKED", actual["tax_amount"]["state"])
        self.assertEqual(
            "TAX_BASE_NEGATIVE_POLICY_REQUIRED",
            actual["tax_amount"]["reason_code"],
        )
        self.assertEqual("BLOCKED", actual["net_profit_amount"]["state"])

        from quantum.finance.oracle import reference_calculate

        oracle = reference_calculate(
            {
                "money_scale": 2,
                "rounding_mode": "HALF_EVEN",
                "inputs": {
                    key: str(value["value"])
                    for key, value in candidate["inputs"].items()
                    if key not in {
                        "gross_sales_units",
                        "returned_units",
                        "resalable_returned_units",
                        "compensated_returned_units",
                    }
                },
                "gross_sales_units": 10,
                "returned_units": 2,
                "resalable_returned_units": 1,
                "compensated_returned_units": 1,
                "cost_per_unit": "400",
                "other_expenses": [
                    {"unit": "MONEY_PER_ITEM", "value": "40"},
                    {"unit": "MONEY", "value": "100"},
                ],
                "tax_base_metric_id": "net_marketplace_income_amount",
                "tax_rate": "0.06",
            }
        )
        self.assertEqual({"state": "BLOCKED", "value": None}, oracle["tax_amount"])
        self.assertEqual({"state": "BLOCKED", "value": None}, oracle["net_profit_amount"])

    def test_metric_lineage_and_hashes_are_deterministic(self) -> None:
        first = calculate(request())
        second = calculate(request())
        self.assertEqual(first["input_hash"], second["input_hash"])
        self.assertEqual(first["result_hash"], second["result_hash"])
        for metric_id in REQUIRED_METRICS:
            metric = first["results"][metric_id]
            self.assertTrue(metric["source_ids"], metric_id)
            self.assertIsNotNone(metric["accounting_view"], metric_id)

    def test_partial_matching_controls_cannot_reconcile(self) -> None:
        calculation = calculate(request())
        expected = {"net_profit_amount": "3130.00"}
        result = _reconcile(
            calculation,
            {"expected_metrics": expected},
            control_totals_sha(expected),
        )
        self.assertEqual("CONFLICT", result["state"])
        self.assertEqual(
            "RECONCILIATION_METRIC_SET_MISMATCH",
            result["reason_code"],
        )

    def test_matching_controls_without_hash_remain_pending(self) -> None:
        calculation = calculate(request())
        result = _reconcile(
            calculation,
            {"expected_metrics": dict(REQUIRED_METRICS)},
            None,
        )
        self.assertEqual("PENDING", result["state"])
        self.assertEqual("CONTROL_TOTALS_HASH_REQUIRED", result["reason_code"])
        self.assertFalse(result["control_totals_bound"])

    def test_tampered_control_totals_hash_conflicts(self) -> None:
        calculation = calculate(request())
        result = _reconcile(
            calculation,
            {"expected_metrics": dict(REQUIRED_METRICS)},
            "0" * 64,
        )
        self.assertEqual("CONFLICT", result["state"])
        self.assertEqual("CONTROL_TOTALS_HASH_MISMATCH", result["reason_code"])
        self.assertFalse(result["control_totals_bound"])

    def test_complete_hash_bound_controls_reconcile(self) -> None:
        calculation = calculate(request())
        expected = dict(REQUIRED_METRICS)
        result = _reconcile(
            calculation,
            {"expected_metrics": expected},
            control_totals_sha(expected),
        )
        self.assertEqual("RECONCILED", result["state"])
        self.assertEqual([], result["differences"])
        self.assertTrue(result["control_totals_bound"])

    def test_actual_mismatch_remains_conflict_after_hash_binding(self) -> None:
        calculation = calculate(request())
        expected = dict(REQUIRED_METRICS)
        expected["net_profit_amount"] = "3129.99"
        result = _reconcile(
            calculation,
            {"expected_metrics": expected},
            control_totals_sha(expected),
        )
        self.assertEqual("CONFLICT", result["state"])
        self.assertEqual("METRIC_VALUE_MISMATCH", result["reason_code"])
        self.assertEqual(
            "net_profit_amount",
            result["differences"][0]["metric_id"],
        )


if __name__ == "__main__":
    unittest.main()
