from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from typing import Any

from quantum.finance import canonical_hash

from ._scope import LocalPilotExecutionError, LocalPilotScope


def _hash(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _finance_summary(results: object) -> dict[str, Any]:
    if not isinstance(results, Mapping):
        raise LocalPilotExecutionError("PILOT_FINANCE_RESULTS_INVALID")
    summary: dict[str, Any] = {}
    for label, result in results.items():
        if not isinstance(label, str) or not isinstance(result, Mapping):
            raise LocalPilotExecutionError("PILOT_FINANCE_RESULTS_INVALID")
        metrics = result.get("results")
        if not isinstance(metrics, Mapping):
            raise LocalPilotExecutionError("PILOT_FINANCE_RESULTS_INVALID")
        states = {
            metric_id: metric.get("state")
            for metric_id, metric in metrics.items()
            if isinstance(metric_id, str) and isinstance(metric, Mapping)
        }
        summary[label] = {
            "input_hash": result.get("input_hash"),
            "result_hash": result.get("result_hash"),
            "publication_state": result.get("publication_state"),
            "metric_states": states,
        }
    return summary


def build_redacted_evidence(
    *,
    run_id: str,
    scope: LocalPilotScope,
    core_result: Mapping[str, Any],
    admission_summary: Mapping[str, Any],
    staging: Mapping[str, Any],
    finance_lineage: Mapping[str, Any],
) -> dict[str, Any]:
    reconciliation = core_result.get("reconciliation")
    if not isinstance(reconciliation, Mapping):
        raise LocalPilotExecutionError("PILOT_RECONCILIATION_RESULT_INVALID")
    evidence: dict[str, Any] = {
        "schema_version": "quantum-local-pilot-evidence-v1",
        "run_id_sha256": _hash(run_id),
        "scope": {
            "operator_id_sha256": _hash(scope.operator_id),
            "organization_id_sha256": _hash(scope.organization_id),
            "tenant_id_sha256": _hash(scope.tenant_id),
            "account_id_sha256": _hash(scope.account_id),
            "host": scope.host,
            "port": scope.port,
            "read_only": scope.read_only,
            "marketplace_write_enabled": scope.marketplace_write_enabled,
        },
        "dataset": core_result.get("dataset"),
        "admission": dict(admission_summary),
        "staging": dict(staging),
        "finance": _finance_summary(core_result.get("finance_results")),
        "finance_lineage": dict(finance_lineage),
        "reconciliation": {
            "state": reconciliation.get("state"),
            "content_hash": canonical_hash(reconciliation),
        },
        "executed_at": core_result.get("executed_at"),
        "pilot_state": "LOCAL_EXECUTION_RECONCILED",
        "release_state": "RELEASE_BLOCKED",
        "limitations": [
            "ROW_LEVEL_NORMALIZATION_EVIDENCE_EXTERNAL",
            "BACKUP_RESTORE_EVIDENCE_REQUIRED",
            "INDEPENDENT_REVIEW_REQUIRED",
            "PRODUCTION_RELEASE_BLOCKED",
        ],
        "evidence_hash": "",
    }
    evidence["evidence_hash"] = canonical_hash(
        evidence,
        exclude=frozenset({"evidence_hash"}),
    )
    return evidence


__all__ = ["build_redacted_evidence"]
