from __future__ import annotations

from pathlib import Path
from typing import Any

from quantum.ingestion.admission_v2 import RealDatasetAdmissionRegistryV2

from ._admission_flow import admit_or_reuse
from ._evidence_builders import build_evidence_builders
from ._errors import KNOWN_PILOT_ERRORS, error_code
from ._finance_flow import calculate_finance_results
from ._manifest_bundle import RunnerBundle
from ._preflight import validate_execution_inputs
from ._reconciliation_flow import reconcile_pilot_results
from ._redacted_evidence import build_redacted_evidence
from ._result import build_execution_result
from ._scope import LocalPilotExecutionError
from ._workspace_create import create_workspace
from ._workspace_output import write_failure, write_outputs
from ._workspace_stage import promote_payload, stage_payload


def execute_runner_bundle(
    bundle: RunnerBundle,
    *,
    workspace_base: Path,
) -> dict[str, Any]:
    layout = None
    registry = RealDatasetAdmissionRegistryV2()
    try:
        layout = create_workspace(
            base=workspace_base,
            tenant_id=bundle.scope.tenant_id,
            run_id=bundle.run_id,
            dataset_id=bundle.declaration.dataset_id,
        )
        staging = stage_payload(
            layout,
            payload=bundle.payload,
            filename=bundle.source_path.name,
        )
        dataset_builder, storage_builder = build_evidence_builders(
            config=bundle.evidence_config,
            scope=bundle.scope,
            times=bundle.times,
            storage_key_sha256=staging["storage_key_sha256"],
        )
        validate_execution_inputs(
            scope=bundle.scope,
            tenant=bundle.tenant,
            registry=registry,
            declaration=bundle.declaration,
            payload=bundle.payload,
            dataset_evidence_builder=dataset_builder,
            storage_evidence_builder=storage_builder,
            observed_at=bundle.times.observed_at,
            admitted_at=bundle.times.admitted_at,
            reconciled_at=bundle.times.reconciled_at,
        )
        admitted = admit_or_reuse(
            registry=registry,
            tenant=bundle.tenant,
            declaration=bundle.declaration,
            payload=bundle.payload,
            inspection_policy=bundle.inspection_policy,
            dataset_evidence_builder=dataset_builder,
            storage_evidence_builder=storage_builder,
            observed_at=bundle.times.observed_at,
            admitted_at=bundle.times.admitted_at,
            access_at=bundle.times.reconciled_at,
        )
        promote_payload(
            layout,
            payload=bundle.payload,
            expected_sha256=bundle.declaration.original_file_sha256,
        )
        finance_results, calculated_snapshot = calculate_finance_results(
            scope=bundle.scope,
            admitted=admitted,
            finance_requests=bundle.finance_requests,
            metric_bindings=bundle.metric_bindings,
            reconciled_at=bundle.times.reconciled_at,
        )
        reconciliation = reconcile_pilot_results(
            scope=bundle.scope,
            admitted=admitted,
            source_snapshot=bundle.source_snapshot,
            calculated_snapshot=calculated_snapshot,
            policy=bundle.reconciliation_policy,
            reconciled_at=bundle.times.reconciled_at,
        )
        core_result = build_execution_result(
            scope=bundle.scope,
            admitted=admitted,
            finance_results=finance_results,
            reconciliation=reconciliation,
            executed_at=bundle.times.reconciled_at,
        )
        admission_summary = registry.evidence_summary(
            tenant=bundle.tenant,
            dataset_id=admitted.declaration.dataset_id,
        )
        evidence = build_redacted_evidence(
            run_id=bundle.run_id,
            scope=bundle.scope,
            core_result=core_result,
            admission_summary=admission_summary,
            staging=staging,
            finance_lineage=bundle.finance_lineage,
        )
        result_path, evidence_path = write_outputs(
            layout,
            operator_result=core_result,
            evidence=evidence,
        )
        return {
            "schema_version": "quantum-local-pilot-run-v1",
            "status": "RECONCILED",
            "run_id": bundle.run_id,
            "dataset_id": admitted.declaration.dataset_id,
            "original_file_sha256": admitted.declaration.original_file_sha256,
            "result_path": str(result_path),
            "evidence_path": str(evidence_path),
            "evidence_hash": evidence["evidence_hash"],
            "release_state": "RELEASE_BLOCKED",
        }
    except KNOWN_PILOT_ERRORS as exc:
        if layout is not None:
            write_failure(layout, code=error_code(exc))
        raise
    except Exception as exc:
        if layout is not None:
            write_failure(layout, code="PILOT_INTERNAL_ERROR")
        raise LocalPilotExecutionError("PILOT_INTERNAL_ERROR") from exc


__all__ = ["execute_runner_bundle"]
