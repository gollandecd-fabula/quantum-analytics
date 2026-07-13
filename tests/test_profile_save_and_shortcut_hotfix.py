from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from quantum.application.finance_profile import (
    FinanceProfileError,
    ProductRecord,
    build_profile,
    load_profile,
    save_profile,
)
from quantum.application import shortcut_repair


class FinanceProfileSaveHotfixTests(unittest.TestCase):
    def _profile(self):
        profile = build_profile(
            (ProductRecord("SKU-1", "Товар", "Группа", "report.xlsx"),)
        )
        profile.tax_rate_percent = "6"
        profile.other_expense_per_unit = "40"
        profile.groups["Группа"].cost_per_unit = "400"
        return profile

    def test_save_profile_round_trips_and_commits_only_after_replace(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "config" / "finance-profile.json"
            profile = self._profile()
            save_profile(path, profile)
            loaded = load_profile(path)

        self.assertIsNotNone(loaded)
        self.assertTrue(profile.confirmed)
        self.assertEqual(profile.tax_rate_percent, "6")
        self.assertEqual(profile.other_expense_per_unit, "40.00")
        self.assertEqual(profile.groups["Группа"].cost_per_unit, "400.00")
        self.assertTrue(loaded.confirmed)
        self.assertEqual(loaded.to_dict(), profile.to_dict())

    def test_failed_replace_preserves_previous_file_and_unconfirmed_memory(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "finance-profile.json"
            original = {"sentinel": "preserve"}
            path.write_text(json.dumps(original), encoding="utf-8")
            profile = self._profile()
            with mock.patch(
                "quantum.application.finance_profile._os.replace",
                side_effect=PermissionError("locked"),
            ), mock.patch(
                "quantum.application.finance_profile._time.sleep"
            ):
                with self.assertRaises(FinanceProfileError) as raised:
                    save_profile(path, profile)

            self.assertEqual(raised.exception.code, "FINANCE_PROFILE_WRITE_FAILED")
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")),
                original,
            )
            self.assertFalse(profile.confirmed)
            self.assertEqual(profile.tax_rate_percent, "6")
            self.assertEqual(profile.other_expense_per_unit, "40")
            self.assertEqual(profile.groups["Группа"].cost_per_unit, "400")
            self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_transient_windows_replace_lock_is_retried(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "finance-profile.json"
            profile = self._profile()
            real_replace = os.replace
            calls = []

            def flaky_replace(source, target):
                calls.append((source, target))
                if len(calls) == 1:
                    raise PermissionError("transient lock")
                return real_replace(source, target)

            with mock.patch(
                "quantum.application.finance_profile._os.replace",
                side_effect=flaky_replace,
            ), mock.patch(
                "quantum.application.finance_profile._time.sleep"
            ) as sleep:
                save_profile(path, profile)

            self.assertEqual(len(calls), 2)
            sleep.assert_called_once()
            self.assertTrue(path.is_file())
            self.assertTrue(profile.confirmed)


class ShortcutRepairHotfixTests(unittest.TestCase):
    def test_non_windows_is_side_effect_free(self) -> None:
        with tempfile.TemporaryDirectory() as raw, mock.patch.object(
            shortcut_repair.sys,
            "platform",
            "linux",
        ), mock.patch.object(shortcut_repair.subprocess, "run") as run:
            result = shortcut_repair.repair_legacy_shortcuts(Path(raw))

        self.assertEqual(
            result["status"],
            "SHORTCUT_REPAIR_SKIPPED_NON_WINDOWS",
        )
        run.assert_not_called()

    def test_windows_repair_runs_hidden_and_targets_current_launcher(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            launcher = root / "START_QUANTUM.cmd"
            launcher.write_text("@echo off\r\n", encoding="ascii")
            completed = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout='{"status":"SHORTCUT_REPAIR_PASS"}',
                stderr="",
            )
            with mock.patch.object(
                shortcut_repair.sys,
                "platform",
                "win32",
            ), mock.patch.object(
                shortcut_repair.subprocess,
                "run",
                return_value=completed,
            ) as run:
                result = shortcut_repair.repair_legacy_shortcuts(root)

            self.assertEqual(result["status"], "SHORTCUT_REPAIR_PASS")
            arguments = run.call_args.args[0]
            self.assertIn("-EncodedCommand", arguments)
            self.assertEqual(
                run.call_args.kwargs["creationflags"],
                getattr(shortcut_repair.subprocess, "CREATE_NO_WINDOW", 0),
            )
            environment = run.call_args.kwargs["env"]
            self.assertEqual(
                Path(environment["QUANTUM_SHORTCUT_LAUNCHER"]),
                launcher,
            )
            report = json.loads(
                (root / "output" / "shortcut_repair_latest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(report["status"], "SHORTCUT_REPAIR_PASS")

    def test_repair_contract_covers_stale_localhost_and_url_shortcuts(self) -> None:
        script = shortcut_repair._POWERSHELL_SCRIPT
        self.assertIn("localhost:8000", script)
        self.assertIn('Filter "*.lnk"', script)
        self.assertIn('Filter "*.url"', script)
        self.assertIn(".disabled_", script)
        self.assertIn("Quantum Analytics", script)
        self.assertIn("Set-QuantumLink", script)


if __name__ == "__main__":
    unittest.main()
