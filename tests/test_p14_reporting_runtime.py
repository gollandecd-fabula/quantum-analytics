from __future__ import annotations

import copy
import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from quantum.evidence import canonical_snapshot_hash
from quantum.reporting import (
    ReportingError,
    build_export_bundle,
    build_report_record,
    export_bundle_json,
    export_records_csv,
    export_records_jsonl,
    import_bundle_json,
    import_records_csv,
    import_records_jsonl,
    page_records,
    validate_export_bundle,
    validate_report_record,
)
from quantum.reporting import runtime
from tests.b3_helpers import valid_snapshot


GENERATED_AT = datetime(2026, 6, 30, 15, 0, tzinfo=UTC)


class P14ReportingRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = valid_snapshot()
        self.record = build_report_record(
            self.snapshot,
            report_record_id="report-1",
            generated_at=GENERATED_AT,
        )

    @staticmethod
    def blocked_snapshot():
        snapshot = valid_snapshot()
        snapshot.update({
            "state": "BLOCKED",
            "value": None,
            "value_type": None,
            "unit": None,
            "currency": None,
            "reason_code": "CONFIGURATION_REQUIRED",
        })
        snapshot["content_hash"] = canonical_snapshot_hash(snapshot)
        return snapshot

    @staticmethod
    def scenario_snapshot():
        snapshot = valid_snapshot()
        snapshot["mode"] = "SCENARIO"
        snapshot["scenario_id"] = "scenario-1"
        snapshot["metric_snapshot_id"] = "metric-result-scenario"
        snapshot["content_hash"] = canonical_snapshot_hash(snapshot)
        return snapshot

    @staticmethod
    def other_tenant_snapshot():
        snapshot = valid_snapshot()
        snapshot["organization_id"] = "other-org"
        snapshot["metric_snapshot_id"] = "metric-result-other-org"
        snapshot["content_hash"] = canonical_snapshot_hash(snapshot)
        return snapshot

    def record_with_id(
        self,
        record_id: str,
        *,
        generated_at: datetime = GENERATED_AT,
    ):
        return build_report_record(
            self.snapshot,
            report_record_id=record_id,
            generated_at=generated_at,
        )

    def test_valid_numeric_zero_is_preserved(self) -> None:
        self.assertEqual(self.record["state"], "VALID")
        self.assertEqual(self.record["value"], "0")
        self.assertEqual(self.record["currency"], "RUB")
        self.assertEqual(self.record["unit"], "MONEY_PER_ITEM")

    def test_blocked_state_never_becomes_zero(self) -> None:
        record = build_report_record(
            self.blocked_snapshot(),
            report_record_id="report-blocked",
            generated_at=GENERATED_AT,
        )
        self.assertEqual(record["state"], "BLOCKED")
        self.assertIsNone(record["value"])
        self.assertEqual(record["reason_code"], "CONFIGURATION_REQUIRED")

    def test_preview_record_has_explicit_publication_limitation(self) -> None:
        self.assertEqual(self.record["publication_state"], "PREVIEW_ONLY")
        self.assertIsNone(self.record["evidence_chain_content_hash"])
        self.assertIn(
            "EVIDENCE_NOT_VERIFIED_FOR_PUBLICATION",
            self.record["limitations"],
        )

    def test_snapshot_validation_is_fail_closed(self) -> None:
        snapshot = valid_snapshot()
        snapshot["content_hash"] = "0" * 64
        with self.assertRaisesRegex(ReportingError, "REPORT_SNAPSHOT_INVALID"):
            build_report_record(
                snapshot,
                report_record_id="report-invalid",
                generated_at=GENERATED_AT,
            )

    def test_report_record_rejects_extra_fields(self) -> None:
        record = copy.deepcopy(self.record)
        record["hidden_default"] = 40
        with self.assertRaisesRegex(ReportingError, "REPORT_RECORD_MALFORMED"):
            validate_report_record(record)

    def test_report_record_preserves_reporting_metadata(self) -> None:
        self.assertEqual(self.record["accounting_view"], "SETTLEMENT")
        self.assertEqual(
            self.record["expense_boundary"],
            ["MARKETPLACE_COMMISSION", "PRODUCT_COST", "TAX"],
        )
        self.assertEqual(self.record["freshness"]["state"], "CURRENT")
        self.assertEqual(self.record["confidence"]["state"], "HIGH")
        self.assertEqual(
            self.record["evidence_chain_ref"],
            {"id": "evidence-chain-synthetic-1", "version": 1},
        )
        self.assertEqual(len(self.record["record_hash"]), 64)

    def test_bundle_json_round_trip_is_exact(self) -> None:
        bundle = build_export_bundle(
            [self.record],
            bundle_id="bundle-1",
            generated_at=GENERATED_AT,
        )
        restored = import_bundle_json(export_bundle_json(bundle))
        self.assertEqual(restored, bundle)

    def test_bundle_hash_detects_tampering(self) -> None:
        bundle = build_export_bundle(
            [self.record],
            bundle_id="bundle-1",
            generated_at=GENERATED_AT,
        )
        bundle["records"][0]["limitations"].append("tampered")
        with self.assertRaisesRegex(ReportingError, "EXPORT_HASH_MISMATCH"):
            validate_export_bundle(bundle)

    def test_bundle_rejects_mixed_tenants(self) -> None:
        other = build_report_record(
            self.other_tenant_snapshot(),
            report_record_id="report-2",
            generated_at=GENERATED_AT,
        )
        with self.assertRaisesRegex(ReportingError, "EXPORT_TENANT_MIXED"):
            build_export_bundle(
                [self.record, other],
                bundle_id="bundle-mixed",
                generated_at=GENERATED_AT,
            )

    def test_bundle_rejects_actual_scenario_mix(self) -> None:
        scenario = build_report_record(
            self.scenario_snapshot(),
            report_record_id="report-scenario",
            generated_at=GENERATED_AT,
        )
        with self.assertRaisesRegex(ReportingError, "EXPORT_MODE_MIXED"):
            build_export_bundle(
                [self.record, scenario],
                bundle_id="bundle-mixed",
                generated_at=GENERATED_AT,
            )

    def test_jsonl_round_trip_preserves_typed_state(self) -> None:
        blocked = build_report_record(
            self.blocked_snapshot(),
            report_record_id="report-blocked",
            generated_at=GENERATED_AT,
        )
        restored = import_records_jsonl(
            export_records_jsonl([self.record, blocked])
        )
        self.assertEqual(restored, (self.record, blocked))

    def test_csv_round_trip_preserves_evidence_and_zero(self) -> None:
        restored = import_records_csv(export_records_csv([self.record]))
        self.assertEqual(restored, (self.record,))
        self.assertEqual(restored[0]["value"], "0")
        self.assertEqual(
            restored[0]["evidence_chain_ref"]["id"],
            "evidence-chain-synthetic-1",
        )

    def test_csv_projection_tampering_is_rejected(self) -> None:
        payload = export_records_csv([self.record])
        tampered = payload.replace(b"report-1", b"report-x", 1)
        with self.assertRaisesRegex(
            ReportingError,
            "EXPORT_CSV_PROJECTION_MISMATCH",
        ):
            import_records_csv(tampered)

    def test_pagination_is_stable(self) -> None:
        records = [self.record_with_id(f"report-{index}") for index in range(3)]
        first = page_records(records, limit=2)
        second = page_records(records, limit=2, cursor=first.next_cursor)
        self.assertEqual(len(first.records), 2)
        self.assertEqual(len(second.records), 1)
        self.assertIsNone(second.next_cursor)
        self.assertEqual(first.total_records, 3)

    def test_cursor_cannot_be_reused_for_changed_result_set(self) -> None:
        records = [self.record_with_id("report-1"), self.record_with_id("report-2")]
        first = page_records(records, limit=1)
        changed = [
            records[0],
            self.record_with_id(
                "report-2",
                generated_at=datetime(2026, 6, 30, 16, 0, tzinfo=UTC),
            ),
        ]
        with self.assertRaisesRegex(ReportingError, "REPORT_CURSOR_INVALID"):
            page_records(changed, limit=1, cursor=first.next_cursor)

    def test_page_limit_is_bounded(self) -> None:
        with self.assertRaisesRegex(ReportingError, "REPORT_PAGE_LIMIT_INVALID"):
            page_records([self.record], limit=101)

    def test_record_limit_is_bounded(self) -> None:
        other = self.record_with_id("report-2")
        with patch.object(runtime, "MAX_EXPORT_RECORDS", 1):
            with self.assertRaisesRegex(
                ReportingError,
                "EXPORT_RECORD_LIMIT_EXCEEDED",
            ):
                build_export_bundle(
                    [self.record, other],
                    bundle_id="bundle-large",
                    generated_at=GENERATED_AT,
                )

    def test_byte_limit_is_bounded(self) -> None:
        bundle = build_export_bundle(
            [self.record],
            bundle_id="bundle-1",
            generated_at=GENERATED_AT,
        )
        with patch.object(runtime, "MAX_EXPORT_BYTES", 10):
            with self.assertRaisesRegex(
                ReportingError,
                "EXPORT_BYTE_LIMIT_EXCEEDED",
            ):
                export_bundle_json(bundle)

    def test_generated_at_requires_timezone(self) -> None:
        with self.assertRaisesRegex(ReportingError, "REPORT_TIMESTAMP_INVALID"):
            build_report_record(
                self.snapshot,
                report_record_id="report-naive",
                generated_at=datetime(2026, 6, 30, 15, 0),
            )

    def test_scenario_record_retains_namespace(self) -> None:
        record = build_report_record(
            self.scenario_snapshot(),
            report_record_id="report-scenario",
            generated_at=GENERATED_AT,
        )
        self.assertEqual(record["mode"], "SCENARIO")
        self.assertEqual(record["scenario_id"], "scenario-1")


if __name__ == "__main__":
    unittest.main()
