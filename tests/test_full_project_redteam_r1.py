from __future__ import annotations

import ast
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from quantum.application._finance_center_shared import bounded_window_geometry
from quantum.application.finance_profile import (
    FinanceProfile,
    FinanceProfileError,
    ProductRecord,
    TAX_BASE_OPTIONS,
    backup_corrupt_profile,
    build_profile,
    confirm_profile,
    load_profile,
    save_profile,
)

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src/quantum/application"


def complete_profile() -> FinanceProfile:
    profile = build_profile(
        (ProductRecord("SKU-1", "Товар", "Группа", "fixture"),)
    )
    profile.tax_rate_percent = "7.25"
    profile.tax_base_metric_id = "gross_sales_amount"
    profile.other_expense_per_unit = "13.40"
    group = profile.groups["Группа"]
    group.cost_per_unit = "412.33"
    group.resalable_returned_units = "0"
    group.compensated_returned_units = "0"
    group.return_compensation_amount = "0"
    group.discounts_amount = "0"
    group.subsidies_amount = "0"
    group.advertising_amount = "0"
    return profile


class FullProjectRedTeamR1Tests(unittest.TestCase):
    def test_window_geometry_never_exceeds_screen(self) -> None:
        for screen_width, screen_height in (
            (800, 600),
            (1024, 768),
            (1366, 768),
            (1920, 1080),
        ):
            geometry, minimum = bounded_window_geometry(
                screen_width,
                screen_height,
                1440,
                900,
                760,
                560,
            )
            dimensions, x_text, y_text = geometry.split("+")
            width, height = map(int, dimensions.split("x"))
            self.assertLessEqual(width, screen_width)
            self.assertLessEqual(height, screen_height)
            self.assertGreaterEqual(int(x_text), 0)
            self.assertGreaterEqual(int(y_text), 0)
            self.assertLessEqual(minimum[0], width)
            self.assertLessEqual(minimum[1], height)

    def test_dialog_uses_staged_profile_and_explicit_cancel(self) -> None:
        source = (APP / "_finance_center_dialog.py").read_text(encoding="utf-8")
        self.assertIn(
            "self.profile = FinanceProfile.from_dict(profile.to_dict())",
            source,
        )
        self.assertNotIn("self.profile = profile\n", source)
        self.assertIn('command=self._cancel', source)
        self.assertIn('self.window.bind("<Escape>", self._cancel)', source)
        self.assertIn("self._reopen_staged()", source)
        self.assertIn("self.owner.profile = self.profile", source)

    def test_staged_profile_mutation_does_not_touch_owner_profile(self) -> None:
        owner = complete_profile()
        staged = FinanceProfile.from_dict(owner.to_dict())
        staged.tax_rate_percent = "19"
        staged.groups["Группа"].cost_per_unit = "999"
        staged.product_to_group["SKU-1"] = "Другая"
        self.assertEqual(owner.tax_rate_percent, "7.25")
        self.assertEqual(owner.groups["Группа"].cost_per_unit, "412.33")
        self.assertEqual(owner.product_to_group["SKU-1"], "Группа")

    def test_profile_values_are_user_data_not_business_defaults(self) -> None:
        profile = FinanceProfile()
        self.assertIsNone(profile.tax_rate_percent)
        self.assertIsNone(profile.tax_base_metric_id)
        self.assertIsNone(profile.other_expense_per_unit)
        profile = build_profile(
            (ProductRecord("SKU", "Товар", "Группа", "fixture"),)
        )
        self.assertIsNone(profile.groups["Группа"].cost_per_unit)

        forbidden_assignments: list[str] = []
        for path in APP.glob("*.py"):
            if path.name == "_finance_center_self_test.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                    continue
                value = getattr(node, "value", None)
                if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
                    continue
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Attribute) and target.attr in {
                        "tax_rate_percent",
                        "tax_base_metric_id",
                        "other_expense_per_unit",
                        "cost_per_unit",
                    } and value.value.strip():
                        forbidden_assignments.append(
                            f"{path.name}:{target.attr}={value.value!r}"
                        )
        self.assertEqual(forbidden_assignments, [])

    def test_all_required_finance_inputs_are_visible_in_dialog_source(self) -> None:
        source = (APP / "_finance_center_dialog.py").read_text(encoding="utf-8")
        source += (APP / "_finance_center_shared.py").read_text(encoding="utf-8")
        for text in (
            "Налоговая ставка, %",
            "Налоговая база",
            "Прочие расходы на проданную единицу, ₽",
            "Себестоимость группы, ₽",
            "Возвраты, пригодные к повторной продаже, шт.",
            "Компенсированные возвраты, шт.",
            "Компенсации возвратов, ₽",
            "Скидки вне отчёта, ₽",
            "Субсидии вне отчёта, ₽",
            "Реклама вне отчёта, ₽",
        ):
            self.assertIn(text, source)
        self.assertGreaterEqual(len(TAX_BASE_OPTIONS), 2)

    def test_invalid_required_values_fail_closed_and_explicit_zero_is_valid(self) -> None:
        for invalid in (None, "", "-1", "NaN", "Infinity", "abc"):
            with self.subTest(invalid=invalid):
                profile = complete_profile()
                profile.other_expense_per_unit = invalid
                with self.assertRaises(FinanceProfileError):
                    confirm_profile(profile)
        profile = complete_profile()
        profile.tax_rate_percent = "101"
        with self.assertRaises(FinanceProfileError):
            confirm_profile(profile)
        profile = complete_profile()
        profile.tax_rate_percent = "0"
        profile.other_expense_per_unit = "0"
        profile.groups["Группа"].cost_per_unit = "0"
        confirm_profile(profile)
        self.assertTrue(profile.confirmed)

    def test_profile_round_trip_is_atomic_and_uses_user_values(self) -> None:
        profile = complete_profile()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config" / "finance-profile.json"
            save_profile(path, profile)
            loaded = load_profile(path)
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.tax_rate_percent, "7.25")
            self.assertEqual(loaded.other_expense_per_unit, "13.40")
            self.assertEqual(
                loaded.groups["Группа"].cost_per_unit,
                "412.33",
            )
            leftovers = list(path.parent.glob(f".{path.name}.*.tmp"))
            self.assertEqual(leftovers, [])

    def test_corrupt_profile_is_moved_to_backup_without_data_loss(self) -> None:
        payload = b"{corrupt-profile:\xff"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "finance-profile.json"
            path.write_bytes(payload)
            with self.assertRaises(FinanceProfileError):
                load_profile(path)
            backup = backup_corrupt_profile(path)
            self.assertFalse(path.exists())
            self.assertTrue(backup.is_file())
            self.assertEqual(backup.read_bytes(), payload)

    def test_oversized_profile_is_rejected_without_unbounded_parse(self) -> None:
        import quantum.application.finance_profile as module

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "finance-profile.json"
            path.write_bytes(b" " * (module._PROFILE_MAX_BYTES + 1))
            with self.assertRaisesRegex(
                FinanceProfileError,
                "FINANCE_PROFILE_TOO_LARGE",
            ):
                load_profile(path)

    def test_backup_failure_is_typed_and_original_remains(self) -> None:
        payload = b"broken"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "finance-profile.json"
            path.write_bytes(payload)
            with patch(
                "quantum.application.finance_profile._replace_with_retry",
                side_effect=OSError("denied"),
            ):
                with self.assertRaisesRegex(
                    FinanceProfileError,
                    "FINANCE_PROFILE_BACKUP_FAILED",
                ):
                    backup_corrupt_profile(path)
            self.assertEqual(path.read_bytes(), payload)

    def test_only_one_profile_persistence_implementation_remains(self) -> None:
        groups = (APP / "_finance_profile_groups.py").read_text(encoding="utf-8")
        top = (APP / "finance_profile.py").read_text(encoding="utf-8")
        self.assertNotIn("def _atomic_json(", groups)
        self.assertNotIn("def save_profile(", groups)
        self.assertNotIn("def load_profile(", groups)
        self.assertEqual(top.count("def save_profile("), 1)
        self.assertEqual(top.count("def load_profile("), 1)

    def test_shell_recovers_corrupt_profile_fail_closed(self) -> None:
        source = (APP / "_finance_center_shell.py").read_text(encoding="utf-8")
        self.assertIn("except FinanceProfileError as exc:", source)
        self.assertIn("backup_corrupt_profile", source)
        self.assertIn("self.profile_save_blocked = True", source)
        reports = (APP / "_finance_center_reports.py").read_text(encoding="utf-8")
        self.assertIn("if self.profile_save_blocked:", reports)

    def test_unconfigured_template_is_distinct_from_technical_failure(self) -> None:
        from quantum.application.desktop_center import self_test as desktop_self_test

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config.json"
            config.write_text(
                json.dumps(
                    {
                        "configuration_status": "REQUIRES_USER_VALUES",
                        "tenant_id": "tenant-test",
                        "execution_mode": "ADMISSION_ONLY",
                    }
                ),
                encoding="utf-8",
            )
            result = desktop_self_test(root, config)
        self.assertEqual(
            result["status"],
            "DESKTOP_CENTER_SELF_TEST_CONFIGURATION_REQUIRED",
        )
        self.assertEqual(
            result["finance_center"]["status"],
            "FINANCE_CENTER_SELF_TEST_CONFIGURATION_REQUIRED",
        )

    def test_ready_configuration_still_passes_self_test(self) -> None:
        from quantum.application.desktop_center import self_test as desktop_self_test

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config.json"
            config.write_text(
                json.dumps(
                    {
                        "configuration_status": "READY",
                        "tenant_id": "tenant-test",
                        "execution_mode": "ADMISSION_ONLY",
                    }
                ),
                encoding="utf-8",
            )
            result = desktop_self_test(root, config)
        self.assertEqual(result["status"], "DESKTOP_CENTER_SELF_TEST_PASS")


if __name__ == "__main__":
    unittest.main()
