from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict
from datetime import datetime
from hashlib import sha256
from typing import Any

from quantum.access import TenantContext
from quantum.finance import calculate, canonical_hash
from quantum.ingestion.admission_v2 import (
    DatasetAdmissionRecord,
    DatasetAdmissionState,
    DatasetControlEvidence,
    RealDatasetAdmissionRegistryV2,
    StorageControlEvidence,
)
from quantum.reconciliation import reconcile_source_totals

from ._bindings import (
    MetricBindings,
    finance_result_snapshot,
    validate_source_identity,
)
from ._scope import (
    LocalPilotExecutionError,
    LocalPilotScope,
    require_aware,
    scope_matches_declaration,
    validate_finance_request,
    validate_time_order,
)


EvidenceBuilder = Callable[
    [DatasetAdmissionRecord],
    DatasetControlEvidence | StorageControlEvidence,
]


def _require_same_inspection_policy(
    record: DatasetAdmissionRecord,
    inspection_policy: object,
) -> None:
    expected = (
        getattr(inspection_policy, "policy_id", None),
        getattr(inspection_policy, "version", None),
        getattr(inspection_policy, "content_hash", None),
    )
    actual = (
        record.policy_id,
        record.policy_version,
        record.policy_content_hash,
    )
    if expected != actual:
        raise LocalPilotExecutionError(
            "PILOT_INSPECTION_POLICY_MISMATCH"
        )


def _admit_or_reuse(
    *,
    registry: RealDatasetAdmissionRegistryV2,
    tenant: TenantContext,
    declaration: object,
    payload: bytes,
    inspection_policy: object,
    dataset_control_evidence_builder: EvidenceBuilder,
    storage_evidence_builder: EvidenceBuilder,
    observed_at: datetime,
    admitted_at: datetime,
    reconciled_at: datetime,
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
        _require_same_inspection_policy(current, inspection_policy)
    if current.state is DatasetAdmissionState.VALIDATED:
        dataset_evidence = dataset_control_evidence_builder(current)
        storage_evidence = storage_evidence_builder(current)
        if not isinstance(dataset_evidence, DatasetControlEvidence):
            raise LocalPilotExecutionError(
                "PILOT_DATASET_EVIDENCE_INVALID"
            )
        if not isinstance(storage_evidence, StorageControlEvidence):
            raise LocalPilotExecutionError(
                "PILOT_STORAGE_EVIDENCE_INVALID"
            )
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
        as_of=reconciled_at,
    )


def execute_local_read_only_pilot(
    *,
    scope: LocalPilotScope,
    tenant: TenantContext,
    registry: RealDatasetAdmissionRegistryV2,
    declaration: object,
    payload: bytes,
    inspection_policy: object,
    dataset_control_evidence_builder: EvidenceBuilder,
    storage_evidence_builder: EvidenceBuilder,
    observed_at: datetime,
    admitted_at: datetime,
    finance_requests: Mapping[str, Mapping[str, Any]],
    source_snapshot: Mapping[str, Any],
    reconciliation_metric_bindings: MetricBindings,
    reconciliation_policy: Mapping[str, Any],
    reconciled_at: datetime,
) -> dict[str, Any]:
    """Execute the governed local pilot without persisting raw bytes."""
    if not isinstance(scope, LocalPilotScope):
        raise LocalPilotExecutionError("PILOT_SCOPE_REQUIRED")
    scope.validate(tenant)
    if not isinstance(registry, RealDatasetAdmissionRegistryV2):
        raise LocalPilotExecutionError("PILOT_ADMISSION_REGISTRY_REQUIRED")
    if not scope_matches_declaration(scope, declaration):
        raise LocalPilotExecutionError("PILOT_DECLARATION_SCOPE_MISMATCH")
    if not isinstance(payload, bytes) or not payload:
        raise LocalPilotExecutionError("PILOT_RAW_BYTES_REQUIRED")
    expected_hash = getattr(declaration, "original_file_sha256", None)
    expected_size = getattr(declaration, "original_size_bytes", None)
    if (
        not isinstance(expected_hash, str)
        or not isinstance(expected_size, int)
        or sha256(payload).hexdigest() != expected_hash
        or len(payload) != expected_size
    ):
        raise LocalPilotExecutionError("PILOT_RAW_BYTES_MISMATCH")
    if not callable(dataset_control_evidence_builder) or not callable(
        storage_evidence_builder
    ):
        raise LocalPilotExecutionError("PILOT_EVIDENCE_BUILDER_REQUIRED")
    require_aware(observed_at, "PILOT_OBSERVED_TIMESTAMP_INVALID")
    require_aware(admitted_at, "PILOT_ADMITTED_TIMESTAMP_INVALID")
    require_aware(reconciled_at, "PILOT_RECONCILED_TIMESTAMP_INVALID")
    validate_time_order(observed_at, admitted_at, reconciled_at)

    admitted = _admit_or_reuse(
        registry=registry,
        tenant=tenant,
        declaration=declaration,
        payload=payload,
        inspection_policy=inspection_policy,
        dataset_control_evidence_builder=dataset_control_evidence_builder,
        storage_evidence_builder=storage_evidence_builder,
        observed_at=observed_at,
        admitted_at=admitted_at,
        reconciled_at=reconciled_at,
    )
    source_snapshot = validate_source_identity(source_snapshot, admitted)

    if not isinstance(finance_requests, Mapping) or not finance_requests:
        raise LocalPilotExecutionError("PILOT_FINANCE_REQUESTS_REQUIRED")
    labels = tuple(finance_requests)
    if any(not isinstance(label, str) or not label for label in labels):
        raise LocalPilotExecutionError("PILOT_FINANCE_LABEL_INVALID")
    finance_results: dict[str, Mapping[str, Any]] = {}
    for label in sorted(labels):
        request = validate_finance_request(
            label,
            finance_requests[label],
            scope,
            admitted_at=admitted_at,
            reconciled_at=reconciled_at,
        )
        result = calculate(request)
        if result.get("publication_state") != "PREVIEW_ONLY":
            raise LocalPilotExecutionError(
                "PILOT_PUBLICATION_STATE_INVALID"
            )
        finance_results[label] = result

    inspection = admitted.inspection
    if inspection is None:
        raise LocalPilotExecutionError("PILOT_INSPECTION_EVIDENCE_MISSING")
    calculated_snapshot = finance_result_snapshot(
        dataset_id=admitted.declaration.dataset_id,
        original_file_sha256=admitted.declaration.original_file_sha256,
        row_count=inspection.data_row_count,
        finance_results=finance_results,
        metric_bindings=reconciliation_metric_bindings,
    )
    reconciliation = reconcile_source_totals(
        admission_record=admitted,
        tenant_id=scope.tenant_id,
        account_id=scope.account_id,
        source_snapshot=source_snapshot,
        calculated_snapshot=calculated_snapshot,
        policy=reconciliation_policy,
        reconciled_at=reconciled_at,
    )
    if reconciliation.get("state") != "RECONCILED":
        raise LocalPilotExecutionError("PILOT_RECONCILIATION_CONFLICT")

    evidence: dict[str, Any] = {
        "schema_version": "quantum-local-pilot-execution-v1",
        "scope": asdict(scope),
        "dataset": {
            "dataset_id": admitted.declaration.dataset_id,
            "original_file_sha256": admitted.declaration.original_file_sha256,
            "state": admitted.state.value,
        },
        "finance_results": finance_results,
        "reconciliation": reconciliation,
        "executed_at": reconciled_at.isoformat(),
        "release_state": "RELEASE_BLOCKED",
        "raw_payload_persisted": False,
    }
    evidence["evidence_hash"] = canonical_hash(
        evidence,
        exclude=frozenset({"evidence_hash"}),
    )
    return evidence


__all__ = ["execute_local_read_only_pilot"]
