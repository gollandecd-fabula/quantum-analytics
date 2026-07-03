from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from ._manifest_common import exact_keys, integer, mapping, sha256_text, text
from ._scope import LocalPilotExecutionError

_LINEAGE_FIELDS = {
    "dataset_id",
    "normalization_evidence_sha256",
    "source_row_count",
}


def build_finance_lineage(
    value: object,
    *,
    finance_labels: set[str],
    dataset_id: str,
) -> dict[str, dict[str, Any]]:
    item = mapping(value, "PILOT_FINANCE_LINEAGE_INVALID")
    if set(item) != finance_labels:
        raise LocalPilotExecutionError("PILOT_FINANCE_LINEAGE_INVALID")
    try:
        expected_dataset_id = str(UUID(dataset_id))
    except ValueError as exc:
        raise LocalPilotExecutionError("PILOT_FINANCE_LINEAGE_INVALID") from exc
    output: dict[str, dict[str, Any]] = {}
    for label, raw in item.items():
        text(label, "PILOT_FINANCE_LINEAGE_INVALID")
        lineage = mapping(raw, "PILOT_FINANCE_LINEAGE_INVALID")
        exact_keys(lineage, _LINEAGE_FIELDS, "PILOT_FINANCE_LINEAGE_INVALID")
        try:
            source_dataset_id = str(UUID(lineage["dataset_id"]))
        except (ValueError, TypeError, AttributeError) as exc:
            raise LocalPilotExecutionError("PILOT_FINANCE_LINEAGE_INVALID") from exc
        if source_dataset_id != expected_dataset_id:
            raise LocalPilotExecutionError("PILOT_FINANCE_LINEAGE_MISMATCH")
        output[label] = {
            "dataset_id": source_dataset_id,
            "normalization_evidence_sha256": sha256_text(
                lineage["normalization_evidence_sha256"],
                "PILOT_FINANCE_LINEAGE_INVALID",
            ),
            "source_row_count": integer(
                lineage["source_row_count"],
                "PILOT_FINANCE_LINEAGE_INVALID",
            ),
        }
    return output


__all__ = ["build_finance_lineage"]
