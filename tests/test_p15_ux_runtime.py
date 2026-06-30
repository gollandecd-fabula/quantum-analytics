from __future__ import annotations

import copy
import unittest
from datetime import UTC, datetime

from quantum.evidence import canonical_snapshot_hash
from quantum.ingestion import RawFileRecord, RawFileState
from quantum.reporting import build_report_record
from quantum.ux import (
    UXError,
    apply_configuration_values,
    build_configuration_form,
    build_exception_inbox,
    build_report_drilldown,
    render_import_status,
    render_report_record,
    validate_ux_hash,
)
from tests.b3_helpers import valid_snapshot


NOW = datetime(2026, 6, 30, 18, 0, tzinfo=UTC)
VALID_FROM = datetime(2026, 7, 1, 0, 0, tzinfo=UTC)
TENANT_ID = "tenant-synthetic"


class P15UXRuntimeTests(unittest.TestCase):
    def form(self, **overrides):
        values = {
            "form_id": "form-1",
            "organization_id": "org-synthetic",
            "mode": "ACTUAL",
            "scenario_id": None,
            "actor": "pilot-user",
            "scope": {"organization_id": "org-synthetic"},
            "valid_from": VALID_FROM,
            "valid_to": None,
            "currency": "RUB",
            "created_at": NOW,
        }
        values.update(overrides)
        return build_configuration_form(**values)

    @staticmethod
    def blocked_record(record_id: str = "report-blocked"):
        snapshot = valid_snapshot()
        snapshot.update({
            "metric_snapshot_id": "metric-blocked",
            "state": "BLOCKED",
            "value": None,
            "value_type": None,
            "unit": None,
            "currency": None,
            "reason_code": "CONFIGURATION_REQUIRED",
        })
        snapshot["content_hash"] = canonical_snapshot_hash(snapshot)
        return build_report_record(
            snapshot,
            report_record_id=record_id,
            generated_at=NOW,
        )

    @staticmethod
    def valid_record(record_id: str = "report-valid"):
        return build_report_record(
            valid_snapshot(),
            report_record_id=record_id,
            generated_at=NOW,
        )

    @staticmethod
    def integer_zero_record(record_id: str = "report-integer-zero"):
        snapshot = valid_snapshot()
        snapshot.update({
            "metric_snapshot_id": "metric-integer-zero",
            "value": 0,
            "value_type": "INTEGER",
            "unit": "COUNT",
            "currency": None,
        })
        snapshot["content_hash"] = canonical_snapshot_hash(snapshot)
        return build_report_record(
            snapshot,
            report_record_id=record_id,
            generated_at=NOW,
        )

    @staticmethod
    def raw_record(
        *,
        raw_file_id: str = "00000000-0000-4000-8000-000000000001",
        tenant_id: str = TENANT_ID,
        state: RawFileState = RawFileState.VALID,
        diagnostics: tuple[str, ...] = (),
    ) -> RawFileRecord:
        return RawFileRecord(
            raw_file_id=raw_file_id,
            tenant_id=tenant_id,
            sha256="a" * 64,
            size_bytes=128,
            sanitized_filename="synthetic.csv",
            storage_key=f"tenants/{tenant_id}/raw/{'a' * 64}",
            state=state,
            schema_id="wb-synthetic-v1" if state is RawFileState.VALID else None,
            structural_fingerprint={"columns": ["synthetic"]},
            semantic_fingerprint=None,
            diagnostics=diagnostics,
        )

    def test_new_form_contains_no_business_defaults(self) -> None:
        form = self.form(valid_from=None, currency=None)
        self.assertEqual(form["status"], "BLOCKED")
        self.assertIsNone(form["valid_from"])
        self.assertIsNone(form["currency"])
        for field in form["fields"]:
            self.assertIsNone(field["value"])
            self.assertEqual(field["state"], "EMPTY")

    def test_complete_explicit_configuration_is_ready_for_rule_draft(self) -> None:
        configured = apply_configuration_values(
            self.form(),
            {
                "cost": "400",
                "tax_rate": "0.06",
                "tax_base": "GROSS_SALES",
                "other_expense": "40",
            },
        )
        self.assertEqual(configured["status"], "READY_FOR_RULE_DRAFT")
        self.assertEqual(configured["publication_state"], "PREVIEW_ONLY")
        self.assertEqual({field["state"] for field in configured["fields"]}, {"VALID"})
        validate_ux_hash(configured, "form_hash")

    def test_partial_configuration_remains_partial_without_fallbacks(self) -> None:
        configured = apply_configuration_values(self.form(), {"cost": "400"})
        self.assertEqual(configured["status"], "PARTIAL")
        states = {field["field_id"]: field["state"] for field in configured["fields"]}
        self.assertEqual(states["cost"], "VALID")
        self.assertEqual(states["tax_rate"], "EMPTY")
        self.assertEqual(states["tax_base"], "EMPTY")
        self.assertEqual(states["other_expense"], "EMPTY")

    def test_numeric_zero_is_a_valid_explicit_input(self) -> None:
        configured = apply_configuration_values(
            self.form(),
            {
                "cost": "0",
                "tax_rate": "0",
                "tax_base": "NET_SALES",
                "other_expense": "0",
            },
        )
        values = {field["field_id"]: field["value"] for field in configured["fields"]}
        self.assertEqual(values["cost"], "0")
        self.assertEqual(values["other_expense"], "0")
        self.assertEqual(configured["status"], "READY_FOR_RULE_DRAFT")

    def test_invalid_decimal_fails_closed(self) -> None:
        configured = apply_configuration_values(self.form(), {"cost": "4e2"})
        cost = next(field for field in configured["fields"] if field["field_id"] == "cost")
        self.assertEqual(cost["state"], "INVALID")
        self.assertIsNone(cost["value"])
        self.assertEqual(configured["status"], "BLOCKED")

    def test_money_input_requires_explicit_currency(self) -> None:
        configured = apply_configuration_values(
            self.form(currency=None),
            {"cost": "400"},
        )
        cost = next(field for field in configured["fields"] if field["field_id"] == "cost")
        self.assertEqual(cost["state"], "BLOCKED")
        self.assertEqual(cost["diagnostic"], "CURRENCY_REQUIRED")

    def test_tax_base_uses_closed_vocabulary(self) -> None:
        configured = apply_configuration_values(
            self.form(),
            {"tax_base": "UNVERIFIED_PAYOUT_GUESS"},
        )
        tax_base = next(
            field for field in configured["fields"] if field["field_id"] == "tax_base"
        )
        self.assertEqual(tax_base["state"], "INVALID")
        self.assertEqual(tax_base["diagnostic"], "TAX_BASE_INVALID")

    def test_scope_rejects_product_and_group_overlap(self) -> None:
        with self.assertRaisesRegex(UXError, "UX_SCOPE_PRODUCT_AMBIGUOUS"):
            self.form(scope={
                "organization_id": "org-synthetic",
                "product_id": "product-1",
                "product_group_id": "group-1",
            })

    def test_actual_mode_rejects_scenario(self) -> None:
        with self.assertRaisesRegex(UXError, "UX_SCENARIO_INVALID"):
            self.form(scenario_id="scenario-1")

    def test_scenario_scope_must_match(self) -> None:
        with self.assertRaisesRegex(UXError, "UX_SCOPE_SCENARIO_MISMATCH"):
            self.form(
                mode="SCENARIO",
                scenario_id="scenario-1",
                scope={
                    "organization_id": "org-synthetic",
                    "scenario_id": "scenario-2",
                },
            )

    def test_form_shape_tampering_fails_closed(self) -> None:
        form = self.form()
        form["fields"][0]["field_id"] = "hidden_cost"
        with self.assertRaisesRegex(UXError, "UX_FORM_FIELDS_INVALID"):
            apply_configuration_values(form, {})

    def test_valid_zero_has_distinct_accessible_rendering(self) -> None:
        view = render_report_record(self.valid_record())
        self.assertEqual(view["state"], "VALID")
        self.assertTrue(view["is_numeric_zero"])
        self.assertEqual(view["status_label"], "Valid numeric zero")
        self.assertEqual(view["semantic_role"], "status")
        validate_ux_hash(view, "view_hash")

    def test_integer_zero_has_distinct_accessible_rendering(self) -> None:
        view = render_report_record(self.integer_zero_record())
        self.assertTrue(view["is_numeric_zero"])
        self.assertEqual(view["value_text"], "0")
        self.assertEqual(view["accessible_summary"], "Valid result with numeric value zero.")

    def test_blocked_result_never_renders_as_zero(self) -> None:
        view = render_report_record(self.blocked_record())
        self.assertEqual(view["state"], "BLOCKED")
        self.assertFalse(view["is_numeric_zero"])
        self.assertEqual(view["value_text"], "—")
        self.assertEqual(view["status_label"], "Blocked")

    def test_preview_drilldown_cannot_claim_verified_evidence(self) -> None:
        drilldown = build_report_drilldown(self.valid_record())
        self.assertEqual(drilldown["verification_status"], "PREVIEW_ONLY")
        self.assertFalse(drilldown["can_claim_verified_evidence"])
        self.assertIsNone(drilldown["evidence_chain_content_hash"])

    def test_valid_import_status_is_accessible_and_hides_storage_key(self) -> None:
        view = render_import_status(self.raw_record())
        self.assertEqual(view["state"], "VALID")
        self.assertEqual(view["semantic_role"], "status")
        self.assertTrue(view["admitted_to_canonical_processing"])
        self.assertNotIn("storage_key", view)
        validate_ux_hash(view, "view_hash")

    def test_quarantined_import_status_is_not_admitted(self) -> None:
        record = self.raw_record(
            state=RawFileState.QUARANTINED,
            diagnostics=("SCHEMA_UNKNOWN",),
        )
        view = render_import_status(record)
        self.assertEqual(view["status_label"], "Quarantined")
        self.assertFalse(view["admitted_to_canonical_processing"])
        self.assertEqual(view["diagnostics"], ["SCHEMA_UNKNOWN"])

    def test_exception_inbox_preserves_independent_valid_metric(self) -> None:
        valid = self.valid_record()
        blocked = self.blocked_record()
        inbox = build_exception_inbox([valid, blocked], generated_at=NOW)
        self.assertTrue(inbox["independent_results_preserved"])
        self.assertEqual(inbox["available_metric_ids"], [valid["metric_snapshot_id"]])
        self.assertEqual(inbox["exception_count"], 1)
        self.assertEqual(inbox["exceptions"][0]["cause"], "CONFIGURATION_REQUIRED")
        validate_ux_hash(inbox, "inbox_hash")

    def test_configuration_exceptions_include_required_resolution(self) -> None:
        form = apply_configuration_values(self.form(valid_from=None), {"cost": "400"})
        inbox = build_exception_inbox(
            [self.valid_record()],
            configuration_forms=[form],
            generated_at=NOW,
        )
        causes = {item["cause"] for item in inbox["exceptions"]}
        self.assertIn("VALID_FROM_REQUIRED", causes)
        self.assertIn("CONFIGURATION_REQUIRED", causes)
        self.assertTrue(all(item["required_resolution"] for item in inbox["exceptions"]))

    def test_quarantined_import_appears_as_schema_exception(self) -> None:
        quarantined = self.raw_record(
            state=RawFileState.QUARANTINED,
            diagnostics=("SCHEMA_UNKNOWN",),
        )
        inbox = build_exception_inbox(
            [],
            import_records=[quarantined],
            tenant_id=TENANT_ID,
            generated_at=NOW,
        )
        self.assertEqual(inbox["organization_id"], None)
        self.assertEqual(inbox["exception_count"], 1)
        self.assertEqual(inbox["exceptions"][0]["category"], "SCHEMA")
        self.assertEqual(inbox["exceptions"][0]["cause"], "SCHEMA_UNKNOWN")

    def test_import_exception_requires_explicit_tenant(self) -> None:
        with self.assertRaisesRegex(UXError, "UX_INBOX_TENANT_REQUIRED"):
            build_exception_inbox(
                [],
                import_records=[self.raw_record(state=RawFileState.REJECTED)],
                generated_at=NOW,
            )

    def test_import_exception_rejects_cross_tenant_record(self) -> None:
        with self.assertRaisesRegex(UXError, "UX_INBOX_TENANT_MIXED"):
            build_exception_inbox(
                [],
                import_records=[self.raw_record(tenant_id="other-tenant")],
                tenant_id=TENANT_ID,
                generated_at=NOW,
            )

    def test_exception_inbox_rejects_mixed_organizations(self) -> None:
        other_snapshot = valid_snapshot()
        other_snapshot["organization_id"] = "other-org"
        other_snapshot["metric_snapshot_id"] = "metric-other"
        other_snapshot["content_hash"] = canonical_snapshot_hash(other_snapshot)
        other = build_report_record(
            other_snapshot,
            report_record_id="report-other",
            generated_at=NOW,
        )
        with self.assertRaisesRegex(UXError, "UX_INBOX_ORGANIZATION_MIXED"):
            build_exception_inbox([self.valid_record(), other], generated_at=NOW)

    def test_exception_inbox_rejects_duplicate_records(self) -> None:
        record = self.valid_record()
        with self.assertRaisesRegex(UXError, "UX_INBOX_RECORD_DUPLICATE"):
            build_exception_inbox([record, record], generated_at=NOW)

    def test_hash_tampering_is_rejected(self) -> None:
        view = render_report_record(self.valid_record())
        tampered = copy.deepcopy(view)
        tampered["status_label"] = "Hidden zero"
        with self.assertRaisesRegex(UXError, "UX_HASH_MISMATCH"):
            validate_ux_hash(tampered, "view_hash")

    def test_unknown_configuration_input_is_rejected(self) -> None:
        with self.assertRaisesRegex(UXError, "UX_CONFIGURATION_VALUES_INVALID"):
            apply_configuration_values(self.form(), {"hidden_default": "40"})


if __name__ == "__main__":
    unittest.main()
