from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .local_bundle import (
    _ACTION_LABELS,
    _CATEGORY_LABELS,
    _SEVERITY_LABELS,
    _canonical_json_text,
)


def _metric_rows(
    metrics: object,
    *,
    scope: str,
) -> list[list[str]]:
    if not isinstance(metrics, Mapping):
        return []
    rows: list[list[str]] = []
    for metric_id in sorted(metrics):
        metric = metrics[metric_id]
        if not isinstance(metric, Mapping):
            continue
        source_ids = metric.get("source_ids")
        source_text = (
            " | ".join(str(item) for item in source_ids)
            if isinstance(source_ids, list)
            else str(metric.get("authority") or "")
        )
        boundary = metric.get("expense_boundary")
        boundary_text = (
            " | ".join(str(item) for item in boundary)
            if isinstance(boundary, list)
            else ""
        )
        rounding = metric.get("rounding")
        rounding_text = (
            _canonical_json_text(rounding) if isinstance(rounding, Mapping) else ""
        )
        rows.append(
            [
                scope,
                str(metric_id),
                str(metric.get("state") or ""),
                "" if metric.get("value") is None else str(metric.get("value")),
                str(metric.get("unit") or ""),
                str(metric.get("currency") or ""),
                str(metric.get("reason_code") or ""),
                str(metric.get("accounting_view") or ""),
                boundary_text,
                rounding_text,
                source_text,
            ]
        )
    return rows


def _observed_metric_rows(bundle: Mapping[str, Any]) -> list[list[str]]:
    return _metric_rows(
        bundle["analysis"].get("observed_metrics"),
        scope="SOURCE_AGGREGATE",
    )


def _calculation_metric_rows(bundle: Mapping[str, Any]) -> list[list[str]]:
    calculation = bundle.get("calculation")
    return _metric_rows(
        calculation.get("results") if isinstance(calculation, Mapping) else None,
        scope="CALCULATION_AGGREGATE",
    )


def _all_metric_rows(bundle: Mapping[str, Any]) -> list[list[str]]:
    return [*_observed_metric_rows(bundle), *_calculation_metric_rows(bundle)]


def _rows_matching(
    bundle: Mapping[str, Any],
    keywords: Sequence[str],
) -> list[list[str]]:
    matches = [
        row
        for row in _all_metric_rows(bundle)
        if any(keyword in row[1].casefold() for keyword in keywords)
    ]
    return matches or [
        [
            "AGGREGATE_DATASET",
            "NO_MATCHING_METRICS",
            "NOT_AVAILABLE",
            "",
            "",
            "",
            "SOURCE_OR_MAPPING_REQUIRED",
            "",
            "",
            "",
            "",
        ]
    ]


def _effect_text(effect: object) -> tuple[str, str, str]:
    if not isinstance(effect, Mapping):
        return "", "", ""
    state = str(effect.get("state") or "")
    if "amount" in effect:
        amount = "" if effect.get("amount") is None else str(effect.get("amount"))
        return state, amount, str(effect.get("currency") or "")
    if "value" in effect:
        amount = "" if effect.get("value") is None else str(effect.get("value"))
        return state, amount, str(effect.get("currency") or "")
    minimum = "" if effect.get("amount_min") is None else str(effect.get("amount_min"))
    maximum = "" if effect.get("amount_max") is None else str(effect.get("amount_max"))
    value = minimum if minimum == maximum else f"{minimum} .. {maximum}".strip(" .")
    return state, value, str(effect.get("currency") or "")


def _recommendation_rows(bundle: Mapping[str, Any]) -> list[list[str]]:
    items = bundle["recommendations"].get("recommendations", [])
    if not isinstance(items, list):
        return []
    rows: list[list[str]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        current_state, current_value, current_currency = _effect_text(
            item.get("current_effect")
        )
        forecast_min_state, forecast_min_value, forecast_min_currency = _effect_text(
            item.get("forecast_effect_min") or item.get("forecast_effect")
        )
        forecast_max_state, forecast_max_value, forecast_max_currency = _effect_text(
            item.get("forecast_effect_max") or item.get("forecast_effect")
        )
        confidence = item.get("confidence")
        confidence_state = (
            str(confidence.get("state") or "")
            if isinstance(confidence, Mapping)
            else str(item.get("confidence_level") or "")
        )
        limitations = item.get("limitations")
        evidence_refs = item.get("evidence_refs")
        action_code = str(item.get("action_code") or "")
        category = str(item.get("category") or "")
        severity = str(item.get("severity") or "")
        rows.append(
            [
                str(item.get("recommendation_id") or ""),
                str(item.get("priority_dimension") or ""),
                _SEVERITY_LABELS.get(severity, severity),
                _CATEGORY_LABELS.get(category, category),
                str(item.get("action") or _ACTION_LABELS.get(action_code, action_code)),
                str(item.get("reason") or ""),
                action_code,
                confidence_state,
                current_state,
                current_value,
                current_currency,
                forecast_min_state,
                forecast_min_value,
                forecast_min_currency,
                forecast_max_state,
                forecast_max_value,
                forecast_max_currency,
                " | ".join(str(value) for value in evidence_refs)
                if isinstance(evidence_refs, list)
                else "",
                " | ".join(str(value) for value in limitations)
                if isinstance(limitations, list)
                else "",
            ]
        )
    return rows


def _result_value(bundle: Mapping[str, Any], metric_id: str) -> str:
    calculation = bundle.get("calculation")
    if not isinstance(calculation, Mapping):
        return ""
    results = calculation.get("results")
    metric = results.get(metric_id) if isinstance(results, Mapping) else None
    if not isinstance(metric, Mapping) or metric.get("state") != "VALID":
        return ""
    value = metric.get("value")
    return "" if value is None else str(value)


def _summary_rows(bundle: Mapping[str, Any]) -> list[list[str]]:
    recommendations = bundle["recommendations"]
    policy_ref = recommendations.get("policy_ref")
    policy = _canonical_json_text(policy_ref) if isinstance(policy_ref, Mapping) else ""
    return [
        ["Идентификатор пакета", str(bundle["bundle_id"])],
        ["Сформирован", str(bundle["generated_at"])],
        ["Набор данных", str(bundle["dataset_id"])],
        ["Статус запуска", str(bundle["run_status"])],
        ["Тип источника", str(bundle.get("source_type") or "")],
        ["SHA-256 источника", str(bundle["source_sha256"])],
        ["Статус сверки", str(bundle["reconciliation"].get("state") or "")],
        ["Чистая прибыль, RUB", _result_value(bundle, "net_profit_amount")],
        ["Прибыль на единицу, RUB", _result_value(bundle, "profit_per_sold_unit")],
        ["Рентабельность затрат", _result_value(bundle, "profitability_of_costs")],
        ["Продано единиц", _result_value(bundle, "net_sold_units")],
        ["Статус рекомендаций", str(recommendations.get("status") or "")],
        ["Количество рекомендаций", str(recommendations.get("recommendation_count", 0))],
        ["Политика рекомендаций", policy],
        ["Количество блокирующих метрик", str(len(bundle["data_quality"].get("blocked_metrics", [])))],
        ["SHA-256 пакета", str(bundle["bundle_hash"])],
    ]


def _flatten_rows(value: object, prefix: str = "") -> list[list[str]]:
    rows: list[list[str]] = []
    if isinstance(value, Mapping):
        for key in sorted(value):
            path = f"{prefix}.{key}" if prefix else str(key)
            item = value[key]
            if isinstance(item, Mapping):
                rows.extend(_flatten_rows(item, path))
            elif isinstance(item, list):
                rows.append([path, _canonical_json_text(item)])
            else:
                rows.append([path, "" if item is None else str(item)])
    else:
        rows.append([prefix or "value", "" if value is None else str(value)])
    return rows


def _journal_rows(bundle: Mapping[str, Any]) -> list[list[str]]:
    rows = [
        [bundle["generated_at"], "BUNDLE_BUILT", bundle["bundle_hash"]],
        [bundle["generated_at"], "SOURCE_BOUND", bundle["source_sha256"]],
        [
            bundle["generated_at"],
            "RECOMMENDATIONS_BOUND",
            str(bundle["recommendations"].get("bundle_hash") or ""),
        ],
    ]
    calculation = bundle.get("calculation")
    if isinstance(calculation, Mapping):
        rows.append(
            [
                bundle["generated_at"],
                "CALCULATION_BOUND",
                str(calculation.get("result_hash") or ""),
            ]
        )
    rows.append(
        [
            bundle["generated_at"],
            "RECONCILIATION_BOUND",
            str(bundle["reconciliation"].get("state") or ""),
        ]
    )
    return rows


def _metric_headers() -> list[str]:
    return [
        "Область",
        "Метрика",
        "Состояние",
        "Значение",
        "Единица",
        "Валюта",
        "Причина",
        "Представление учёта",
        "Граница расходов",
        "Округление",
        "Источник",
    ]
