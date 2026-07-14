from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any


LOCAL_OUTPUT_BUNDLE_SCHEMA_VERSION = "quantum-local-output-bundle-v1"
LOCAL_OUTPUT_MANIFEST_SCHEMA_VERSION = "quantum-local-output-manifest-v1"
MAX_LOCAL_OUTPUT_JSON_BYTES = 10_000_000
EXPECTED_XLSX_SHEETS = (
    "Управленческое резюме",
    "Рекомендации",
    "Финансы по товарам",
    "Продажи",
    "Реклама",
    "Возвраты",
    "Остатки и хранение",
    "Расходы",
    "Качество данных",
    "Параметры расчёта",
    "Источники данных",
    "Журнал изменений",
)
_FORBIDDEN_KEYS = frozenset(
    {
        "raw_rows",
        "raw_payload",
        "source_rows",
        "workbook_bytes",
        "file_bytes",
    }
)
_HASH = re.compile(r"^[0-9a-f]{64}$")
_XML_INVALID = re.compile(
    "[\x00-\x08\x0B\x0C\x0E-\x1F\uD800-\uDFFF\uFFFE\uFFFF]"
)
_RECONCILIATION_STATES = {
    "RECONCILED",
    "PENDING",
    "NOT_REQUESTED",
    "CONFLICT",
    "NOT_AVAILABLE",
}
_ACTION_LABELS = {
    "COMPLETE_REQUIRED_INPUTS": "Заполнить обязательные данные",
    "INVESTIGATE_LOW_BUYOUT": "Разобрать низкий выкуп",
    "REVIEW_STOCKOUT": "Проверить дефицит остатка",
    "REVIEW_STOCK_WITHOUT_BUYOUT": "Проверить остаток без выкупа",
    "REVIEW_HIGH_STOCK_TO_BUYOUT_RATIO": "Проверить избыточный остаток",
    "INVESTIGATE_HIGH_RETURN_RATE": "Разобрать высокий уровень возвратов",
    "REVIEW_COMMISSION_AND_PRICE_STRUCTURE": "Проверить комиссию и цену",
    "REVIEW_FORWARD_LOGISTICS_COST": "Проверить прямую логистику",
    "REVIEW_REVERSE_LOGISTICS_COST": "Проверить обратную логистику",
    "REVIEW_STORAGE_COST": "Проверить стоимость хранения",
    "RECONCILE_SETTLEMENT_GAP": "Сверить расхождение выплаты",
    "RESTORE_BREAK_EVEN": "Восстановить безубыточность",
    "RESOLVE_RECONCILIATION_CONFLICT": "Устранить конфликт сверки",
}
_SEVERITY_LABELS = {
    "CRITICAL": "Критический",
    "HIGH": "Высокий",
    "MEDIUM": "Средний",
    "LOW": "Низкий",
}
_CATEGORY_LABELS = {
    "DATA_QUALITY": "Качество данных",
    "SALES": "Продажи",
    "INVENTORY": "Остатки",
    "RETURNS": "Возвраты",
    "COST": "Расходы",
    "LOGISTICS": "Логистика",
    "RECONCILIATION": "Сверка",
    "FINANCIAL": "Финансы",
    "ADVERTISING": "Реклама",
    "STORAGE": "Хранение",
}


class OutputBundleError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _canonical_json_text(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise OutputBundleError("OUTPUT_JSON_INVALID") from exc


def _canonical_json_bytes(value: Any) -> bytes:
    payload = _canonical_json_text(value).encode("utf-8")
    if len(payload) > MAX_LOCAL_OUTPUT_JSON_BYTES:
        raise OutputBundleError("OUTPUT_JSON_SIZE_LIMIT_EXCEEDED")
    return payload


def _clone(value: Any) -> Any:
    return json.loads(_canonical_json_text(value))


def _timestamp(value: datetime | str) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise OutputBundleError("OUTPUT_TIMESTAMP_INVALID")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if not isinstance(value, str) or not value:
        raise OutputBundleError("OUTPUT_TIMESTAMP_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OutputBundleError("OUTPUT_TIMESTAMP_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OutputBundleError("OUTPUT_TIMESTAMP_INVALID")
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _text(value: object, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OutputBundleError(code)
    return value.strip()


def _walk_privacy(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise OutputBundleError("OUTPUT_NON_STRING_KEY")
            if key in _FORBIDDEN_KEYS:
                raise OutputBundleError("OUTPUT_RAW_DATA_FORBIDDEN:" + path + "." + key)
            if key == "raw_rows_in_report" and item is not False:
                raise OutputBundleError("OUTPUT_RAW_ROWS_FLAG_INVALID")
            _walk_privacy(item, path + "." + key)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _walk_privacy(item, f"{path}[{index}]")


def _bundle_hash(bundle: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in bundle.items() if key != "bundle_hash"}
    return sha256(_canonical_json_bytes(payload)).hexdigest()


def _unique_strings(values: Sequence[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if isinstance(value, str) and value and value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _mapping_clone(value: object) -> dict[str, Any] | None:
    return _clone(value) if isinstance(value, Mapping) else None


def _list_clone(value: object) -> list[Any]:
    return _clone(value) if isinstance(value, list) else []


def _normalise_recommendations(
    report: Mapping[str, Any],
    source_bridge: dict[str, Any],
) -> dict[str, Any]:
    source_recommendations = source_bridge.pop("recommendations", None)
    top_recommendations = report.get("recommendations")
    if not isinstance(source_recommendations, Mapping):
        if isinstance(top_recommendations, Mapping):
            source_recommendations = top_recommendations
        else:
            raise OutputBundleError("OUTPUT_RECOMMENDATIONS_REQUIRED")
    recommendations = _clone(source_recommendations)
    if isinstance(top_recommendations, Mapping) and _canonical_json_bytes(
        recommendations
    ) != _canonical_json_bytes(top_recommendations):
        raise OutputBundleError("OUTPUT_RECOMMENDATION_BUNDLE_MISMATCH")
    return recommendations


def _normalise_reconciliation(report: Mapping[str, Any]) -> dict[str, Any]:
    raw = report.get("reconciliation")
    if raw is None:
        return {"state": "NOT_AVAILABLE", "differences": []}
    if not isinstance(raw, Mapping):
        raise OutputBundleError("OUTPUT_RECONCILIATION_INVALID")
    result = _clone(raw)
    if result.get("state") not in _RECONCILIATION_STATES:
        raise OutputBundleError("OUTPUT_RECONCILIATION_STATE_INVALID")
    differences = result.get("differences")
    if not isinstance(differences, list):
        raise OutputBundleError("OUTPUT_RECONCILIATION_INVALID")
    return result


def _finance_reason_codes(source_bridge: Mapping[str, Any]) -> list[str]:
    raw = source_bridge.get("finance_request_reason_codes")
    if raw is None:
        raw = [source_bridge.get("finance_request_reason_code")]
    if not isinstance(raw, list):
        return []
    return _unique_strings(raw)


def _build_data_quality(
    report: Mapping[str, Any],
    source_bridge: Mapping[str, Any],
) -> dict[str, Any]:
    inspection = report.get("inspection")
    inspection_diagnostics = (
        inspection.get("diagnostics", [])
        if isinstance(inspection, Mapping)
        else []
    )
    admission_diagnostics = report.get("admission_diagnostics", [])
    blocked_metrics = report.get("blocked_metrics", [])
    reason_codes = _unique_strings(
        [
            *_finance_reason_codes(source_bridge),
            *(
                admission_diagnostics
                if isinstance(admission_diagnostics, list)
                else []
            ),
            *(
                inspection_diagnostics
                if isinstance(inspection_diagnostics, list)
                else []
            ),
        ]
    )
    return {
        "admission_state": report.get("admission_state"),
        "storage_zone_state": report.get("storage_zone_state"),
        "source_bridge_status": source_bridge.get("status"),
        "finance_request_state": source_bridge.get("finance_request_state"),
        "reason_codes": reason_codes,
        "blocked_metrics": _unique_strings(
            blocked_metrics if isinstance(blocked_metrics, list) else []
        ),
        "inspection_diagnostics": _list_clone(inspection_diagnostics),
        "raw_rows_in_report": False,
    }


def _build_parameters(
    report: Mapping[str, Any],
    calculation: Mapping[str, Any] | None,
    recommendations: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "admission_policy_ref": _mapping_clone(report.get("policy")),
        "recommendation_policy_ref": _mapping_clone(
            recommendations.get("policy_ref")
        ),
        "calculation_profile_ref": _mapping_clone(
            calculation.get("profile_ref") if calculation else None
        ),
        "rounding_policy_ref": _mapping_clone(
            calculation.get("rounding_policy_ref") if calculation else None
        ),
        "calculation_mode": calculation.get("mode") if calculation else None,
        "scenario_id": calculation.get("scenario_id") if calculation else None,
        "calculated_at": calculation.get("calculated_at") if calculation else None,
        "publication_state": (
            calculation.get("publication_state") if calculation else None
        ),
    }


def _build_provenance(
    report: Mapping[str, Any],
    source_bridge: Mapping[str, Any],
    calculation: Mapping[str, Any] | None,
    recommendations: Mapping[str, Any],
    source_sha256: str,
) -> dict[str, Any]:
    return {
        "source": {
            "dataset_id": report.get("dataset_id"),
            "source_id": source_bridge.get("source_id"),
            "source_type": source_bridge.get("source_type"),
            "source_sha256": source_sha256,
            "canonical_rows_sha256": source_bridge.get(
                "canonical_rows_sha256"
            ),
            "canonical_ledger_sha256": source_bridge.get(
                "canonical_ledger_sha256"
            ),
            "header_sha256": source_bridge.get("header_sha256"),
        },
        "calculation": {
            "schema_version": calculation.get("schema_version") if calculation else None,
            "calculation_id": calculation.get("calculation_id") if calculation else None,
            "input_hash": calculation.get("input_hash") if calculation else None,
            "result_hash": calculation.get("result_hash") if calculation else None,
        },
        "recommendations": {
            "schema_version": recommendations.get("schema_version"),
            "bundle_hash": recommendations.get("bundle_hash"),
        },
        "runtime": {
            "runner_version": report.get("runner_version"),
            "runtime_profile": report.get("runtime_profile"),
            "marketplace_write_enabled": report.get(
                "marketplace_write_enabled", False
            ),
            "storage_encryption_required": report.get(
                "storage_encryption_required"
            ),
        },
        "inspection": _mapping_clone(report.get("inspection")),
        "schema_discovery": _mapping_clone(report.get("schema_discovery")),
    }


def build_local_output_bundle(
    report: Mapping[str, Any],
    *,
    generated_at: datetime | str,
) -> dict[str, Any]:
    if not isinstance(report, Mapping):
        raise OutputBundleError("OUTPUT_REPORT_INVALID")
    dataset_id = _text(report.get("dataset_id"), "OUTPUT_DATASET_ID_INVALID")
    run_status = _text(report.get("status"), "OUTPUT_RUN_STATUS_INVALID")
    source_bridge_raw = report.get("source_bridge")
    if not isinstance(source_bridge_raw, Mapping):
        raise OutputBundleError("OUTPUT_SOURCE_BRIDGE_REQUIRED")
    source_bridge = _clone(source_bridge_raw)
    recommendations = _normalise_recommendations(report, source_bridge)
    source_type = source_bridge.get("source_type")
    if source_type is not None and not isinstance(source_type, str):
        raise OutputBundleError("OUTPUT_SOURCE_TYPE_INVALID")
    source_sha256 = source_bridge.get("source_sha256") or report.get("file_sha256")
    source_sha256 = _text(source_sha256, "OUTPUT_SOURCE_SHA256_INVALID").lower()
    if _HASH.fullmatch(source_sha256) is None:
        raise OutputBundleError("OUTPUT_SOURCE_SHA256_INVALID")

    calculation = _mapping_clone(report.get("calculation"))
    reconciliation = _normalise_reconciliation(report)
    report_limitations = report.get("limitations", [])
    bridge_limitations = source_bridge.get("limitations", [])
    calculation_limitations = (
        calculation.get("limitations", []) if calculation is not None else []
    )
    if any(
        not isinstance(value, list)
        for value in (
            report_limitations,
            bridge_limitations,
            calculation_limitations,
        )
    ):
        raise OutputBundleError("OUTPUT_LIMITATIONS_INVALID")
    limitations = _unique_strings(
        [
            *report_limitations,
            *bridge_limitations,
            *calculation_limitations,
        ]
    )
    generated = _timestamp(generated_at)
    bundle: dict[str, Any] = {
        "schema_version": LOCAL_OUTPUT_BUNDLE_SCHEMA_VERSION,
        "bundle_id": "local-output:" + dataset_id,
        "generated_at": generated,
        "dataset_id": dataset_id,
        "run_status": run_status,
        "source_type": source_type,
        "source_sha256": source_sha256,
        "analysis": source_bridge,
        "calculation": calculation,
        "reconciliation": reconciliation,
        "recommendations": recommendations,
        "data_quality": _build_data_quality(report, source_bridge),
        "parameters": _build_parameters(report, calculation, recommendations),
        "provenance": _build_provenance(
            report,
            source_bridge,
            calculation,
            recommendations,
            source_sha256,
        ),
        "limitations": limitations,
        "bundle_hash": "",
    }
    _walk_privacy(bundle)
    bundle["bundle_hash"] = _bundle_hash(bundle)
    validate_local_output_bundle(bundle)
    return bundle


def _validate_hash_or_none(value: object, code: str) -> None:
    if value is not None and (
        not isinstance(value, str) or _HASH.fullmatch(value) is None
    ):
        raise OutputBundleError(code)


def validate_local_output_bundle(bundle: object) -> None:
    expected = {
        "schema_version",
        "bundle_id",
        "generated_at",
        "dataset_id",
        "run_status",
        "source_type",
        "source_sha256",
        "analysis",
        "calculation",
        "reconciliation",
        "recommendations",
        "data_quality",
        "parameters",
        "provenance",
        "limitations",
        "bundle_hash",
    }
    if not isinstance(bundle, Mapping) or set(bundle) != expected:
        raise OutputBundleError("OUTPUT_BUNDLE_FIELDS_INVALID")
    if bundle.get("schema_version") != LOCAL_OUTPUT_BUNDLE_SCHEMA_VERSION:
        raise OutputBundleError("OUTPUT_BUNDLE_SCHEMA_UNSUPPORTED")
    _text(bundle.get("bundle_id"), "OUTPUT_BUNDLE_ID_INVALID")
    _text(bundle.get("dataset_id"), "OUTPUT_DATASET_ID_INVALID")
    _text(bundle.get("run_status"), "OUTPUT_RUN_STATUS_INVALID")
    _timestamp(bundle.get("generated_at"))
    source_type = bundle.get("source_type")
    if source_type is not None and (
        not isinstance(source_type, str) or not source_type
    ):
        raise OutputBundleError("OUTPUT_SOURCE_TYPE_INVALID")
    source_sha256 = bundle.get("source_sha256")
    if not isinstance(source_sha256, str) or _HASH.fullmatch(source_sha256) is None:
        raise OutputBundleError("OUTPUT_SOURCE_SHA256_INVALID")
    if not isinstance(bundle.get("analysis"), Mapping):
        raise OutputBundleError("OUTPUT_ANALYSIS_INVALID")
    calculation = bundle.get("calculation")
    if calculation is not None and not isinstance(calculation, Mapping):
        raise OutputBundleError("OUTPUT_CALCULATION_INVALID")
    if isinstance(calculation, Mapping):
        if not isinstance(calculation.get("results"), Mapping):
            raise OutputBundleError("OUTPUT_CALCULATION_RESULTS_INVALID")
        _validate_hash_or_none(
            calculation.get("input_hash"),
            "OUTPUT_CALCULATION_INPUT_HASH_INVALID",
        )
        _validate_hash_or_none(
            calculation.get("result_hash"),
            "OUTPUT_CALCULATION_RESULT_HASH_INVALID",
        )
    reconciliation = bundle.get("reconciliation")
    if not isinstance(reconciliation, Mapping):
        raise OutputBundleError("OUTPUT_RECONCILIATION_INVALID")
    if reconciliation.get("state") not in _RECONCILIATION_STATES:
        raise OutputBundleError("OUTPUT_RECONCILIATION_STATE_INVALID")
    if not isinstance(reconciliation.get("differences"), list):
        raise OutputBundleError("OUTPUT_RECONCILIATION_INVALID")
    recommendations = bundle.get("recommendations")
    if not isinstance(recommendations, Mapping):
        raise OutputBundleError("OUTPUT_RECOMMENDATIONS_INVALID")
    items = recommendations.get("recommendations")
    count = recommendations.get("recommendation_count")
    if not isinstance(items, list) or not isinstance(count, int) or isinstance(count, bool):
        raise OutputBundleError("OUTPUT_RECOMMENDATIONS_INVALID")
    if count != len(items):
        raise OutputBundleError("OUTPUT_RECOMMENDATION_COUNT_MISMATCH")
    for field, code in (
        ("data_quality", "OUTPUT_DATA_QUALITY_INVALID"),
        ("parameters", "OUTPUT_PARAMETERS_INVALID"),
        ("provenance", "OUTPUT_PROVENANCE_INVALID"),
    ):
        if not isinstance(bundle.get(field), Mapping):
            raise OutputBundleError(code)
    data_quality = bundle["data_quality"]
    if data_quality.get("raw_rows_in_report") is not False:
        raise OutputBundleError("OUTPUT_RAW_ROWS_FLAG_INVALID")
    provenance_source = bundle["provenance"].get("source")
    if not isinstance(provenance_source, Mapping):
        raise OutputBundleError("OUTPUT_PROVENANCE_SOURCE_INVALID")
    if provenance_source.get("source_sha256") != source_sha256:
        raise OutputBundleError("OUTPUT_PROVENANCE_SOURCE_HASH_MISMATCH")
    limitations = bundle.get("limitations")
    if not isinstance(limitations, list) or any(
        not isinstance(item, str) or not item for item in limitations
    ):
        raise OutputBundleError("OUTPUT_LIMITATIONS_INVALID")
    _walk_privacy(bundle)
    supplied_hash = bundle.get("bundle_hash")
    if not isinstance(supplied_hash, str) or supplied_hash != _bundle_hash(bundle):
        raise OutputBundleError("OUTPUT_BUNDLE_HASH_MISMATCH")
    _canonical_json_bytes(bundle)


def render_xlsx_report(bundle: Mapping[str, Any]) -> bytes:
    from .xlsx_report import render_xlsx_report as renderer

    return renderer(bundle)


def render_dashboard_html(bundle: Mapping[str, Any]) -> bytes:
    from .dashboard import render_dashboard_html as renderer

    return renderer(bundle)


def write_local_output_bundle(
    report: Mapping[str, Any],
    *,
    output_root: Path,
    generated_at: datetime | str,
) -> dict[str, Any]:
    from .writer import write_local_output_bundle as writer

    return writer(report, output_root=output_root, generated_at=generated_at)
