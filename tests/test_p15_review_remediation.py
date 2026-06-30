from __future__ import annotations

import unittest
from datetime import UTC, datetime

from quantum.evidence import canonical_snapshot_hash
from quantum.ingestion import RawFileRecord, RawFileState
from quantum.reporting import build_report_record
from quantum.ux import (
    UXError,
    build_configuration_form,
    build_exception_inbox,
    render_import_status,
    render_report_record,
    validate_ux_hash,
)
from tests.b3_helpers import valid_snapshot


NOW = datetime(2026, 6, 30, 21, 0, tzinfo=UTC)
TENANT_ID = "tenant-review-remediation"


def report_with_value(value: str):
    snapshot = valid_snapshot()
    snapshot["metric_snapshot_id"] = f"metric-zero-{value}"
    snapshot["value"] = value
    snapshot["content_hash"] = canonical_snapshot_hash(snapshot)
    return build_report_record(
        snapshot,
        report_record_id=f"report-zero-{value}",
        generated_at=NOW,
    )


def configuration_form(*, form_id: str, actor: str):
    return build_configuration_form(
        form_id=form_id,
        organization_id="org-synthetic",
        mode="ACTUAL",
        scenario_id=None,
        actor=actor,
        scope={"organization_id": "org-synthetic"},
        valid_from=NOW,
        valid_to=None,
        currency="RUB",
        created_at=NOW,
    )


def quarantined_record(raw_file_id: str) -> RawFileRecord:
    digest = "f" * 64
    return RawFileRecord(
        raw_file_id=raw_file_id,
        tenant_id=TENANT_ID,
        sha256=digest,
        size_bytes=64,
        sanitized_filename="review.csv",
        storage_key=f"tenants/{TENANT_ID}/raw/{digest}",
        state=RawFileState.QUARANTINED,
        schema_id=None,
        structural_fingerprint={"columns": ["unknown"]},
        semantic_fingerprint=None,
        diagnostics=("SCHEMA_UNKNOWN",),
    )


class P15ReviewRemediationTests(unittest.TestCase):
    def test_decimal_zero_variants_render_as_valid_zero(self) -> None:
        for value in ("0.0", "0.00", "-0", "-0.00"):
            with self.subTest(value=value):
                view = render_report_record(report_with_value(value))
                self.assertTrue(view["is_numeric_zero"])
                self.assertEqual(view["status_token"], "valid-zero")
                self.assertEqual(view["status_label"], "Valid numeric zero")
                self.assertEqual(
                    view["accessible_summary"],
                    "Valid result with numeric value zero.",
                )
                self.assertEqual(view["value_text"], value)
                validate_ux_hash(view, "view_hash")

    def test_duplicate_configuration_form_ids_fail_closed(self) -> None:
        first = configuration_form(form_id="form-duplicate", actor="actor-a")
        second = configuration_form(form_id="form-duplicate", actor="actor-b")
        with self.assertRaisesRegex(UXError, "UX_INBOX_FORM_DUPLICATE"):
            build_exception_inbox(
                [],
                configuration_forms=[first, second],
                generated_at=NOW,
            )

    def test_empty_tenant_id_is_rejected_without_import_records(self) -> None:
        with self.assertRaisesRegex(UXError, "UX_INBOX_TENANT_REQUIRED"):
            build_exception_inbox(
                [report_with_value("0")],
                tenant_id="",
                generated_at=NOW,
            )

    def test_noncanonical_raw_file_uuid_is_rejected(self) -> None:
        canonical = "00000000-0000-4000-8000-000000000041"
        variants = (
            canonical.upper(),
            canonical.replace("-", "").upper(),
        )
        for raw_file_id in variants:
            with self.subTest(raw_file_id=raw_file_id):
                with self.assertRaisesRegex(UXError, "UX_IMPORT_RECORD_INVALID"):
                    render_import_status(quarantined_record(raw_file_id))

    def test_non_rfc3339_timestamp_strings_are_rejected(self) -> None:
        noncanonical = "2026-06-30 21:00:00+00:00"
        with self.subTest(field="created_at"):
            with self.assertRaisesRegex(UXError, "UX_CREATED_AT_INVALID"):
                build_configuration_form(
                    form_id="form-bad-created-at",
                    organization_id="org-synthetic",
                    mode="ACTUAL",
                    scenario_id=None,
                    actor="actor-a",
                    scope={"organization_id": "org-synthetic"},
                    valid_from=NOW,
                    valid_to=None,
                    currency="RUB",
                    created_at=noncanonical,
                )
        with self.subTest(field="valid_from"):
            with self.assertRaisesRegex(UXError, "UX_VALID_FROM_INVALID"):
                build_configuration_form(
                    form_id="form-bad-valid-from",
                    organization_id="org-synthetic",
                    mode="ACTUAL",
                    scenario_id=None,
                    actor="actor-a",
                    scope={"organization_id": "org-synthetic"},
                    valid_from=noncanonical,
                    valid_to=None,
                    currency="RUB",
                    created_at=NOW,
                )
        with self.subTest(field="generated_at"):
            with self.assertRaisesRegex(UXError, "UX_INBOX_TIMESTAMP_INVALID"):
                build_exception_inbox(
                    [report_with_value("0")],
                    generated_at=noncanonical,
                )


if __name__ == "__main__":
    unittest.main()
