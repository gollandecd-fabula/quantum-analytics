from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class RunnerBundle:
    run_id: str
    manifest_path: Path
    source_path: Path
    payload: bytes
    scope: Any
    tenant: Any
    times: Any
    declaration: Any
    inspection_policy: Any
    evidence_config: Any
    finance_requests: Any
    finance_lineage: Any
    source_snapshot: Any
    metric_bindings: Any
    reconciliation_policy: Any


__all__ = ["RunnerBundle"]
