from __future__ import annotations

from collections.abc import Mapping
import os
from pathlib import Path
import re
from typing import Any

from quantum.adapters.wildberries import bridge_reviewed_wb_source
from quantum.ingestion import XlsxInspectionLimits
from quantum.insights import (
    RECOMMENDATION_BUNDLE_SCHEMA_VERSION,
    build_recommendations,
)

from .windows_outputs import attach_local_output_bundle


WINDOWS_SOURCE_BRIDGE_SCHEMA_VERSION = "quantum-windows-source-bridge-v1"
_REPORT_NUMBER = re.compile(
    r"(?:№\s*|report[_\s-]*)([0-9]{6,})",
    re.IGNORECASE,
)
_CONTEXT_MAP = (
    ("reporting_period_start", "date_from"),
    ("reporting_period_end", "date_to"),
)


class WindowsSourceBridgeError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _text(value: object, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WindowsSourceBridgeError(code)
    return value.strip()


def build_source_context(
    config: Mapping[str, Any],
    source_path: Path,
) -> dict[str, str] | None:
    if not isinstance(config, Mapping):
        raise WindowsSourceBridgeError("WINDOWS_SOURCE_CONTEXT_CONFIG_INVALID")
    if not isinstance(source_path, Path):
        raise WindowsSourceBridgeError("WINDOWS_SOURCE_CONTEXT_PATH_INVALID")

    context: dict[str, str] = {}
    report_id = config.get("report_id")
    if report_id is not None:
        if isinstance(report_id, bool):
            raise WindowsSourceBridgeError(
                "WINDOWS_SOURCE_CONTEXT_REPORT_ID_INVALID"
            )
        normalized = str(report_id).strip()
        if not normalized.isdigit():
            raise WindowsSourceBridgeError(
                "WINDOWS_SOURCE_CONTEXT_REPORT_ID_INVALID"
            )
        context["report_id"] = normalized
    else:
        match = _REPORT_NUMBER.search(source_path.name)
        if match is not None:
            context["report_id"] = match.group(1)

    for config_field, context_field in _CONTEXT_MAP:
        value = config.get(config_field)
        if value is not None:
            context[context_field] = _text(
                value,
                "WINDOWS_SOURCE_CONTEXT_DATE_INVALID",
            )

    currency = config.get("source_currency")
    if currency is not None:
        normalized_currency = _text(
            currency,
            "WINDOWS_SOURCE_CONTEXT_CURRENCY_INVALID",
        ).upper()
        if not re.fullmatch(r"[A-Z]{3}", normalized_currency):
            raise WindowsSourceBridgeError(
                "WINDOWS_SOURCE_CONTEXT_CURRENCY_INVALID"
            )
        context["currency"] = normalized_currency
    return context or None


def _output_path(config: Mapping[str, Any]) -> Path | None:
    explicit = config.get("local_output_root")
    if explicit is not None:
        root = Path(
            _text(explicit, "WINDOWS_LOCAL_OUTPUT_ROOT_INVALID")
        ).expanduser()
        if not root.is_absolute():
            raise WindowsSourceBridgeError(
                "WINDOWS_LOCAL_OUTPUT_ROOT_MUST_BE_ABSOLUTE"
            )
    else:
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            return None
        root = Path(local_app_data) / "QuantumLocalProduction" / "output"
    return root / "source_bridge_output.json"


def _blocked(
    *,
    status: str,
    reason_code: str,
    detail: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": WINDOWS_SOURCE_BRIDGE_SCHEMA_VERSION,
        "status": status,
        "finance_request": None,
        "finance_request_state": "BLOCKED",
        "finance_request_reason_codes": [reason_code],
        "raw_rows_in_report": False,
    }
    if detail is not None:
        result["detail"] = detail
    return result


def _recommendation_error(exc: Exception) -> dict[str, Any]:
    return {
        "schema_version": RECOMMENDATION_BUNDLE_SCHEMA_VERSION,
        "status": "ERROR",
        "source_type": None,
        "policy_ref": None,
        "recommendation_count": 0,
        "recommendations": [],
        "reason_codes": [
            getattr(exc, "code", "RECOMMENDATION_UNEXPECTED_ERROR")
        ],
        "detail": type(exc).__name__,
        "bundle_hash": None,
    }


def _attach_outputs(
    *,
    report: Mapping[str, Any],
    result: dict[str, Any],
    config: Mapping[str, Any],
) -> None:
    try:
        output_path = _output_path(config)
    except Exception as exc:
        result["output_bundle"] = {
            "status": "OUTPUT_BUNDLE_ERROR",
            "reason_code": getattr(
                exc,
                "code",
                "WINDOWS_LOCAL_OUTPUT_ROOT_INVALID",
            ),
            "detail": type(exc).__name__,
        }
        return
    if output_path is None:
        result["output_bundle"] = {
            "status": "OUTPUT_BUNDLE_SKIPPED",
            "reason_code": "LOCALAPPDATA_NOT_AVAILABLE",
        }
        return
    output_report = dict(report)
    limitations = list(output_report.get("limitations", []))
    for item in (
        "HOME_LOCAL_UNENCRYPTED_STORAGE",
        "PHYSICAL_ACCESS_RISK_ACCEPTED",
    ):
        if item not in limitations:
            limitations.append(item)
    output_report["limitations"] = limitations
    output_report["source_bridge"] = result
    attached = attach_local_output_bundle(
        report=output_report,
        output_path=output_path,
    )
    if attached is not None:
        result["output_bundle"] = attached


def attach_reviewed_source_bridge(
    *,
    report: Mapping[str, Any],
    payload: bytes,
    schema_discovery: Mapping[str, Any] | None,
    limits: XlsxInspectionLimits,
    config: Mapping[str, Any],
    source_path: Path,
) -> dict[str, Any] | None:
    """Attach source analytics after admission without changing admission state."""
    if schema_discovery is None:
        return None
    if report.get("storage_zone_state") != "ADMITTED":
        return _blocked(
            status="SOURCE_BRIDGE_SKIPPED",
            reason_code="SOURCE_NOT_ADMITTED",
        )
    dataset_id = report.get("dataset_id")
    if not isinstance(dataset_id, str) or not dataset_id:
        return _blocked(
            status="SOURCE_BRIDGE_BLOCKED",
            reason_code="ADMITTED_DATASET_ID_REQUIRED",
        )
    try:
        context = build_source_context(config, source_path)
        result = bridge_reviewed_wb_source(
            payload=payload,
            schema_discovery=schema_discovery,
            limits=limits,
            source_id="dataset:" + dataset_id,
            source_context=context,
        )
    except Exception as exc:
        return _blocked(
            status="SOURCE_BRIDGE_ERROR",
            reason_code=getattr(
                exc,
                "code",
                "SOURCE_BRIDGE_UNEXPECTED_ERROR",
            ),
            detail=type(exc).__name__,
        )
    try:
        result["recommendations"] = build_recommendations(
            result,
            config.get("recommendation_policy"),
        )
    except Exception as exc:
        result["recommendations"] = _recommendation_error(exc)
    result["windows_integration_schema_version"] = (
        WINDOWS_SOURCE_BRIDGE_SCHEMA_VERSION
    )
    _attach_outputs(report=report, result=result, config=config)
    return result
