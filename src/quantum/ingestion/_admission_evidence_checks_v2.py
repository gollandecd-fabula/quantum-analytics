from __future__ import annotations

from datetime import datetime

from ._admission_contracts_v2 import (
    AdmissionError,
    DatasetAdmissionRecord,
    DatasetControlEvidence,
    StorageControlEvidence,
    _aware_utc,
    _uuid,
)


def require_evidence_binding(
    record: DatasetAdmissionRecord,
    dataset_evidence: DatasetControlEvidence,
    storage_evidence: StorageControlEvidence,
) -> None:
    declaration = record.declaration
    inspection = record.inspection
    if dataset_evidence.verifier_account_id == declaration.uploader_account_id:
        raise AdmissionError("DATASET_EVIDENCE_NOT_INDEPENDENT")
    if storage_evidence.verifier_account_id == declaration.uploader_account_id:
        raise AdmissionError("STORAGE_EVIDENCE_NOT_INDEPENDENT")
    if inspection is None or not inspection.matched:
        raise AdmissionError("DATASET_VALIDATION_EVIDENCE_MISSING")
    if (
        _uuid(dataset_evidence.dataset_id, "DATASET_EVIDENCE_DATASET_INVALID")
        != declaration.dataset_id
    ):
        raise AdmissionError("DATASET_EVIDENCE_DATASET_MISMATCH")
    if dataset_evidence.original_file_sha256 != declaration.original_file_sha256:
        raise AdmissionError("DATASET_EVIDENCE_FILE_MISMATCH")
    if dataset_evidence.owner_authority_reference != declaration.owner_authority_reference:
        raise AdmissionError("DATASET_EVIDENCE_AUTHORITY_MISMATCH")
    if (
        dataset_evidence.reporting_period_start != declaration.reporting_period_start
        or dataset_evidence.reporting_period_end != declaration.reporting_period_end
        or dataset_evidence.timezone != declaration.timezone
    ):
        raise AdmissionError("DATASET_EVIDENCE_PERIOD_MISMATCH")
    if dataset_evidence.control_totals_sha256 != declaration.control_totals_sha256:
        raise AdmissionError("DATASET_EVIDENCE_CONTROL_TOTALS_MISMATCH")
    if dataset_evidence.policy_content_hash != record.policy_content_hash:
        raise AdmissionError("DATASET_EVIDENCE_POLICY_MISMATCH")
    if dataset_evidence.workbook_sha256 != inspection.workbook_sha256:
        raise AdmissionError("DATASET_EVIDENCE_WORKBOOK_MISMATCH")
    if (
        dataset_evidence.structural_fingerprint_sha256
        != inspection.structural_fingerprint_sha256
    ):
        raise AdmissionError("DATASET_EVIDENCE_FINGERPRINT_MISMATCH")
    if (
        dataset_evidence.matched_schema_id != inspection.matched_schema_id
        or dataset_evidence.matched_schema_version != inspection.matched_schema_version
        or dataset_evidence.matched_schema_authority_reference
        != inspection.matched_schema_authority_reference
    ):
        raise AdmissionError("DATASET_EVIDENCE_SCHEMA_MISMATCH")
    if (
        _uuid(storage_evidence.dataset_id, "STORAGE_EVIDENCE_DATASET_INVALID")
        != declaration.dataset_id
    ):
        raise AdmissionError("STORAGE_EVIDENCE_DATASET_MISMATCH")
    if storage_evidence.original_file_sha256 != declaration.original_file_sha256:
        raise AdmissionError("STORAGE_EVIDENCE_FILE_MISMATCH")


def require_evidence_times(
    record: DatasetAdmissionRecord,
    dataset_evidence: DatasetControlEvidence,
    storage_evidence: StorageControlEvidence,
    admitted_at: datetime,
) -> None:
    validation_time = record.latest_decision.decided_at
    dataset_verified = _aware_utc(
        dataset_evidence.verified_at,
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
    if dataset_verified > admitted_at:
        raise AdmissionError("DATASET_EVIDENCE_FROM_FUTURE")
    if storage_verified > admitted_at:
        raise AdmissionError("STORAGE_EVIDENCE_FROM_FUTURE")
