from __future__ import annotations

from typing import Any

from . import verification as _base


def verify_evidence_chain(graph: object, **kwargs: Any) -> tuple[str, ...]:
    """Public Evidence Chain verifier backed by the canonical iterative engine."""
    return _base.verify_evidence_chain(graph, **kwargs)


def verify_metric_snapshot(snapshot: object) -> tuple[str, ...]:
    """Public Metric Snapshot verifier backed by the canonical strict engine."""
    return _base.verify_metric_snapshot(snapshot)


def diagnose_metric_snapshot(snapshot: object) -> str | None:
    errors = verify_metric_snapshot(snapshot)
    return errors[0] if errors else None
