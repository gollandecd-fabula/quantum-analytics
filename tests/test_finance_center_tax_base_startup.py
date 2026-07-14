from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from quantum.application import _finance_center_reports as reports
from quantum.application.finance_profile import FinanceProfile, TAX_BASE_OPTIONS


class _DummyText:
    def __init__(self) -> None:
        self.value = ""
        self.state = ""

    def configure(self, *, state: str) -> None:
        self.state = state

    def delete(self, _start: str, _end: str) -> None:
        self.value = ""

    def insert(self, _start: str, value: str) -> None:
        self.value = value


class FinanceCenterTaxBaseStartupTests(unittest.TestCase):
    def test_reports_module_receives_tax_base_options_from_shared_import(self) -> None:
        self.assertIs(reports.TAX_BASE_OPTIONS, TAX_BASE_OPTIONS)

    def test_refresh_finance_summary_renders_selected_tax_base(self) -> None:
        center = reports.FinanceCenterReportsMixin()
        center.profile = FinanceProfile(
            tax_rate_percent="6",
            tax_base_metric_id="gross_sales_amount",
            other_expense_per_unit="40",
        )
        center.finance_summary = _DummyText()
        center.refresh_cards = lambda: None

        tkinter_stub = SimpleNamespace(NORMAL="normal", DISABLED="disabled", END="end")
        with patch.object(reports, "tk", tkinter_stub):
            center.refresh_finance_summary()

        self.assertIn("Налоговая база:", center.finance_summary.value)
        self.assertIn(
            TAX_BASE_OPTIONS["gross_sales_amount"],
            center.finance_summary.value,
        )
        self.assertEqual(center.finance_summary.state, "disabled")


if __name__ == "__main__":
    unittest.main()
