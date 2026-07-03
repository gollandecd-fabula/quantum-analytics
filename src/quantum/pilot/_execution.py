from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from quantum.access import TenantContext
from quantum.ingestion.admission_v2 import RealDatasetAdmissionRegistryV2

from ._admission_flow import EvidenceBuilder, admit_or_reuse
from ._bindings import MetricBindings
from ._finance_flow import calculate_finance_results
from ._preflight import validate_execution_inputs
from ._reconciliation_flow import reconcile_pilot_results
from ._result import build_execution_result
from ._scope import LocalPilotScope


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
    scope, tenant, registry, payload = validate_execution_inputs(
        scope=scope,
        tenant=tenant,
        registry=registry,
        declaration=declaration,
        payload=payload,
        dataset_evidence_builder=dataset_control_evidence_builder,
        storage_evidence_builder=storage_evidence_builder,
        observed_at=observed_at,
        admitted_at=admitted_at,
        reconciled_at=reconciled_at,
    )
    admitted = admit_or_reuse(
        registry=registry,
        tenant=tenant,
        declaration=declaration,
        payload=payload,
        inspection_policy=inspection_policy,
        dataset_evidence_builder=dataset_control_evidence_builder,
        storage_evidence_builder=storage_evidence_builder,
        observed_at=observed_at,
        admitted_at=admitted_at,
        access_at=reconciled_at,
    )
    finance_results, calculated_snapshot = calculate_finance_results(
        scope=scope,
        admitted=admitted,
        finance_requests=finance_requests,
        metric_bindings=reconciliation_metric_bindings,
        reconciled_at=reconciled_at,
    )
    reconciliation = reconcile_pilot_results(
        scope=scope,
        admitted=admitted,
        source_snapshot=source_snapshot,
        calculated_snapshot=calculated_snapshot,
        policy=reconciliation_policy,
        reconciled_at=reconciled_at,
    )
    return build_execution_result(
        scope=scope,
        admitted=admitted,
        finance_results=finance_results,
        reconciliation=reconciliation,
        executed_at=reconciled_at,
    )


__all__ = ["execute_local_read_only_pilot"]
