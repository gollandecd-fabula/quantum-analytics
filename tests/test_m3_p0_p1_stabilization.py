from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from quantum.finance import FinanceError, calculate, canonical_hash, evaluate_expression
from quantum.adapters.wildberries.detailed_financial import _decimal as detailed_decimal
from quantum.adapters.wildberries.weekly_summary import (
    EXPECTED_WEEKLY_SUMMARY_HEADERS,
    WbWeeklySummaryError,
    _decimal as weekly_decimal,
    _header_row,
)
from quantum.pilot.universal_intake import register_file


def typed(state, value, value_type, unit, currency=None, reason_code=None):
    return {
        "state": state,
        "value": value,
        "value_type": value_type,
        "unit": unit,
        "currency": currency,
        "reason_code": reason_code,
        "source_ids": [],
    }


def policy():
    value = {
        "policy_id": "m3-rounding",
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
        "actor": "m3",
        "created_at": "2026-07-11T00:00:00Z",
        "source": "m3-red-team",
        "change_reason": "P0/P1 stabilization",
        "approval_reference": "owner",
        "supersedes": None,
    }
    value["content_hash"] = canonical_hash(
        value,
        exclude=frozenset({"content_hash"}),
    )
    return value


def request():
    zero_money = typed("VALID", "0", "MONEY", "MONEY", "RUB")
    zero_items = typed("VALID", "0", "INTEGER", "ITEM")
    return {
        "calculation_id": "m3-calc",
        "organization_id": "org-1",
        "mode": "ACTUAL",
        "scenario_id": None,
        "calculated_at": "2026-07-11T00:00:00Z",
        "profile_ref": {
            "id": "profile-1",
            "version": 1,
            "content_hash": "0" * 64,
        },
        "profile_status": "PILOT",
        "rounding_policy": policy(),
        "currency": "RUB",
        "inputs": {
            "gross_sales_units": typed(
                "VALID", "1", "INTEGER", "ITEM"
            ),
            "returned_units": deepcopy(zero_items),
            "resalable_returned_units": deepcopy(zero_items),
            "compensated_returned_units": deepcopy(zero_items),
            "return_compensation_amount": deepcopy(zero_money),
            "gross_sales_amount": deepcopy(zero_money),
            "discounts_amount": deepcopy(zero_money),
            "subsidies_excluding_return_compensation_amount": deepcopy(
                zero_money
            ),
            "marketplace_commission_amount": deepcopy(zero_money),
            "forward_logistics_amount": deepcopy(zero_money),
            "reverse_logistics_amount": deepcopy(zero_money),
            "storage_amount": deepcopy(zero_money),
            "advertising_amount": deepcopy(zero_money),
            "fines_withholdings_amount": deepcopy(zero_money),
        },
        "cost_per_unit": typed(
            "VALID", "0", "MONEY", "MONEY_PER_ITEM", "RUB"
        ),
        "other_expense_components": [
            {
                "component_id": "other",
                "value": typed(
                    "VALID", "0", "MONEY", "MONEY_PER_ITEM", "RUB"
                ),
            }
        ],
        "tax_rate": typed("VALID", "0", "RATE", "RATE"),
        "tax_base_metric_id": "gross_sales_amount",
    }


class M3P0P1StabilizationTests(unittest.TestCase):
    def test_missing_cost_tax_and_other_expenses_fail_closed(self):
        for field in (
            "cost_per_unit",
            "tax_rate",
            "other_expense_components",
        ):
            candidate = request()
            candidate.pop(field)
            with self.subTest(field=field):
                with self.assertRaises(FinanceError) as error:
                    calculate(candidate)
                self.assertEqual(
                    "KERNEL_REQUEST_INVALID",
                    error.exception.code,
                )

    def test_unknown_financial_input_is_rejected(self):
        candidate = request()
        candidate["inputs"]["invented_revenue"] = typed(
            "VALID", "1", "MONEY", "MONEY", "RUB"
        )
        with self.assertRaises(FinanceError) as error:
            calculate(candidate)
        self.assertEqual("KERNEL_INPUTS_INVALID", error.exception.code)

    def test_explicit_zero_revenue_is_valid_not_missing(self):
        results = calculate(request())["results"]
        for metric in (
            "net_marketplace_income_amount",
            "product_cost_amount",
            "other_expense_amount",
            "tax_amount",
            "net_profit_amount",
            "profit_per_sold_unit",
        ):
            self.assertEqual("VALID", results[metric]["state"], metric)
            self.assertEqual("0.00", results[metric]["value"], metric)

    def test_division_by_zero_is_blocked_not_raised(self):
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
        result = evaluate_expression(expression, {}, [], policy())
        self.assertEqual("BLOCKED", result["state"])
        self.assertEqual(
            "EXPRESSION_DIVISION_BY_ZERO",
            result["reason_code"],
        )
        self.assertIsNone(result["value"])

    def test_decimal_comma_is_supported_in_wb_numeric_boundaries(self):
        self.assertEqual(
            Decimal("1.25"),
            detailed_decimal("1,25", "M3"),
        )
        self.assertEqual(
            Decimal("1.25"),
            weekly_decimal("1,25", "M3"),
        )

    def test_changed_column_order_is_rejected_not_silently_remapped(self):
        headers = list(EXPECTED_WEEKLY_SUMMARY_HEADERS)
        headers[0], headers[1] = headers[1], headers[0]
        with self.assertRaises(WbWeeklySummaryError) as error:
            _header_row([(1, tuple(headers))], 1)
        self.assertEqual(
            "WB_WEEKLY_HEADERS_UNSUPPORTED",
            error.exception.code,
        )

    def test_missing_file_returns_privacy_safe_error_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = register_file(
                file_path=Path(tmp) / "missing.xlsx",
                storage_root=Path(tmp) / "storage",
            )
        self.assertEqual("ERROR", report["status"])
        self.assertIn("FILE_NOT_FOUND", report["reason_codes"])
        self.assertIsNone(report["file_sha256"])
        self.assertFalse(report["marketplace_write_enabled"])
        self.assertIsNone(report["calculation"])


if __name__ == "__main__":
    unittest.main()
