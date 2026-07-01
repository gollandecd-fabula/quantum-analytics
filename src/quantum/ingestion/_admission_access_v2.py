from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

from quantum.access import TenantContext

from ._admission_contracts_v2 import (
    AdmissionError,
    DatasetAdmissionRecord,
    DatasetAdmissionState,
    _aware_utc,
    _safe_identifier,
)


class _AdmissionAccessMixinV2:
    def revoke(
        self,
        *,
        tenant: TenantContext,
        dataset_id: str,
        reason_code: str,
        revoked_at: datetime,
    ) -> DatasetAdmissionRecord:
        tenant = self._require_tenant(tenant)
        current = _aware_utc(revoked_at, "DATASET_REVOCATION_TIMEZONE_REQUIRED")
        reason = _safe_identifier(reason_code, "DATASET_REVOCATION_REASON_INVALID")
        with self._lock:
            record = self.get(tenant=tenant, dataset_id=dataset_id)
            self._require_monotonic_time(record, current)
            if record.state is not DatasetAdmissionState.ADMITTED:
                raise AdmissionError("DATASET_NOT_ADMITTED")
            updated = self._transition(
                record,
                DatasetAdmissionState.REVOKED,
                actor=tenant.account_id,
                at=current,
                reason=reason,
            )
            self._records[(tenant.tenant_id, record.declaration.dataset_id)] = updated
            return updated

    def require_admitted(
        self,
        *,
        tenant: TenantContext,
        dataset_id: str,
        as_of: datetime | None = None,
    ) -> DatasetAdmissionRecord:
        current = _aware_utc(
            as_of or datetime.now(UTC),
            "DATASET_ACCESS_TIMEZONE_REQUIRED",
        )
        record = self.get(tenant=tenant, dataset_id=dataset_id)
        if record.state is not DatasetAdmissionState.ADMITTED:
            raise AdmissionError("DATASET_NOT_ADMITTED")
        if current < record.latest_decision.decided_at:
            raise AdmissionError("DATASET_NOT_ADMITTED_AT_TIME")
        if current >= _aware_utc(
            record.declaration.retention_deadline,
            "DATASET_RETENTION_TIMEZONE_REQUIRED",
        ):
            raise AdmissionError("DATASET_RETENTION_EXPIRED")
        return record

    def evidence_summary(
        self,
        *,
        tenant: TenantContext,
        dataset_id: str,
    ) -> dict[str, object]:
        record = self.get(tenant=tenant, dataset_id=dataset_id)
        inspection = record.inspection
        decisions = [
            {
                "state": item.state.value,
                "actor_account_id_sha256": sha256(
                    item.actor_account_id.encode("utf-8")
                ).hexdigest(),
                "decided_at": item.decided_at.astimezone(UTC).isoformat(),
                "reason_code": item.reason_code,
                "diagnostics": list(item.diagnostics),
            }
            for item in record.decisions
        ]
        return {
            "dataset_id": record.declaration.dataset_id,
            "tenant_id_sha256": sha256(
                record.declaration.tenant_id.encode("utf-8")
            ).hexdigest(),
            "source_internal_id": record.declaration.source_internal_id,
            "state": record.state.value,
            "original_file_sha256": record.declaration.original_file_sha256,
            "original_size_bytes": record.declaration.original_size_bytes,
            "expected_row_count": record.declaration.expected_row_count,
            "policy_id": record.policy_id,
            "policy_version": record.policy_version,
            "policy_content_hash": record.policy_content_hash,
            "workbook_sha256": inspection.workbook_sha256 if inspection else None,
            "matched_schema_id": inspection.matched_schema_id if inspection else None,
            "matched_schema_version": (
                inspection.matched_schema_version if inspection else None
            ),
            "matched_schema_authority_reference": (
                inspection.matched_schema_authority_reference if inspection else None
            ),
            "structural_fingerprint_sha256": (
                inspection.structural_fingerprint_sha256 if inspection else None
            ),
            "data_row_count": inspection.data_row_count if inspection else None,
            "formula_count": inspection.formula_count if inspection else None,
            "prohibited_header_count": (
                inspection.prohibited_header_count if inspection else None
            ),
            "diagnostics": list(record.diagnostics),
            "dataset_control_evidence_id": record.dataset_control_evidence_id,
            "storage_evidence_id": record.storage_evidence_id,
            "storage_key_sha256": record.storage_key_sha256,
            "decision_count": len(decisions),
            "decisions": decisions,
        }
