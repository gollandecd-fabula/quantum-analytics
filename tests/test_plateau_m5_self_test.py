from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from quantum.application import desktop_center
from quantum.application._finance_center_self_test import (
    run_finance_center_self_test,
)


class PlateauM5SelfTestTests(unittest.TestCase):
    def _config(self, root: Path, *, ready: bool = True) -> Path:
        path = root / "config" / "default-home-local.json"
        path.parent.mkdir(parents=True)
        path.write_text(
            json.dumps(
                {
                    "configuration_status": (
                        "READY" if ready else "REQUIRES_USER_VALUES"
                    ),
                    "execution_mode": "ADMISSION_ONLY",
                    "tenant_id": "tenant-self-test",
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_finance_self_test_executes_known_answer_and_round_trip(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            result = run_finance_center_self_test(root, config)
        self.assertEqual("FINANCE_CENTER_SELF_TEST_PASS", result["status"])
        self.assertTrue(result["checks"]["known_answer_finance"])
        self.assertTrue(result["checks"]["runtime_mro"])
        self.assertTrue(result["checks"]["persistence_round_trip"])
        self.assertTrue(result["checks"]["schema_review_gate"])
        self.assertFalse(result["marketplace_write_enabled"])
        self.assertEqual(
            "680.00",
            result["diagnostics"]["known_answer_actual"][
                "net_profit_amount"
            ],
        )

    def test_invalid_config_forces_finance_self_test_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root, ready=False)
            result = run_finance_center_self_test(root, config)
        self.assertEqual(
            "FINANCE_CENTER_SELF_TEST_FAILED",
            result["status"],
        )
        self.assertFalse(result["checks"]["config_valid"])

    def test_desktop_cannot_report_pass_when_nested_test_failed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            with mock.patch(
                "quantum.application.local_runtime.self_test",
                return_value={
                    "status": "FINANCE_CENTER_SELF_TEST_FAILED",
                    "checks": {"known_answer_finance": False},
                },
            ):
                result = desktop_center.self_test(root, config)
        self.assertEqual(
            "DESKTOP_CENTER_SELF_TEST_FAILED",
            result["status"],
        )
        self.assertFalse(result["checks"]["finance_center"])

    def test_self_test_cli_returns_nonzero_on_failure(self) -> None:
        failed = {"status": "DESKTOP_CENTER_SELF_TEST_FAILED"}
        with mock.patch.object(
            desktop_center,
            "self_test",
            return_value=failed,
        ), mock.patch(
            "sys.argv",
            ["desktop_center", "--self-test"],
        ), mock.patch("builtins.print"):
            self.assertEqual(2, desktop_center.main())


if __name__ == "__main__":
    unittest.main()
