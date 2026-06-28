from __future__ import annotations

import unittest

from quantum.evidence import canonical_snapshot_hash, diagnose_metric_snapshot, verify_metric_snapshot
from quantum.evidence import verification as base_verification
from tests.b3_helpers import valid_snapshot


class B3MetricSnapshot(unittest.TestCase):
    def test_01_valid_zero(self):
        self.assertEqual(verify_metric_snapshot(valid_snapshot()), ())

    def test_02_hash_tamper(self):
        snapshot = valid_snapshot()
        snapshot["actor"] = "different-actor"
        self.assertEqual(diagnose_metric_snapshot(snapshot), "METRIC_SNAPSHOT_HASH_MISMATCH")

    def test_03_non_valid_cannot_carry_zero(self):
        snapshot = valid_snapshot()
        snapshot.update({
            "state": "BLOCKED", "value": "0", "value_type": "MONEY",
            "unit": "MONEY", "currency": "RUB", "reason_code": "MISSING_COST",
        })
        snapshot["content_hash"] = canonical_snapshot_hash(snapshot)
        self.assertIn("METRIC_SNAPSHOT_NON_VALID_VALUE", verify_metric_snapshot(snapshot))

    def test_04_non_valid_requires_reason(self):
        snapshot = valid_snapshot()
        snapshot.update({
            "state": "UNAVAILABLE", "value": None, "value_type": None,
            "unit": None, "currency": None, "reason_code": None,
        })
        snapshot["content_hash"] = canonical_snapshot_hash(snapshot)
        self.assertIn("METRIC_SNAPSHOT_NON_VALID_VALUE", verify_metric_snapshot(snapshot))

    def test_05_actual_scenario_isolation(self):
        snapshot = valid_snapshot()
        snapshot["scenario_id"] = "scenario-1"
        snapshot["content_hash"] = canonical_snapshot_hash(snapshot)
        self.assertIn("METRIC_SNAPSHOT_MODE_CONTAMINATION", verify_metric_snapshot(snapshot))

    def test_06_naive_timestamp(self):
        snapshot = valid_snapshot()
        snapshot["period_start"] = "2026-06-01T00:00:00"
        snapshot["content_hash"] = canonical_snapshot_hash(snapshot)
        self.assertIn("METRIC_SNAPSHOT_TIMESTAMP_INVALID", verify_metric_snapshot(snapshot))

    def test_07_period_order(self):
        snapshot = valid_snapshot()
        snapshot["period_end"] = snapshot["period_start"]
        snapshot["content_hash"] = canonical_snapshot_hash(snapshot)
        self.assertIn("METRIC_SNAPSHOT_PERIOD_INVALID", verify_metric_snapshot(snapshot))

    def test_08_money_requires_currency(self):
        snapshot = valid_snapshot()
        snapshot["currency"] = None
        snapshot["content_hash"] = canonical_snapshot_hash(snapshot)
        self.assertIn("METRIC_SNAPSHOT_VALUE_INVALID", verify_metric_snapshot(snapshot))

    def test_09_typed_values_and_optional_locators(self):
        integer = valid_snapshot()
        integer.update({
            "value_type": "INTEGER",
            "value": True,
            "unit": "MONEY",
            "currency": None,
        })
        integer["content_hash"] = canonical_snapshot_hash(integer)
        self.assertIn("METRIC_SNAPSHOT_VALUE_INVALID", verify_metric_snapshot(integer))
        self.assertIn(
            "METRIC_SNAPSHOT_VALUE_INVALID",
            base_verification.verify_metric_snapshot(integer),
        )

        for value_type in ("DECIMAL", "RATE"):
            for unit in ("MONEY", "MONEY_PER_ITEM"):
                with self.subTest(value_type=value_type, unit=unit):
                    snapshot = valid_snapshot()
                    snapshot.update({
                        "value_type": value_type,
                        "value": "1.5",
                        "unit": unit,
                        "currency": None,
                    })
                    snapshot["content_hash"] = canonical_snapshot_hash(snapshot)
                    self.assertIn(
                        "METRIC_SNAPSHOT_VALUE_INVALID",
                        verify_metric_snapshot(snapshot),
                    )
                    self.assertIn(
                        "METRIC_SNAPSHOT_VALUE_INVALID",
                        base_verification.verify_metric_snapshot(snapshot),
                    )

        invalid_locator_values = ("", [], {}, 7, False)
        for field in (
            "marketplace_account_id",
            "prior_snapshot_id",
            "restates_snapshot_id",
        ):
            for value in invalid_locator_values:
                with self.subTest(field=field, value=repr(value)):
                    snapshot = valid_snapshot()
                    snapshot[field] = value
                    snapshot["content_hash"] = canonical_snapshot_hash(snapshot)
                    self.assertIn(
                        "METRIC_SNAPSHOT_MALFORMED",
                        verify_metric_snapshot(snapshot),
                    )
                    self.assertIn(
                        "METRIC_SNAPSHOT_MALFORMED",
                        base_verification.verify_metric_snapshot(snapshot),
                    )

    def test_10_unknown_expense_and_rounding_settings(self):
        expense = valid_snapshot()
        expense["expense_boundary"].append("FIXED_COST_MAGIC")
        expense["content_hash"] = canonical_snapshot_hash(expense)
        self.assertIn(
            "METRIC_SNAPSHOT_EXPENSE_BOUNDARY_INVALID",
            verify_metric_snapshot(expense),
        )

        for field, value in (
            ("application_point", "UNKNOWN_STAGE"),
            ("resolved_mode", "BANKERSISH"),
        ):
            with self.subTest(field=field):
                snapshot = valid_snapshot()
                snapshot["rounding"][field] = value
                snapshot["content_hash"] = canonical_snapshot_hash(snapshot)
                self.assertIn(
                    "METRIC_SNAPSHOT_ROUNDING_INVALID",
                    verify_metric_snapshot(snapshot),
                )
                self.assertIn(
                    "METRIC_SNAPSHOT_ROUNDING_INVALID",
                    base_verification.verify_metric_snapshot(snapshot),
                )


if __name__ == "__main__":
    unittest.main()
