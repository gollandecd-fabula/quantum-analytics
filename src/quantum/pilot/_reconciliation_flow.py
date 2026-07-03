from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from quantum.ingestion.admission_v2 import DatasetAdmissionRecord
from quantum.reconciliation import reconcile_source_totals

from ._bindings import validate_source_identity
from ._scope import LocalPilotExecutionError, LocalPilotScope


def reconcile_pilot_results(
    *,
    scope: LocalPilotScope,
    admitted: DatasetAdmissionRecord,
    source_snapshot: Mapping[str, Any],
    calculated_snapshot: Mapping[str, Any],
    policy: Mapping[str, Any],
    reconciled_at: datetime,
) -> Mapping[str, Any]:
    source = validate_source_identity(source_snapshot, admitted)
    reconciliation = reconcile_source_totals(
        admission_record=admitted,
        tenant_id=scope.tenant_id,
        account_id=scope.account_id,
        source_snapshot=source,
        calculated_snapshot=calculated_snapshot,
        policy=policy,
        reconciled_at=reconciled_at,
    )
    if reconciliation.get("state") != "RECONCILED":
        raise LocalPilotExecutionError("PILOT_RECONCILIATION_CONFLICT")
    return reconciliation


__all__ = ["reconcile_pilot_results"]
