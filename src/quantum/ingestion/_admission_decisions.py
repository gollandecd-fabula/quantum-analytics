from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

from quantum.access import TenantContext

from ._admission_contracts import (
    AdmissionError,
    DatasetAdmissionRecord,
    DatasetAdmissionState,
    DatasetControlEvidence,
    StorageControlEvidence,
    _aware_utc,
    _safe_identifier,
)


class _AdmissionDecisionMixin:
    def admit(
        self,
        *,
        tenant: TenantContext,
        dataset_id: str,
        dataset_control_evidence: DatasetControlEvidence,
        storage_evidence: StorageControlEvidence,
        admitted_at: datetime,
    ) -> DatasetAdmissionRecord:
        tenant = self._require_tenant(tenant)
        current = _aware_utc(admitted_at, "DATASET_ADMISSION_TIMEZONE_REQUIRED")
        if not isinstance(dataset_control_evidence, DatasetControlEvidence):
            raise AdmissionError("DATASET_CONTROL_EVIDENCE_REQUIRED")
        if not isinstance(storage_evidence, StorageControlEvidence):
            raise AdmissionError("STORAGE_EVIDENCE_REQUIRED")
        try:
            tenant.require_tenant(dataset_control_evidence.tenant_id)
            tenant.require_tenant(storage_evidence.tenant_id)
        except ValueError as exc:
            raise AdmissionError("DATASET_NOT_FOUND") from exc
        if not dataset_control_evidence.complete:
            raise AdmissionError("DATASET_CONTROLS_INCOMPLETE")
        if not storage_evidence.complete:
            raise AdmissionError("STORAGE_CONTROLS_INCOMPLETE")
        with self._lock:
            record = self.get(tenant=tenant, dataset_id=dataset_id)
            self._require_monotonic_time(record, current)
            if record.state is not DatasetAdmissionState.VALIDATED:
                raise AdmissionError("DATASET_NOT_VALIDATED")
            if dataset_control_evidence.dataset_id != record.declaration.dataset_id:
                raise AdmissionError("DATASET_EVIDENCE_DATASET_MISMATCH")
            if (
                dataset_control_evidence.original_file_sha256
                != record.declaration.original_file_sha256
            ):
                raise AdmissionError("DATASET_EVIDENCE_FILE_MISMATCH")
            if storage_evidence.dataset_id != record.declaration.dataset_id:
                raise AdmissionError("STORAGE_EVIDENCE_DATASET_MISMATCH")
            if storage_evidence.original_file_sha256 != record.declaration.original_file_sha256:
                raise AdmissionError("STORAGE_EVIDENCE_FILE_MISMATCH")
            if current >= _aware_utc(
                record.declaration.retention_deadline,
                "DATASET_RETENTION_TIMEZONE_REQUIRED",
            ):
                raise AdmissionError("DATASET_RETENTION_EXPIRED")
            validation_time = record.latest_decision.decided_at
            dataset_verified = _aware_utc(
                dataset_control_evidence.verified_at,
                "DATASET_EVIDENCE_TIMEZONE_REQUIRED",
            )
            storage_verified = _aware_utc(
                storage_evidence.verified_at,
                "STORAGE_EVIDENCE_TIMEZONE_REQUIRED",
            )
            if dataset_verified < validation_time:
                raise AdmissionError("DATASET_EVIDENCE_STALE")
            if storage_verified < validation_time:
                raise AdmissionError("STORAGE_EVIDENCE_STALE")
            if dataset_verified > current:
                raise AdmissionError("DATASET_EVIDENCE_FROM_FUTURE")
            if storage_verified > current:
                raise AdmissionError("STORAGE_EVIDENCE_FROM_FUTURE")
            updated = self._transition(
                record,
                DatasetAdmissionState.ADMITTED,
                actor=tenant.account_id,
                at=current,
                reason="DATASET_ADMITTED",
                dataset_control_evidence_id=dataset_control_evidence.evidence_id,
                storage_evidence_id=storage_evidence.evidence_id,
                storage_key_sha256=storage_evidence.storage_key_sha256,
            )
            self._records[(tenant.tenant_id, record.declaration.dataset_id)] = updated
            return updated
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
    ) -> DatasetAdmissionRecord:
        record = self.get(tenant=tenant, dataset_id=dataset_id)
        if record.state is not DatasetAdmissionState.ADMITTED:
            raise AdmissionError("DATASET_NOT_ADMITTED")
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
            "tenant_id_sha256": sha256(record.declaration.tenant_id.encode("utf-8")).hexdigest(),
            "source_internal_id_sha256": sha256(
                record.declaration.source_internal_id.encode("utf-8")
            ).hexdigest(),
            "state": record.state.value,
            "original_file_sha256": record.declaration.original_file_sha256,
            "original_size_bytes": record.declaration.original_size_bytes,
            "expected_row_count": record.declaration.expected_row_count,
            "policy_id": record.policy_id,
            "policy_version": record.policy_version,
            "policy_content_hash": record.policy_content_hash,
            "matched_schema_id": inspection.matched_schema_id if inspection else None,
            "matched_schema_version": inspection.matched_schema_version if inspection else None,
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
