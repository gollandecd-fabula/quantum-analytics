from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from quantum.access import TenantContext
from quantum.ingestion.admission_v2 import (
    DatasetAdmissionRecord,
    DatasetAdmissionState,
    DatasetControlEvidence,
    RealDatasetAdmissionRegistryV2,
    StorageControlEvidence,
)

from ._scope import LocalPilotExecutionError

EvidenceBuilder = Callable[
    [DatasetAdmissionRecord],
    DatasetControlEvidence | StorageControlEvidence,
]


def _require_same_policy(record: DatasetAdmissionRecord, policy: object) -> None:
    expected = (
        getattr(policy, "policy_id", None),
        getattr(policy, "version", None),
        getattr(policy, "content_hash", None),
    )
    actual = (record.policy_id, record.policy_version, record.policy_content_hash)
    if expected != actual:
        raise LocalPilotExecutionError("PILOT_INSPECTION_POLICY_MISMATCH")


def admit_or_reuse(
    *,
    registry: RealDatasetAdmissionRegistryV2,
    tenant: TenantContext,
    declaration: object,
    payload: bytes,
    inspection_policy: object,
    dataset_evidence_builder: EvidenceBuilder,
    storage_evidence_builder: EvidenceBuilder,
    observed_at: datetime,
    admitted_at: datetime,
    access_at: datetime,
) -> DatasetAdmissionRecord:
    current = registry.declare(tenant=tenant, declaration=declaration)
    if current.state in {
        DatasetAdmissionState.DECLARED,
        DatasetAdmissionState.QUARANTINED,
    }:
        current = registry.inspect_and_validate(
            tenant=tenant,
            dataset_id=current.declaration.dataset_id,
            payload=payload,
            policy=inspection_policy,
            observed_at=observed_at,
        )
    if current.state in {
        DatasetAdmissionState.VALIDATED,
        DatasetAdmissionState.ADMITTED,
    }:
        _require_same_policy(current, inspection_policy)
    if current.state is DatasetAdmissionState.VALIDATED:
        dataset_evidence = dataset_evidence_builder(current)
        storage_evidence = storage_evidence_builder(current)
        if not isinstance(dataset_evidence, DatasetControlEvidence):
            raise LocalPilotExecutionError("PILOT_DATASET_EVIDENCE_INVALID")
        if not isinstance(storage_evidence, StorageControlEvidence):
            raise LocalPilotExecutionError("PILOT_STORAGE_EVIDENCE_INVALID")
        current = registry.admit(
            tenant=tenant,
            dataset_id=current.declaration.dataset_id,
            dataset_control_evidence=dataset_evidence,
            storage_evidence=storage_evidence,
            admitted_at=admitted_at,
        )
    if current.state is not DatasetAdmissionState.ADMITTED:
        raise LocalPilotExecutionError(
            "PILOT_DATASET_NOT_VALIDATED:" + current.state.value
        )
    return registry.require_admitted(
        tenant=tenant,
        dataset_id=current.declaration.dataset_id,
        as_of=access_at,
    )


__all__ = ["EvidenceBuilder", "admit_or_reuse"]
