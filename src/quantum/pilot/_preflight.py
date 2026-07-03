from __future__ import annotations

from datetime import datetime
from hashlib import sha256

from quantum.access import TenantContext
from quantum.ingestion.admission_v2 import RealDatasetAdmissionRegistryV2

from ._scope import (
    LocalPilotExecutionError,
    LocalPilotScope,
    require_aware,
    scope_matches_declaration,
    validate_time_order,
)


def validate_execution_inputs(
    *,
    scope: object,
    tenant: object,
    registry: object,
    declaration: object,
    payload: object,
    dataset_evidence_builder: object,
    storage_evidence_builder: object,
    observed_at: datetime,
    admitted_at: datetime,
    reconciled_at: datetime,
) -> tuple[LocalPilotScope, TenantContext, RealDatasetAdmissionRegistryV2, bytes]:
    if not isinstance(scope, LocalPilotScope):
        raise LocalPilotExecutionError("PILOT_SCOPE_REQUIRED")
    if not isinstance(tenant, TenantContext):
        raise LocalPilotExecutionError("PILOT_TENANT_CONTEXT_REQUIRED")
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
    if not callable(dataset_evidence_builder) or not callable(storage_evidence_builder):
        raise LocalPilotExecutionError("PILOT_EVIDENCE_BUILDER_REQUIRED")
    require_aware(observed_at, "PILOT_OBSERVED_TIMESTAMP_INVALID")
    require_aware(admitted_at, "PILOT_ADMITTED_TIMESTAMP_INVALID")
    require_aware(reconciled_at, "PILOT_RECONCILED_TIMESTAMP_INVALID")
    validate_time_order(observed_at, admitted_at, reconciled_at)
    return scope, tenant, registry, payload


__all__ = ["validate_execution_inputs"]
