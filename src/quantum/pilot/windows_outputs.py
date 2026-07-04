from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from quantum.outputs import write_local_output_bundle


WINDOWS_OUTPUT_INTEGRATION_SCHEMA_VERSION = "quantum-windows-output-integration-v1"


def attach_local_output_bundle(
    *,
    report: Mapping[str, Any],
    output_path: Path,
    generated_at: datetime | str | None = None,
) -> dict[str, Any] | None:
    if not isinstance(report, Mapping):
        return {
            "status": "OUTPUT_BUNDLE_ERROR",
            "schema_version": WINDOWS_OUTPUT_INTEGRATION_SCHEMA_VERSION,
            "reason_code": "OUTPUT_REPORT_INVALID",
            "detail": "TypeError",
        }
    if not isinstance(report.get("source_bridge"), Mapping):
        return None
    if not isinstance(output_path, Path):
        return {
            "status": "OUTPUT_BUNDLE_ERROR",
            "schema_version": WINDOWS_OUTPUT_INTEGRATION_SCHEMA_VERSION,
            "reason_code": "OUTPUT_PATH_INVALID",
            "detail": "TypeError",
        }
    resolved_output = output_path.resolve()
    output_root = resolved_output.parent / "Quantum_Output"
    try:
        result = write_local_output_bundle(
            report,
            output_root=output_root,
            generated_at=generated_at or datetime.now(UTC),
        )
    except Exception as exc:
        return {
            "status": "OUTPUT_BUNDLE_ERROR",
            "schema_version": WINDOWS_OUTPUT_INTEGRATION_SCHEMA_VERSION,
            "reason_code": getattr(exc, "code", "OUTPUT_BUNDLE_UNEXPECTED_ERROR"),
            "detail": type(exc).__name__,
        }
    result["windows_integration_schema_version"] = (
        WINDOWS_OUTPUT_INTEGRATION_SCHEMA_VERSION
    )
    result["primary_output_path"] = str(resolved_output)
    result["output_root"] = str(output_root)
    return result
