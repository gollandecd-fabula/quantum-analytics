from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

from .dashboard import render_dashboard_html
from .local_bundle import (
    LOCAL_OUTPUT_MANIFEST_SCHEMA_VERSION,
    OutputBundleError,
    build_local_output_bundle,
    render_xlsx_report,
)


_SAFE_TOKEN = re.compile(r"[^A-Za-z0-9._-]+")


def _json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise OutputBundleError("OUTPUT_JSON_INVALID") from exc


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def _artifact(path: Path, payload: bytes) -> dict[str, Any]:
    return {
        "name": path.name,
        "size_bytes": len(payload),
        "sha256": sha256(payload).hexdigest(),
    }


def write_local_output_bundle(
    report: Mapping[str, Any],
    *,
    output_root: Path,
    generated_at: datetime | str,
) -> dict[str, Any]:
    if not isinstance(output_root, Path):
        raise OutputBundleError("OUTPUT_ROOT_INVALID")
    bundle = build_local_output_bundle(report, generated_at=generated_at)
    token = _SAFE_TOKEN.sub("-", str(bundle["dataset_id"])).strip("-._")
    if not token:
        token = bundle["bundle_hash"][:16]
    target = output_root.resolve() / ("quantum_" + token[:80])
    target.mkdir(parents=True, exist_ok=True)

    payloads = {
        "quantum_result.json": _json_bytes(bundle),
        "recommendations.json": _json_bytes(bundle["recommendations"]),
        "Quantum_Report.xlsx": render_xlsx_report(bundle),
        "dashboard.html": render_dashboard_html(bundle),
    }
    artifacts: list[dict[str, Any]] = []
    for name in sorted(payloads):
        path = target / name
        _atomic_write(path, payloads[name])
        artifacts.append(_artifact(path, payloads[name]))

    manifest: dict[str, Any] = {
        "schema_version": LOCAL_OUTPUT_MANIFEST_SCHEMA_VERSION,
        "bundle_id": bundle["bundle_id"],
        "bundle_hash": bundle["bundle_hash"],
        "generated_at": bundle["generated_at"],
        "manifest_excludes_self": True,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "manifest_hash": "",
    }
    manifest["manifest_hash"] = sha256(
        _json_bytes(
            {key: value for key, value in manifest.items() if key != "manifest_hash"}
        )
    ).hexdigest()
    manifest_payload = _json_bytes(manifest)
    manifest_path = target / "evidence_manifest.json"
    _atomic_write(manifest_path, manifest_payload)
    return {
        "status": "OUTPUT_BUNDLE_COMPLETE",
        "schema_version": LOCAL_OUTPUT_MANIFEST_SCHEMA_VERSION,
        "directory": str(target),
        "bundle_hash": bundle["bundle_hash"],
        "manifest_hash": manifest["manifest_hash"],
        "artifacts": [
            {**entry, "path": str(target / entry["name"])} for entry in artifacts
        ]
        + [
            {
                **_artifact(manifest_path, manifest_payload),
                "path": str(manifest_path),
            }
        ],
    }
