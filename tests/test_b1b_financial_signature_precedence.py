from __future__ import annotations

import unittest

from quantum.finance import calculate

from tests.b1b_helpers import load_baseline, request_from_case, typed


class B1bFinancialSignaturePrecedenceTests(unittest.TestCase):
    def baseline_request(self) -> dict:
        return request_from_case(load_baseline()["cases"][0])

    def test_invalid_nonvalid_other_expense_signature_beats_unavailable_state(self) -> None:
        request = self.baseline_request()
        request["other_expense_components"][0]["value"] = typed(
            None,
            value_type="RATE",
            unit="RATE",
            state="UNAVAILABLE",
            reason_code="EXPENSE_SOURCE_UNAVAILABLE",
        )

        result = calculate(request)["results"]["other_expense_amount"]
        self.assertEqual(result["state"], "BLOCKED")
        self.assertEqual(
            result["reason_code"], "OTHER_EXPENSE_SIGNATURE_MISMATCH"
        )

    def test_invalid_nonvalid_tax_signatures_beat_unavailable_state(self) -> None:
        request = self.baseline_request()
        request["tax_rate"] = typed(
            None,
            value_type="DECIMAL",
            unit="DIMENSIONLESS",
            state="UNAVAILABLE",
            reason_code="TAX_RATE_SOURCE_UNAVAILABLE",
        )
        result = calculate(request)["results"]["tax_amount"]
        self.assertEqual(result["state"], "BLOCKED")
        self.assertEqual(result["reason_code"], "TAX_RULE_SIGNATURE_MISMATCH")

        request = self.baseline_request()
        request["inputs"]["custom_tax_base"] = typed(
            None,
            value_type="MONEY",
            unit="MONEY",
            currency="RUB",
            state="UNAVAILABLE",
            reason_code="TAX_BASE_SOURCE_UNAVAILABLE",
        )
        request["tax_base_metric_id"] = "custom_tax_base"
        result = calculate(request)["results"]["tax_amount"]
        self.assertEqual(result["state"], "BLOCKED")
        self.assertEqual(result["reason_code"], "TAX_RULE_SIGNATURE_MISMATCH")


if __name__ == "__main__":
    unittest.main()
