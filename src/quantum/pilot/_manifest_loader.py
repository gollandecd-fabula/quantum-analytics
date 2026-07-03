from __future__ import annotations

from pathlib import Path

from ._evidence_config import build_evidence_config
from ._manifest_bundle import RunnerBundle
from ._manifest_calculation import (
    build_finance_requests,
    build_metric_bindings,
    build_reconciliation_policy,
    build_source_snapshot,
)
from ._manifest_common import exact_keys, load_json, text
from ._manifest_dataset import build_declaration
from ._manifest_lineage import build_finance_lineage
from ._manifest_policy import build_inspection_policy
from ._manifest_scope import build_scope
from ._manifest_time import build_times
from ._source_file import read_source_file

_TOP_LEVEL_FIELDS = {
    "schema_version",
    "run_id",
    "source_file",
    "scope",
    "timestamps",
    "dataset",
    "inspection_policy",
    "controls",
    "finance_requests",
    "finance_lineage",
    "source_snapshot",
    "reconciliation_metric_bindings",
    "reconciliation_policy",
}


def load_runner_bundle(manifest_path: Path) -> RunnerBundle:
    manifest = load_json(manifest_path)
    exact_keys(manifest, _TOP_LEVEL_FIELDS, "PILOT_MANIFEST_INVALID")
    if manifest.get("schema_version") != "quantum-local-pilot-manifest-v1":
        from ._scope import LocalPilotExecutionError

        raise LocalPilotExecutionError("PILOT_MANIFEST_SCHEMA_INVALID")
    run_id = text(manifest["run_id"], "PILOT_RUN_ID_INVALID")
    scope, tenant = build_scope(manifest["scope"])
    times = build_times(manifest["timestamps"])
    inspection_policy = build_inspection_policy(manifest["inspection_policy"])
    source_path, payload = read_source_file(
        manifest_path=manifest_path,
        source_file=manifest["source_file"],
        max_file_bytes=inspection_policy.limits.max_file_bytes,
    )
    declaration = build_declaration(
        manifest["dataset"],
        scope=scope,
        payload=payload,
        declared_at=times.declared_at,
    )
    controls = build_evidence_config(manifest["controls"])
    finance_requests = build_finance_requests(manifest["finance_requests"])
    labels = set(finance_requests)
    finance_lineage = build_finance_lineage(
        manifest["finance_lineage"],
        finance_labels=labels,
        dataset_id=declaration.dataset_id,
    )
    source_snapshot = build_source_snapshot(
        manifest["source_snapshot"],
        dataset_id=declaration.dataset_id,
        original_file_sha256=declaration.original_file_sha256,
    )
    metric_bindings = build_metric_bindings(
        manifest["reconciliation_metric_bindings"],
        finance_labels=labels,
    )
    reconciliation_policy = build_reconciliation_policy(
        manifest["reconciliation_policy"]
    )
    return RunnerBundle(
        run_id=run_id,
        manifest_path=manifest_path.resolve(),
        source_path=source_path,
        payload=payload,
        scope=scope,
        tenant=tenant,
        times=times,
        declaration=declaration,
        inspection_policy=inspection_policy,
        evidence_config=controls,
        finance_requests=finance_requests,
        finance_lineage=finance_lineage,
        source_snapshot=source_snapshot,
        metric_bindings=metric_bindings,
        reconciliation_policy=reconciliation_policy,
    )


__all__ = ["load_runner_bundle"]
