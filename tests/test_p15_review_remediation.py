from __future__ import annotations

import unittest
from datetime import UTC, datetime

from quantum.evidence import canonical_snapshot_hash
from quantum.reporting import build_report_record
from quantum.ux import (
    UXError,
    build_configuration_form,
    build_exception_inbox,
    render_report_record,
    validate_ux_hash,
)
from tests.b3_helpers import valid_snapshot


NOW = datetime(2026, 6, 30, 21, 0, tzinfo=UTC)


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


if __name__ == "__main__":
    unittest.main()
