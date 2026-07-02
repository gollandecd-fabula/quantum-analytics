from __future__ import annotations

from ._admission_contracts_v2 import AdmissionError, DatasetAdmissionState, _aware_utc
from ._admission_evidence_checks_v2 import require_evidence_binding, require_evidence_times


def finalize_validated_record(registry, *, tenant, record, dataset_control, storage_control, decided_at):
    if record.state is not DatasetAdmissionState.VALIDATED:
        raise AdmissionError("DATASET_NOT_VALIDATED")
    if decided_at >= _aware_utc(record.declaration.retention_deadline, "DATASET_RETENTION_TIMEZONE_REQUIRED"):
        raise AdmissionError("DATASET_RETENTION_EXPIRED")
    require_evidence_binding(record, dataset_control, storage_control)
    require_evidence_times(record, dataset_control, storage_control, decided_at)
    declaration = record.declaration
    dataset_key = (tenant.tenant_id, dataset_control.evidence_id)
    storage_key = (tenant.tenant_id, storage_control.evidence_id)
    if registry._dataset_evidence_id_owners.get(dataset_key) not in (None, declaration.dataset_id):
        raise AdmissionError("DATASET_EVIDENCE_REPLAY_DETECTED")
    if registry._storage_evidence_id_owners.get(storage_key) not in (None, declaration.dataset_id):
        raise AdmissionError("STORAGE_EVIDENCE_REPLAY_DETECTED")
    updated = registry._transition(
        record,
        DatasetAdmissionState.ADMITTED,
        actor=tenant.account_id,
        at=decided_at,
        reason="DATASET_ADMITTED",
        dataset_control_evidence_id=dataset_control.evidence_id,
        storage_evidence_id=storage_control.evidence_id,
        storage_key_sha256=storage_control.storage_key_sha256,
    )
    registry._records[(tenant.tenant_id, declaration.dataset_id)] = updated
    registry._dataset_evidence_id_owners[dataset_key] = declaration.dataset_id
    registry._storage_evidence_id_owners[storage_key] = declaration.dataset_id
    return updated
