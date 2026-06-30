from __future__ import annotations

import unittest
from copy import deepcopy

import quantum.finance._rules_hardening as rules_hardening
from quantum.finance import (
    FinanceError,
    canonical_hash,
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

    def test_untrusted_unapproved_selection_is_rejected_before_status_lookup(self) -> None:
        draft_rule = rule_document(status="DRAFT")
        resolution = resolve_rule([draft_rule], context())
        candidate = resolution["candidates"][0]
        resolution["state"] = "VALID"
        resolution["diagnostic_code"] = None
        candidate["eligible"] = True
        candidate["selected"] = True
        candidate["exclusion_reasons"] = []
        candidate["ordering_tuple"] = [
            [1, 0, 0, 0, 0, 0],
            draft_rule["priority"],
            draft_rule["valid_from"],
            draft_rule["version"],
        ]
        resolution["trace_id"] = canonical_hash(
            resolution, exclude=frozenset({"trace_id"})
        )

        with self.assertRaisesRegex(
            FinanceError, "RULE_RESOLUTION_REPLAY_MISMATCH"
        ):
            evaluate_resolved_rule(
                resolution,
                [draft_rule],
                {},
                policy(),
            )

    def test_malformed_envelope_fields_fail_before_trust_lookup(self) -> None:
        rule = rule_document()
        original = resolve_rule([rule], context())
        malformed_cases = []

        bad_context_hash = deepcopy(original)
        bad_context_hash["context_hash"] = "x"
        malformed_cases.append(bad_context_hash)

        bad_actor = deepcopy(original)
        bad_actor["actor"] = ""
        malformed_cases.append(bad_actor)

        bad_resolved_at = deepcopy(original)
        bad_resolved_at["resolved_at"] = "not-a-date"
        malformed_cases.append(bad_resolved_at)

        bad_candidate = deepcopy(original)
        del bad_candidate["candidates"][0]["ordering_tuple"]
        malformed_cases.append(bad_candidate)

        for malformed in malformed_cases:
            malformed["trace_id"] = canonical_hash(
                malformed, exclude=frozenset({"trace_id"})
            )
            with self.subTest(malformed=malformed):
                with self.assertRaisesRegex(
                    FinanceError, "RULE_RESOLUTION_INVALID"
                ):
                    evaluate_resolved_rule(
                        malformed,
                        [rule],
                        {},
                        policy(),
                    )

    def test_submicrosecond_rfc3339_timestamps_are_rejected(self) -> None:
        with self.assertRaisesRegex(FinanceError, "RULE_VALIDITY_INVALID"):
            resolve_rule(
                [
                    rule_document(
                        valid_from="2026-06-30T00:00:00.0000001Z"
                    )
                ],
                context(
                    calculation_instant="2026-06-30T00:00:01Z"
                ),
            )

        with self.assertRaisesRegex(FinanceError, "RULE_CONTEXT_INVALID"):
            resolve_rule(
                [rule_document()],
                context(
                    calculation_instant="2026-06-30T00:00:00.0000001Z"
                ),
            )


if __name__ == "__main__":
    unittest.main()
