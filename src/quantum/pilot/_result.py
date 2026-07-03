from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from datetime import datetime
from typing import Any

from quantum.finance import canonical_hash
from quantum.ingestion.admission_v2 import DatasetAdmissionRecord

from ._scope import LocalPilotScope


def build_execution_result(
    *,
    scope: LocalPilotScope,
    admitted: DatasetAdmissionRecord,
    finance_results: Mapping[str, Mapping[str, Any]],
    reconciliation: Mapping[str, Any],
    executed_at: datetime,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": "quantum-local-pilot-execution-v1",
        "scope": asdict(scope),
        "dataset": {
            "dataset_id": admitted.declaration.dataset_id,
            "original_file_sha256": admitted.declaration.original_file_sha256,
            "state": admitted.state.value,
        },
        "finance_results": dict(finance_results),
        "reconciliation": dict(reconciliation),
        "executed_at": executed_at.isoformat(),
        "release_state": "RELEASE_BLOCKED",
        "raw_payload_persisted": False,
    }
    result["evidence_hash"] = canonical_hash(
        result,
        exclude=frozenset({"evidence_hash"}),
    )
    return result


__all__ = ["build_execution_result"]
