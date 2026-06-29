from __future__ import annotations

import copy
import unittest

from quantum.evidence import (
    canonical_snapshot_hash,
    diagnose_metric_snapshot,
    verify_metric_snapshot,
)
from tests.b3_helpers import valid_snapshot


def checked(**changes):
    snapshot = valid_snapshot()
    snapshot.update(changes)
    snapshot["content_hash"] = canonical_snapshot_hash(snapshot)
    return verify_metric_snapshot(snapshot)


class B3MetricSnapshot(unittest.TestCase):
    def test_01_valid_zero(self):
        self.assertEqual(verify_metric_snapshot(valid_snapshot()), ())

    def test_02_hash_tamper(self):
        snapshot = valid_snapshot()
        snapshot["actor"] = "different-actor"
        self.assertEqual(
            diagnose_metric_snapshot(snapshot),
            "METRIC_SNAPSHOT_HASH_MISMATCH",
        )

    def test_03_non_valid_cannot_carry_zero(self):
        self.assertIn(
            "METRIC_SNAPSHOT_NON_VALID_VALUE",
            checked(
                state="BLOCKED",
                value="0",
                value_type="MONEY",
                unit="MONEY",
                currency="RUB",
                reason_code="MISSING_COST",
            ),
        )

    def test_04_non_valid_requires_reason(self):
        self.assertIn(
            "METRIC_SNAPSHOT_NON_VALID_VALUE",
            checked(
                state="UNAVAILABLE",
                value=None,
                value_type=None,
                unit=None,
                currency=None,
                reason_code=None,
            ),
        )

    def test_05_actual_scenario_isolation(self):
        self.assertIn(
            "METRIC_SNAPSHOT_MODE_CONTAMINATION",
            checked(scenario_id="scenario-1"),
        )

    def test_06_naive_timestamp(self):
        self.assertIn(
            "METRIC_SNAPSHOT_TIMESTAMP_INVALID",
            checked(period_start="2026-06-01T00:00:00"),
        )

    def test_07_period_order(self):
        snapshot = valid_snapshot()
        snapshot["period_end"] = snapshot["period_start"]
        snapshot["content_hash"] = canonical_snapshot_hash(snapshot)
        self.assertIn(
            "METRIC_SNAPSHOT_PERIOD_INVALID",
            verify_metric_snapshot(snapshot),
        )

    def test_08_money_requires_currency(self):
        self.assertIn(
            "METRIC_SNAPSHOT_VALUE_INVALID",
            checked(currency=None),
        )

    def test_09_typed_values_locators_and_unhashable_enums(self):
        self.assertIn(
            "METRIC_SNAPSHOT_VALUE_INVALID",
            checked(value_type="INTEGER", value=True, unit="MONEY", currency=None),
        )
        for value_type in ("DECIMAL", "RATE"):
            for unit in ("MONEY", "MONEY_PER_ITEM"):
                self.assertIn(
                    "METRIC_SNAPSHOT_VALUE_INVALID",
                    checked(value_type=value_type, value="1.5", unit=unit, currency=None),
                )

        for field in (
            "marketplace_account_id",
            "prior_snapshot_id",
            "restates_snapshot_id",
        ):
            for value in ("", [], {}, 7, False):
                self.assertIn(
                    "METRIC_SNAPSHOT_MALFORMED",
                    checked(**{field: copy.deepcopy(value)}),
                )

        enum_cases = {
            "state": "METRIC_SNAPSHOT_STATE_INVALID",
            "value_type": "METRIC_SNAPSHOT_VALUE_INVALID",
            "unit": "METRIC_SNAPSHOT_VALUE_INVALID",
            "accounting_view": "METRIC_SNAPSHOT_ACCOUNTING_VIEW_INVALID",
            "data_freshness_state": "METRIC_SNAPSHOT_FRESHNESS_INVALID",
            "confidence_state": "METRIC_SNAPSHOT_CONFIDENCE_INVALID",
        }
        for field, diagnostic in enum_cases.items():
            for value in ([], {}):
                self.assertIn(
                    diagnostic,
                    checked(**{field: copy.deepcopy(value)}),
                )

        for value in ([], {}):
            snapshot = valid_snapshot()
            snapshot["expense_boundary"].append(copy.deepcopy(value))
            snapshot["content_hash"] = canonical_snapshot_hash(snapshot)
            self.assertIn(
                "METRIC_SNAPSHOT_EXPENSE_BOUNDARY_INVALID",
                verify_metric_snapshot(snapshot),
            )

    def test_10_unknown_expense_and_rounding_settings(self):
        snapshot = valid_snapshot()
        snapshot["expense_boundary"].append("FIXED_COST_MAGIC")
        snapshot["content_hash"] = canonical_snapshot_hash(snapshot)
        self.assertIn(
            "METRIC_SNAPSHOT_EXPENSE_BOUNDARY_INVALID",
            verify_metric_snapshot(snapshot),
        )

        for field, value in (
            ("application_point", "UNKNOWN_STAGE"),
            ("resolved_mode", "BANKERSISH"),
            ("application_point", []),
            ("resolved_mode", {}),
        ):
            snapshot = valid_snapshot()
            snapshot["rounding"][field] = copy.deepcopy(value)
            snapshot["content_hash"] = canonical_snapshot_hash(snapshot)
            self.assertIn(
                "METRIC_SNAPSHOT_ROUNDING_INVALID",
                verify_metric_snapshot(snapshot),
            )


if __name__ == "__main__":
    unittest.main()
