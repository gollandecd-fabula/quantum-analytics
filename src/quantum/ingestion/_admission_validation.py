from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from hashlib import sha256

from quantum.access import TenantContext

from ._admission_contracts import (
    AdmissionError,
    DatasetAdmissionRecord,
    DatasetAdmissionState,
    _aware_utc,
)
from ._xlsx_contracts import XlsxInspectionError, XlsxInspectionPolicy


class _AdmissionValidationMixin:
    def inspect_and_validate(
        self,
        *,
        tenant: TenantContext,
        dataset_id: str,
        payload: bytes,
        policy: XlsxInspectionPolicy,
        observed_at: datetime,
    ) -> DatasetAdmissionRecord:
        tenant = self._require_tenant(tenant)
        observed = _aware_utc(observed_at, "DATASET_INSPECTION_TIMEZONE_REQUIRED")
        if not isinstance(policy, XlsxInspectionPolicy):
            raise AdmissionError("XLSX_POLICY_REQUIRED")
        with self._lock:
            record = self.get(tenant=tenant, dataset_id=dataset_id)
            self._require_monotonic_time(record, observed)
            policy_changes = {
                "policy_id": policy.policy_id,
                "policy_version": policy.version,
                "policy_content_hash": policy.content_hash,
            }
            if record.state is DatasetAdmissionState.DECLARED:
                record = self._transition(
                    record,
                    DatasetAdmissionState.QUARANTINED,
                    actor=tenant.account_id,
                    at=observed,
                    reason="DATASET_QUARANTINED_FOR_VALIDATION",
                    **policy_changes,
                )
                self._records[(tenant.tenant_id, record.declaration.dataset_id)] = record
            elif record.state is DatasetAdmissionState.QUARANTINED:
                record = replace(record, **policy_changes)
            else:
                raise AdmissionError("DATASET_STATE_TRANSITION_INVALID")

            if not isinstance(payload, bytes) or not payload:
                return self._reject_locked(
                    tenant=tenant,
                    record=record,
                    code="DATASET_BYTES_REQUIRED",
                    at=observed,
                )
            declaration = record.declaration
            actual_digest = sha256(payload).hexdigest()
            if (
                actual_digest != declaration.original_file_sha256
                or len(payload) != declaration.original_size_bytes
            ):
                return self._reject_locked(
                    tenant=tenant,
                    record=record,
                    code="DATASET_ORIGINAL_FILE_MISMATCH",
                    at=observed,
                )
            try:
                inspection = self._inspector.inspect(payload=payload, policy=policy)
            except XlsxInspectionError as exc:
                return self._reject_locked(
                    tenant=tenant,
                    record=record,
                    code=exc.code,
                    at=observed,
                )

            diagnostics = list(inspection.diagnostics)
            if (
                declaration.expected_row_count is not None
                and declaration.expected_row_count != inspection.data_row_count
            ):
                diagnostics.append("DATASET_CONTROL_ROW_COUNT_MISMATCH")
            diagnostics_tuple = tuple(sorted(set(diagnostics)))
            if diagnostics_tuple:
                updated = self._record_same_state_decision(
                    record,
                    actor=tenant.account_id,
                    at=observed,
                    reason="DATASET_VALIDATION_BLOCKED",
                    diagnostics=diagnostics_tuple,
                    inspection=inspection,
                )
                self._records[(tenant.tenant_id, declaration.dataset_id)] = updated
                return updated

            updated = self._transition(
                record,
                DatasetAdmissionState.VALIDATED,
                actor=tenant.account_id,
                at=observed,
                reason="DATASET_VALIDATED",
                inspection=inspection,
            )
            self._records[(tenant.tenant_id, declaration.dataset_id)] = updated
            return updated
    def _reject_locked(
        self,
        *,
        tenant: TenantContext,
        record: DatasetAdmissionRecord,
        code: str,
        at: datetime,
    ) -> DatasetAdmissionRecord:
        diagnostics = (code,)
        updated = self._transition(
            record,
            DatasetAdmissionState.REJECTED,
            actor=tenant.account_id,
            at=at,
            reason=code,
            diagnostics=diagnostics,
        )
        self._records[(tenant.tenant_id, record.declaration.dataset_id)] = updated
        return updated
