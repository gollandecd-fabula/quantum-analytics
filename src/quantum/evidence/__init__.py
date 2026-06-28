from __future__ import annotations

from typing import Any

from .verification import (
    EDGE_SIGNATURES,
    canonical_graph_hash,
    canonical_snapshot_hash,
    diagnose_metric_snapshot,
    verify_evidence_chain,
    verify_metric_snapshot,
)

PRIMARY_DIAGNOSTIC_PRIORITY = (
    "EVIDENCE_MALFORMED",
    "EVIDENCE_VERSION_INVALID",
    "EVIDENCE_TENANT_MISMATCH",
    "EVIDENCE_MODE_CONTAMINATION",
    "EVIDENCE_TIMESTAMP_INVALID",
    "EVIDENCE_HASH_MISMATCH",
    "EVIDENCE_NODE_MISSING",
    "EVIDENCE_NODE_DUPLICATE",
    "EVIDENCE_NODE_TYPE_INVALID",
    "EVIDENCE_EDGE_DUPLICATE",
    "EVIDENCE_EDGE_INVALID",
    "EVIDENCE_GRAPH_CYCLE",
    "EVIDENCE_REQUIRED_PATH_MISSING",
    "EVIDENCE_TRANSFORMATION_ORDER_AMBIGUOUS",
    "EVIDENCE_APPROVAL_MISSING",
    "EVIDENCE_SOURCE_FILE_UNAVAILABLE",
    "EVIDENCE_SOURCE_BYTES_MISMATCH",
    "EVIDENCE_ORPHAN_NODE",
)


def diagnose_evidence_chain(graph: object, **kwargs: Any) -> str | None:
    """Return the highest-priority diagnostic from the complete verifier output."""
    errors = verify_evidence_chain(graph, **kwargs)
    if not errors:
        return None
    present = set(errors)
    for code in PRIMARY_DIAGNOSTIC_PRIORITY:
        if code in present:
            return code
    return errors[0]


__all__ = [
    "EDGE_SIGNATURES",
    "PRIMARY_DIAGNOSTIC_PRIORITY",
    "canonical_graph_hash",
    "canonical_snapshot_hash",
    "diagnose_evidence_chain",
    "diagnose_metric_snapshot",
    "verify_evidence_chain",
    "verify_metric_snapshot",
]
