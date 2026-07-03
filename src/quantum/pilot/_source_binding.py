from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from quantum.ingestion.admission_v2 import DatasetAdmissionRecord

from ._scope import LocalPilotExecutionError, secure_equal


def _canonical_dataset_id(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return str(UUID(value))
    except (ValueError, AttributeError):
        return None


def validate_source_identity(
    source_snapshot: object,
    admitted: DatasetAdmissionRecord,
) -> Mapping[str, Any]:
    if not isinstance(source_snapshot, Mapping):
        raise LocalPilotExecutionError("PILOT_SOURCE_SNAPSHOT_INVALID")
    source_id = _canonical_dataset_id(source_snapshot.get("dataset_id"))
    admitted_id = _canonical_dataset_id(admitted.declaration.dataset_id)
    source_hash = source_snapshot.get("original_file_sha256")
    if (
        source_id is None
        or admitted_id is None
        or not isinstance(source_hash, str)
        or not secure_equal(source_id, admitted_id)
        or not secure_equal(
            source_hash,
            admitted.declaration.original_file_sha256,
        )
    ):
        raise LocalPilotExecutionError(
            "PILOT_SOURCE_SNAPSHOT_IDENTITY_MISMATCH"
        )
    return source_snapshot


__all__ = ["validate_source_identity"]
