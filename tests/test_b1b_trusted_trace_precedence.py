from __future__ import annotations

import unittest

import quantum.finance._rules_hardening as rules_hardening
from quantum.finance import (
    FinanceError,
    evaluate_resolved_rule,
    resolve_rule,
)

from tests.b1b_helpers import context, policy, rule_document, typed


class B1bTrustedTracePrecedenceTests(unittest.TestCase):
    def test_changed_ruleset_is_rejected_before_reference_lookup(self) -> None:
        selected_rule = rule_document(rule_id="cost.selected", value="10")
        replacement_rule = rule_document(rule_id="cost.replacement", value="20")
        resolution = resolve_rule([selected_rule], context())

        with self.assertRaisesRegex(
            FinanceError, "RULE_RESOLUTION_REPLAY_MISMATCH"
        ):
            evaluate_resolved_rule(
                resolution,
                [replacement_rule],
                {},
                policy(),
            )

    def test_evicted_trace_is_rejected_before_variable_validation(self) -> None:
        expression = {
            "kind": "VARIABLE",
            "name": "gross_sales_amount",
            "value_type": "MONEY",
            "currency": "EUR",
            "unit": "MONEY",
        }
        rule = rule_document(method="SAFE_EXPRESSION", expression=expression)
        resolution = resolve_rule([rule], context())
        malformed_gross_sales = typed(
            "100",
            value_type="MONEY",
            unit="MONEY",
            currency="EUR",
        )
        malformed_gross_sales["source_ids"] = [[]]
        variables = {
            "gross_sales_amount": malformed_gross_sales,
            "tax_rate": typed("0.10", value_type="RATE", unit="RATE"),
        }

        with rules_hardening._TRUSTED_TRACE_LOCK:
            rules_hardening._TRUSTED_TRACES.pop(resolution["trace_id"], None)

        with self.assertRaisesRegex(
            FinanceError, "RULE_RESOLUTION_REPLAY_MISMATCH"
        ):
            evaluate_resolved_rule(
                resolution,
                [rule],
                variables,
                policy(),
            )


if __name__ == "__main__":
    unittest.main()
