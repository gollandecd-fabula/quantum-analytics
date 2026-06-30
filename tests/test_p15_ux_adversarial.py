from __future__ import annotations

import copy
import unittest
from datetime import UTC, datetime

from quantum.evidence import canonical_snapshot_hash
from quantum.ingestion import RawFileRecord, RawFileState
from quantum.reporting import ReportingError, build_report_record
from quantum.ux import (
    UXError,
    apply_configuration_values,
    build_configuration_form,
    build_exception_inbox,
    build_report_drilldown,
    render_import_status,
    render_report_record,
)
from tests.b3_helpers import valid_snapshot


NOW = datetime(2026, 6, 30, 19, 0, tzinfo=UTC)
VALID_FROM = datetime(2026, 7, 1, 0, 0, tzinfo=UTC)
TENANT_ID = "tenant-adversarial"


def valid_form():
    return build_configuration_form(
        form_id="form-adversarial",
        organization_id="org-synthetic",
        mode="ACTUAL",
        scenario_id=None,
        actor="pilot-user",
        scope={"organization_id": "org-synthetic"},
        valid_from=VALID_FROM,
        valid_to=None,
        currency="RUB",
        created_at=NOW,
    )


def report_record(*, record_id: str, mode: str = "ACTUAL", scenario_id=None):
    snapshot = valid_snapshot()
    snapshot["metric_snapshot_id"] = f"metric-{record_id}"
    snapshot["mode"] = mode
    snapshot["scenario_id"] = scenario_id
    snapshot["content_hash"] = canonical_snapshot_hash(snapshot)
    return build_report_record(
        snapshot,
        report_record_id=record_id,
        generated_at=NOW,
    )


def raw_record(
    *,
    raw_file_id: str = "00000000-0000-4000-8000-000000000010",
    tenant_id: str = TENANT_ID,
    state: RawFileState = RawFileState.QUARANTINED,
    storage_key: str | None = None,
    diagnostics: tuple[str, ...] = ("SCHEMA_UNKNOWN",),
    structural_fingerprint=None,
    semantic_fingerprint=None,
    schema_id=None,
):
    if state is RawFileState.VALID:
        schema_id = schema_id or "wb-synthetic-v1"
        structural_fingerprint = structural_fingerprint or {"columns": ["a"]}
        semantic_fingerprint = semantic_fingerprint or {"semantic": "a"}
        diagnostics = ()
    elif state is RawFileState.QUARANTINED:
        structural_fingerprint = structural_fingerprint or {"columns": ["unknown"]}
        semantic_fingerprint = None
        schema_id = None
    elif state is RawFileState.REJECTED:
        structural_fingerprint = None
        semantic_fingerprint = None
        schema_id = None
    digest = "b" * 64
    return RawFileRecord(
        raw_file_id=raw_file_id,
        tenant_id=tenant_id,
        sha256=digest,
        size_bytes=64,
        sanitized_filename="adversarial.csv",
        storage_key=storage_key or f"tenants/{tenant_id}/raw/{digest}",
        state=state,
        schema_id=schema_id,
        structural_fingerprint=structural_fingerprint,
        semantic_fingerprint=semantic_fingerprint,
        diagnostics=diagnostics,
    )


class P15UXAdversarialTests(unittest.TestCase):
    def test_tampered_actor_is_rejected_before_value_application(self) -> None:
        form = valid_form()
        form["actor"] = ""
        with self.assertRaisesRegex(UXError, "UX_ACTOR_INVALID"):
            apply_configuration_values(form, {"cost": "400"})

    def test_tampered_currency_is_rejected_before_value_application(self) -> None:
        form = valid_form()
        form["currency"] = "rub"
        with self.assertRaisesRegex(UXError, "UX_CURRENCY_INVALID"):
            apply_configuration_values(form, {"cost": "400"})

    def test_tampered_created_at_is_rejected(self) -> None:
        form = valid_form()
        form["created_at"] = "2026-06-30"
        with self.assertRaisesRegex(UXError, "UX_CREATED_AT_INVALID"):
            apply_configuration_values(form, {})

    def test_tampered_problem_shape_is_rejected(self) -> None:
        form = valid_form()
        form["problems"] = [{"code": "X", "field_id": "cost", "message": "x", "secret": 1}]
        with self.assertRaisesRegex(UXError, "UX_FORM_PROBLEMS_INVALID"):
            apply_configuration_values(form, {})

    def test_noncanonical_storage_key_is_rejected(self) -> None:
        forged = raw_record(storage_key="other/tenant/raw/value")
        with self.assertRaisesRegex(UXError, "UX_IMPORT_RECORD_INVALID"):
            render_import_status(forged)

    def test_valid_state_without_semantic_fingerprint_is_rejected(self) -> None:
        forged = RawFileRecord(
            raw_file_id="00000000-0000-4000-8000-000000000011",
            tenant_id=TENANT_ID,
            sha256="c" * 64,
            size_bytes=64,
            sanitized_filename="forged.csv",
            storage_key=f"tenants/{TENANT_ID}/raw/{'c' * 64}",
            state=RawFileState.VALID,
            schema_id="wb-synthetic-v1",
            structural_fingerprint={"columns": ["a"]},
            semantic_fingerprint=None,
            diagnostics=(),
        )
        with self.assertRaisesRegex(UXError, "UX_IMPORT_STATE_PAYLOAD_INVALID"):
            render_import_status(forged)

    def test_received_state_with_diagnostics_is_rejected(self) -> None:
        forged = RawFileRecord(
            raw_file_id="00000000-0000-4000-8000-000000000012",
            tenant_id=TENANT_ID,
            sha256="d" * 64,
            size_bytes=64,
            sanitized_filename="received.csv",
            storage_key=f"tenants/{TENANT_ID}/raw/{'d' * 64}",
            state=RawFileState.RECEIVED,
            diagnostics=("UNEXPECTED",),
        )
        with self.assertRaisesRegex(UXError, "UX_IMPORT_STATE_PAYLOAD_INVALID"):
            render_import_status(forged)

    def test_duplicate_import_diagnostics_are_rejected(self) -> None:
        forged = raw_record(diagnostics=("SCHEMA_UNKNOWN", "SCHEMA_UNKNOWN"))
        with self.assertRaisesRegex(UXError, "UX_IMPORT_RECORD_INVALID"):
            render_import_status(forged)

    def test_duplicate_import_records_are_rejected(self) -> None:
        record = raw_record()
        with self.assertRaisesRegex(UXError, "UX_INBOX_IMPORT_DUPLICATE"):
            build_exception_inbox(
                [],
                import_records=[record, record],
                tenant_id=TENANT_ID,
                generated_at=NOW,
            )

    def test_actual_and_scenario_reports_cannot_share_inbox(self) -> None:
        actual = report_record(record_id="actual")
        scenario = report_record(
            record_id="scenario",
            mode="SCENARIO",
            scenario_id="scenario-1",
        )
        with self.assertRaisesRegex(UXError, "UX_INBOX_MODE_MIXED"):
            build_exception_inbox([actual, scenario], generated_at=NOW)

    def test_empty_inbox_context_is_rejected(self) -> None:
        with self.assertRaisesRegex(UXError, "UX_INBOX_CONTEXT_EMPTY"):
            build_exception_inbox([], generated_at=NOW)

    def test_valid_import_only_inbox_has_explicit_tenant_and_no_exception(self) -> None:
        record = raw_record(state=RawFileState.VALID)
        inbox = build_exception_inbox(
            [],
            import_records=[record],
            tenant_id=TENANT_ID,
            generated_at=NOW,
        )
        self.assertEqual(inbox["tenant_id"], TENANT_ID)
        self.assertEqual(inbox["exception_count"], 0)
        self.assertEqual(inbox["exceptions"], [])

    def test_exception_order_and_hash_are_deterministic(self) -> None:
        first = raw_record(
            raw_file_id="00000000-0000-4000-8000-000000000021",
            diagnostics=("SCHEMA_B",),
        )
        second = raw_record(
            raw_file_id="00000000-0000-4000-8000-000000000022",
            diagnostics=("SCHEMA_A",),
        )
        forward = build_exception_inbox(
            [],
            import_records=[first, second],
            tenant_id=TENANT_ID,
            generated_at=NOW,
        )
        reverse = build_exception_inbox(
            [],
            import_records=[second, first],
            tenant_id=TENANT_ID,
            generated_at=NOW,
        )
        self.assertEqual(forward, reverse)

    def test_tampered_report_is_rejected_by_rendering(self) -> None:
        record = report_record(record_id="tampered")
        record["state"] = "BLOCKED"
        with self.assertRaisesRegex(UXError, "UX_REPORT_INVALID"):
            render_report_record(record)

    def test_tampered_report_is_rejected_by_drilldown(self) -> None:
        record = report_record(record_id="drilldown")
        record["metric_content_hash"] = "0" * 64
        with self.assertRaisesRegex(UXError, "UX_REPORT_INVALID"):
            build_report_drilldown(record)

    def test_b4_builder_still_rejects_invalid_scenario_shape(self) -> None:
        snapshot = valid_snapshot()
        snapshot["mode"] = "SCENARIO"
        snapshot["scenario_id"] = None
        snapshot["content_hash"] = canonical_snapshot_hash(snapshot)
        with self.assertRaises(ReportingError):
            build_report_record(
                snapshot,
                report_record_id="invalid-scenario",
                generated_at=NOW,
            )

    def test_configuration_input_does_not_mutate_source_form(self) -> None:
        form = valid_form()
        original = copy.deepcopy(form)
        apply_configuration_values(form, {"cost": "400"})
        self.assertEqual(form, original)


if __name__ == "__main__":
    unittest.main()
