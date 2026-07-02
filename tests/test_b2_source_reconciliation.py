from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from copy import deepcopy
import unittest

from quantum.finance._common import canonical_hash
from quantum.ingestion._admission_contracts_v2 import (
    DatasetAdmissionRecord,
    DatasetAdmissionState,
    DatasetDeclaration,
    DatasetSensitivity,
)
from quantum.reconciliation import ReconciliationError, reconcile_source_totals

DATASET_ID = "11111111-1111-4111-8111-111111111111"
FILE_HASH = "a" * 64


def declaration(
    *,
    expected_rows: int | None = 10,
    retention_deadline: datetime | None = None,
) -> DatasetDeclaration:
    now = datetime(2026, 7, 2, tzinfo=UTC)
    return DatasetDeclaration(
        dataset_id=DATASET_ID,
        tenant_id="tenant-1",
        uploader_account_id="account-1",
        source_internal_id="source-1",
        marketplace="WB",
        report_type="FINANCIAL_REPORT",
        reporting_period_start=date(2026, 6, 1),
        reporting_period_end=date(2026, 6, 30),
        timezone="Europe/Moscow",
        original_file_sha256=FILE_HASH,
        original_size_bytes=1024,
        expected_row_count=expected_rows,
        control_totals_sha256=None,
        data_categories=("FINANCIAL",),
        sensitivity=DatasetSensitivity.COMMERCIAL_CONFIDENTIAL,
        owner_authority_reference="owner-approval-1",
        lawful_authority_attested=True,
        retention_deadline=retention_deadline or now + timedelta(days=30),
        declared_at=now,
    )


def admitted_record(
    *,
    state: DatasetAdmissionState = DatasetAdmissionState.ADMITTED,
    retention_deadline: datetime | None = None,
) -> DatasetAdmissionRecord:
    return DatasetAdmissionRecord(
        declaration=declaration(retention_deadline=retention_deadline),
        state=state,
    )


def policy() -> dict:
    value = {
        "policy_id": "b2-pilot-v1",
        "version": 1,
        "content_hash": "",
        "row_count_tolerance": 0,
        "metric_tolerances": {
            "gross_sales_amount": {
                "absolute": "0.01",
                "value_type": "MONEY",
                "unit": "MONEY",
                "currency": "RUB",
            },
            "marketplace_commission_amount": {
                "absolute": "0.01",
                "value_type": "MONEY",
                "unit": "MONEY",
                "currency": "RUB",
            },
        },
    }
    value["content_hash"] = canonical_hash(value, exclude=frozenset({"content_hash"}))
    return value


def total(value: str) -> dict:
    return {
        "state": "VALID",
        "value": value,
        "value_type": "MONEY",
        "unit": "MONEY",
        "currency": "RUB",
    }


def snapshot(*, sales: str = "10000.00", commission: str = "1000.00", rows: int = 10) -> dict:
    return {
        "dataset_id": DATASET_ID,
        "original_file_sha256": FILE_HASH,
        "row_count": rows,
        "totals": {
            "gross_sales_amount": total(sales),
            "marketplace_commission_amount": total(commission),
        },
    }


class B2SourceReconciliationTests(unittest.TestCase):
    def reconcile(
        self,
        source: dict,
        calculated: dict,
        *,
        record: DatasetAdmissionRecord | None = None,
        account_id: str = "account-1",
        reconciled_at: datetime = datetime(2026, 7, 2, 12, tzinfo=UTC),
    ) -> dict:
        return reconcile_source_totals(
            admission_record=record or admitted_record(),
            tenant_id="tenant-1",
            account_id=account_id,
            source_snapshot=source,
            calculated_snapshot=calculated,
            policy=policy(),
            reconciled_at=reconciled_at,
        )

    def test_exact_match_is_reconciled_and_hashed(self) -> None:
        result = self.reconcile(snapshot(), snapshot())
        self.assertEqual(result["state"], "RECONCILED")
        self.assertEqual(result["row_count"]["state"], "MATCH")
        self.assertEqual(len(result["evidence_hash"]), 64)

    def test_difference_within_versioned_tolerance_matches(self) -> None:
        result = self.reconcile(snapshot(), snapshot(sales="10000.01"))
        self.assertEqual(result["state"], "RECONCILED")
        self.assertEqual(result["metrics"]["gross_sales_amount"]["state"], "MATCH")

    def test_material_difference_is_conflict_not_silent_acceptance(self) -> None:
        result = self.reconcile(snapshot(), snapshot(commission="999.98"))
        self.assertEqual(result["state"], "CONFLICT")
        self.assertEqual(result["metrics"]["marketplace_commission_amount"]["state"], "CONFLICT")

    def test_row_count_conflict_blocks_reconciliation(self) -> None:
        result = self.reconcile(snapshot(), snapshot(rows=9))
        self.assertEqual(result["state"], "CONFLICT")
        self.assertEqual(result["row_count"]["state"], "CONFLICT")

    def test_non_admitted_dataset_fails_closed(self) -> None:
        with self.assertRaisesRegex(ReconciliationError, "RECONCILIATION_DATASET_NOT_ADMITTED"):
            self.reconcile(
                snapshot(),
                snapshot(),
                record=admitted_record(state=DatasetAdmissionState.VALIDATED),
            )

    def test_same_tenant_non_owner_account_fails_closed(self) -> None:
        with self.assertRaisesRegex(ReconciliationError, "RECONCILIATION_DATASET_NOT_FOUND"):
            self.reconcile(snapshot(), snapshot(), account_id="account-2")

    def test_reconciliation_after_retention_deadline_fails_closed(self) -> None:
        deadline = datetime(2026, 7, 3, tzinfo=UTC)
        with self.assertRaisesRegex(ReconciliationError, "RECONCILIATION_RETENTION_EXPIRED"):
            self.reconcile(
                snapshot(),
                snapshot(),
                record=admitted_record(retention_deadline=deadline),
                reconciled_at=deadline + timedelta(microseconds=1),
            )

    def test_reconciliation_at_retention_deadline_is_allowed(self) -> None:
        deadline = datetime(2026, 7, 3, tzinfo=UTC)
        result = self.reconcile(
            snapshot(),
            snapshot(),
            record=admitted_record(retention_deadline=deadline),
            reconciled_at=deadline,
        )
        self.assertEqual(result["state"], "RECONCILED")

    def test_dataset_and_source_hash_are_bound(self) -> None:
        changed = deepcopy(snapshot())
        changed["original_file_sha256"] = "b" * 64
        with self.assertRaisesRegex(ReconciliationError, "RECONCILIATION_SOURCE_HASH_MISMATCH"):
            self.reconcile(snapshot(), changed)

    def test_missing_metric_fails_closed(self) -> None:
        changed = deepcopy(snapshot())
        changed["totals"].pop("marketplace_commission_amount")
        with self.assertRaisesRegex(ReconciliationError, "RECONCILIATION_METRIC_SET_MISMATCH"):
            self.reconcile(snapshot(), changed)


if __name__ == "__main__":
    unittest.main()
