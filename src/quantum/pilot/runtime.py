from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
import hmac
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


class LocalPilotExecutionError(ValueError):
    """Fail-closed local-pilot orchestration error with a stable code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class LocalPilotScope:
    host: str
    port: int
    operator_id: str
    organization_id: str
    tenant_id: str
    account_id: str
    read_only: bool = True
    single_operator: bool = True
    single_organization: bool = True
    marketplace_write_enabled: bool = False
    production_credentials_enabled: bool = False
    public_hosting_enabled: bool = False

    def validate(self, tenant: TenantContext) -> None:
        if self.host != "127.0.0.1":
            raise LocalPilotExecutionError("PILOT_LOOPBACK_REQUIRED")
        if not isinstance(self.port, int) or isinstance(self.port, bool) or not (1 <= self.port <= 65535):
            raise LocalPilotExecutionError("PILOT_PORT_INVALID")
        for value, code in (
            (self.operator_id, "PILOT_OPERATOR_ID_INVALID"),
            (self.organization_id, "PILOT_ORGANIZATION_ID_INVALID"),
            (self.tenant_id, "PILOT_TENANT_ID_INVALID"),
            (self.account_id, "PILOT_ACCOUNT_ID_INVALID"),
        ):
            if not isinstance(value, str) or not value:
                raise LocalPilotExecutionError(code)
        if not self.read_only:
            raise LocalPilotExecutionError("PILOT_READ_ONLY_REQUIRED")
        if not self.single_operator:
            raise LocalPilotExecutionError("PILOT_SINGLE_OPERATOR_REQUIRED")
        if not self.single_organization:
            raise LocalPilotExecutionError("PILOT_SINGLE_ORGANIZATION_REQUIRED")
        if self.marketplace_write_enabled:
            raise LocalPilotExecutionError("PILOT_MARKETPLACE_WRITES_FORBIDDEN")
        if self.production_credentials_enabled:
            raise LocalPilotExecutionError("PILOT_PRODUCTION_CREDENTIALS_FORBIDDEN")
        if self.public_hosting_enabled:
            raise LocalPilotExecutionError("PILOT_PUBLIC_HOSTING_FORBIDDEN")
        if not isinstance(tenant, TenantContext):
            raise LocalPilotExecutionError("PILOT_TENANT_CONTEXT_REQUIRED")
        if not hmac.compare_digest(self.tenant_id, tenant.tenant_id) or not hmac.compare_digest(
            self.account_id,
            tenant.account_id,
        ):
            raise LocalPilotExecutionError("PILOT_TENANT_SCOPE_MISMATCH")


EvidenceBuilder = Callable[[DatasetAdmissionRecord], DatasetControlEvidence | StorageControlEvidence]
SnapshotBuilder = Callable[[Mapping[str, Mapping[str, Any]]], Mapping[str, Any]]


def _require_aware(value: datetime, code: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise LocalPilotExecutionError(code)


def _scope_matches_declaration(scope: LocalPilotScope, declaration: object) -> bool:
    tenant_id = getattr(declaration, "tenant_id", None)
    uploader_account_id = getattr(declaration, "uploader_account_id", None)
    return (
        isinstance(tenant_id, str)
        and isinstance(uploader_account_id, str)
        and hmac.compare_digest(scope.tenant_id, tenant_id)
        and hmac.compare_digest(scope.account_id, uploader_account_id)
    )


def _validate_finance_request(label: str, request: object, scope: LocalPilotScope) -> Mapping[str, Any]:
    if not isinstance(label, str) or not label:
        raise LocalPilotExecutionError("PILOT_FINANCE_LABEL_INVALID")
    if not isinstance(request, Mapping):
        raise LocalPilotExecutionError("PILOT_FINANCE_REQUEST_INVALID")
    organization_id = request.get("organization_id")
    if not isinstance(organization_id, str) or not hmac.compare_digest(
        organization_id,
        scope.organization_id,
    ):
        raise LocalPilotExecutionError("PILOT_FINANCE_ORGANIZATION_MISMATCH")
    if request.get("mode") != "ACTUAL" or request.get("scenario_id") is not None:
        raise LocalPilotExecutionError("PILOT_ACTUAL_MODE_REQUIRED")
    return request


def _metric_view(metric: object) -> dict[str, Any]:
    if not isinstance(metric, Mapping):
        raise LocalPilotExecutionError("PILOT_RECONCILIATION_METRIC_INVALID")
    required = ("state", "value", "value_type", "unit", "currency")
    if any(key not in metric for key in required):
        raise LocalPilotExecutionError("PILOT_RECONCILIATION_METRIC_INVALID")
    return {key: metric[key] for key in required}


def finance_result_snapshot(
    *,
    dataset_id: str,
    original_file_sha256: str,
    row_count: int,
    finance_results: Mapping[str, Mapping[str, Any]],
    metric_bindings: Mapping[str, tuple[str, str]],
) -> dict[str, Any]:
    """Build a B2 snapshot from explicit category/result metric bindings."""
    if not isinstance(row_count, int) or isinstance(row_count, bool) or row_count < 0:
        raise LocalPilotExecutionError("PILOT_RECONCILIATION_ROW_COUNT_INVALID")
    totals: dict[str, dict[str, Any]] = {}
    for target_metric, binding in metric_bindings.items():
        if (
            not isinstance(target_metric, str)
            or not target_metric
            or not isinstance(binding, tuple)
            or len(binding) != 2
        ):
            raise LocalPilotExecutionError("PILOT_RECONCILIATION_BINDING_INVALID")
        label, result_metric = binding
        result = finance_results.get(label)
        if not isinstance(result, Mapping):
            raise LocalPilotExecutionError("PILOT_RECONCILIATION_BINDING_INVALID")
        metrics = result.get("results")
        if not isinstance(metrics, Mapping) or result_metric not in metrics:
            raise LocalPilotExecutionError("PILOT_RECONCILIATION_BINDING_INVALID")
        totals[target_metric] = _metric_view(metrics[result_metric])
    return {
        "dataset_id": dataset_id,
        "original_file_sha256": original_file_sha256,
        "row_count": row_count,
        "totals": totals,
    }


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
    calculated_snapshot_builder: SnapshotBuilder,
    reconciliation_policy: Mapping[str, Any],
    reconciled_at: datetime,
) -> dict[str, Any]:
    """Execute the governed local pilot chain without logging or persisting raw bytes."""
    if not isinstance(scope, LocalPilotScope):
        raise LocalPilotExecutionError("PILOT_SCOPE_REQUIRED")
    scope.validate(tenant)
    if not isinstance(registry, RealDatasetAdmissionRegistryV2):
        raise LocalPilotExecutionError("PILOT_ADMISSION_REGISTRY_REQUIRED")
    if not _scope_matches_declaration(scope, declaration):
        raise LocalPilotExecutionError("PILOT_DECLARATION_SCOPE_MISMATCH")
    if not isinstance(payload, bytes) or not payload:
        raise LocalPilotExecutionError("PILOT_RAW_BYTES_REQUIRED")
    if not callable(dataset_control_evidence_builder) or not callable(storage_evidence_builder):
        raise LocalPilotExecutionError("PILOT_EVIDENCE_BUILDER_REQUIRED")
    if not callable(calculated_snapshot_builder):
        raise LocalPilotExecutionError("PILOT_SNAPSHOT_BUILDER_REQUIRED")
    _require_aware(observed_at, "PILOT_OBSERVED_TIMESTAMP_INVALID")
    _require_aware(admitted_at, "PILOT_ADMITTED_TIMESTAMP_INVALID")
    _require_aware(reconciled_at, "PILOT_RECONCILED_TIMESTAMP_INVALID")

    declared = registry.declare(tenant=tenant, declaration=declaration)
    validated = registry.inspect_and_validate(
        tenant=tenant,
        dataset_id=declared.declaration.dataset_id,
        payload=payload,
        policy=inspection_policy,
        observed_at=observed_at,
    )
    if validated.state != DatasetAdmissionState.VALIDATED:
        raise LocalPilotExecutionError(
            "PILOT_DATASET_NOT_VALIDATED:" + validated.state.value
        )
    dataset_evidence = dataset_control_evidence_builder(validated)
    storage_evidence = storage_evidence_builder(validated)
    if not isinstance(dataset_evidence, DatasetControlEvidence):
        raise LocalPilotExecutionError("PILOT_DATASET_EVIDENCE_INVALID")
    if not isinstance(storage_evidence, StorageControlEvidence):
        raise LocalPilotExecutionError("PILOT_STORAGE_EVIDENCE_INVALID")
    admitted = registry.admit(
        tenant=tenant,
        dataset_id=validated.declaration.dataset_id,
        dataset_control_evidence=dataset_evidence,
        storage_evidence=storage_evidence,
        admitted_at=admitted_at,
    )
    registry.require_admitted(
        tenant=tenant,
        dataset_id=admitted.declaration.dataset_id,
        as_of=reconciled_at,
    )

    if not isinstance(finance_requests, Mapping) or not finance_requests:
        raise LocalPilotExecutionError("PILOT_FINANCE_REQUESTS_REQUIRED")
    finance_results: dict[str, Mapping[str, Any]] = {}
    for label in sorted(finance_requests):
        request = _validate_finance_request(label, finance_requests[label], scope)
        result = calculate(request)
        if result.get("publication_state") != "PREVIEW_ONLY":
            raise LocalPilotExecutionError("PILOT_PUBLICATION_STATE_INVALID")
        finance_results[label] = result

    calculated_snapshot = calculated_snapshot_builder(finance_results)
    if not isinstance(calculated_snapshot, Mapping):
        raise LocalPilotExecutionError("PILOT_CALCULATED_SNAPSHOT_INVALID")
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


__all__ = [
    "LocalPilotExecutionError",
    "LocalPilotScope",
    "execute_local_read_only_pilot",
    "finance_result_snapshot",
]
