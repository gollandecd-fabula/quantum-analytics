from __future__ import annotations

from collections.abc import Callable

from quantum.ingestion.admission import (
    DatasetAdmissionRecord,
    DatasetControlEvidence,
    StorageControlEvidence,
    StorageEnvironment,
)

from ._evidence_config import EvidenceConfig
from ._manifest_time import PilotTimes
from ._scope import LocalPilotExecutionError, LocalPilotScope, secure_equal


DatasetBuilder = Callable[[DatasetAdmissionRecord], DatasetControlEvidence]
StorageBuilder = Callable[[DatasetAdmissionRecord], StorageControlEvidence]


def build_evidence_builders(
    *,
    config: EvidenceConfig,
    scope: LocalPilotScope,
    times: PilotTimes,
    storage_key_sha256: str,
) -> tuple[DatasetBuilder, StorageBuilder]:
    if secure_equal(config.dataset_verifier_account_id, scope.account_id):
        raise LocalPilotExecutionError("PILOT_DATASET_VERIFIER_NOT_INDEPENDENT")
    if secure_equal(config.storage_verifier_account_id, scope.account_id):
        raise LocalPilotExecutionError("PILOT_STORAGE_VERIFIER_NOT_INDEPENDENT")

    def dataset_builder(record: DatasetAdmissionRecord) -> DatasetControlEvidence:
        inspection = record.inspection
        if inspection is None or not inspection.matched:
            raise LocalPilotExecutionError("PILOT_INSPECTION_EVIDENCE_MISSING")
        if record.policy_content_hash is None:
            raise LocalPilotExecutionError("PILOT_INSPECTION_POLICY_MISMATCH")
        declaration = record.declaration
        return DatasetControlEvidence(
            evidence_id=config.dataset_evidence_id,
            tenant_id=scope.tenant_id,
            dataset_id=declaration.dataset_id,
            original_file_sha256=declaration.original_file_sha256,
            owner_authority_reference=declaration.owner_authority_reference,
            reporting_period_start=declaration.reporting_period_start,
            reporting_period_end=declaration.reporting_period_end,
            timezone=declaration.timezone,
            control_totals_sha256=declaration.control_totals_sha256,
            policy_content_hash=record.policy_content_hash,
            workbook_sha256=inspection.workbook_sha256,
            structural_fingerprint_sha256=inspection.structural_fingerprint_sha256,
            matched_schema_id=inspection.matched_schema_id or "unmatched",
            matched_schema_version=inspection.matched_schema_version or "unmatched",
            matched_schema_authority_reference=(
                inspection.matched_schema_authority_reference or "unmatched"
            ),
            source_authority_verified=config.source_authority_verified,
            report_period_verified=config.report_period_verified,
            control_totals_verified=config.control_totals_verified,
            direct_identifiers_absent_or_approved=(
                config.direct_identifiers_absent_or_approved
            ),
            malware_scan_clean=config.malware_scan_clean,
            malware_scan_evidence_sha256=config.malware_scan_evidence_sha256,
            verified_at=times.admitted_at,
            verifier_account_id=config.dataset_verifier_account_id,
        )

    def storage_builder(record: DatasetAdmissionRecord) -> StorageControlEvidence:
        return StorageControlEvidence(
            evidence_id=config.storage_evidence_id,
            tenant_id=scope.tenant_id,
            dataset_id=record.declaration.dataset_id,
            original_file_sha256=record.declaration.original_file_sha256,
            storage_key_sha256=storage_key_sha256,
            transport_encrypted=config.transport_encrypted,
            encryption_at_rest=config.encryption_at_rest,
            tenant_scoped_paths=config.tenant_scoped_paths,
            immutable_original=config.immutable_original,
            separated_quarantine_and_admitted_zones=(
                config.separated_quarantine_and_admitted_zones
            ),
            least_privilege_credentials=config.least_privilege_credentials,
            verified_at=times.admitted_at,
            verifier_account_id=config.storage_verifier_account_id,
            storage_environment=StorageEnvironment.LOCAL_SINGLE_USER,
            loopback_only=config.loopback_only,
        )

    return dataset_builder, storage_builder


__all__ = ["build_evidence_builders"]
