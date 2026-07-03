from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from ._atomic_io import atomic_json
from ._manifest_common import datetime_value
from ._path_safety import reject_symlinks
from ._scope import LocalPilotExecutionError
from ._workspace_open import open_workspace


def _inventory(root: Path) -> tuple[int, int, str]:
    records: list[str] = []
    file_count = 0
    byte_count = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        payload = path.read_bytes()
        file_count += 1
        byte_count += len(payload)
        records.append(
            f"{path.relative_to(root).as_posix()}:{len(payload)}:"
            f"{hashlib.sha256(payload).hexdigest()}"
        )
    digest = hashlib.sha256("\n".join(records).encode("utf-8")).hexdigest()
    return file_count, byte_count, digest


def purge_workspace(
    *,
    workspace_base: Path,
    tenant_id: str,
    run_id: str,
    purged_at: datetime | str,
) -> dict[str, Any]:
    at = (
        purged_at
        if isinstance(purged_at, datetime)
        else datetime_value(purged_at, "PILOT_PURGE_TIMESTAMP_INVALID")
    )
    if at.tzinfo is None or at.utcoffset() is None:
        raise LocalPilotExecutionError("PILOT_PURGE_TIMESTAMP_INVALID")
    layout = open_workspace(
        base=workspace_base,
        tenant_id=tenant_id,
        run_id=run_id,
    )
    reject_symlinks(layout.root)
    try:
        marker = json.loads(layout.marker.read_text(encoding="utf-8"))
        file_count, byte_count, inventory_hash = _inventory(layout.root)
        dataset_id = marker["dataset_id"]
    except (OSError, KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LocalPilotExecutionError("PILOT_PURGE_INVENTORY_FAILED") from exc
    shutil.rmtree(layout.root)
    if layout.root.exists():
        raise LocalPilotExecutionError("PILOT_PURGE_FAILED")
    receipt = {
        "schema_version": "quantum-local-pilot-deletion-v1",
        "run_id_sha256": hashlib.sha256(run_id.encode("utf-8")).hexdigest(),
        "tenant_id_sha256": hashlib.sha256(tenant_id.encode("utf-8")).hexdigest(),
        "dataset_id": dataset_id,
        "deleted_file_count": file_count,
        "deleted_byte_count": byte_count,
        "inventory_sha256": inventory_hash,
        "purged_at": at.isoformat(),
        "source_file_outside_workspace_deleted": False,
        "release_state": "RELEASE_BLOCKED",
    }
    receipt_id = hashlib.sha256(
        f"{tenant_id}\x1f{run_id}\x1f{at.isoformat()}".encode("utf-8")
    ).hexdigest()
    receipt_path = workspace_base.resolve() / "deletion-receipts" / f"{receipt_id}.json"
    if receipt_path.exists():
        raise LocalPilotExecutionError("PILOT_PURGE_RECEIPT_EXISTS")
    atomic_json(receipt_path, receipt)
    return {**receipt, "receipt_path": str(receipt_path)}


__all__ = ["purge_workspace"]
