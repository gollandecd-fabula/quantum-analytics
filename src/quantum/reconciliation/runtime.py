from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from quantum.ingestion._admission_contracts_v2 import DatasetAdmissionRecord

from ._runtime_core import ReconciliationError
from ._runtime_core import reconcile_source_totals as _core_reconcile_source_totals


def reconcile_source_totals(
    *,
    admission_record: DatasetAdmissionRecord,
    tenant_id: str,
    account_id: str,
    source_snapshot: Mapping[str, Any],
    calculated_snapshot: Mapping[str, Any],
    policy: Mapping[str, Any],
    reconciled_at: datetime,
) -> dict[str, Any]:
    """Enforce retention validity before producing reconciliation evidence."""
    if (
        not isinstance(reconciled_at, datetime)
        or reconciled_at.tzinfo is None
        or reconciled_at.utcoffset() is None
    ):
        raise ReconciliationError("RECONCILIATION_TIMESTAMP_INVALID")
    if isinstance(admission_record, DatasetAdmissionRecord):
        deadline = admission_record.declaration.retention_deadline
        if reconciled_at.astimezone(UTC) > deadline.astimezone(UTC):
            raise ReconciliationError("RECONCILIATION_RETENTION_EXPIRED")
    return _core_reconcile_source_totals(
        admission_record=admission_record,
        tenant_id=tenant_id,
        account_id=account_id,
        source_snapshot=source_snapshot,
        calculated_snapshot=calculated_snapshot,
        policy=policy,
        reconciled_at=reconciled_at,
    )


__all__ = ["ReconciliationError", "reconcile_source_totals"]
