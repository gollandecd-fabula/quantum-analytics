from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from .local_bundle import (
    _ACTION_LABELS,
    _CATEGORY_LABELS,
    _SEVERITY_LABELS,
    _canonical_json_text,
)
from .xlsx_ooxml import Cell


_FINANCIAL_LABELS = (
    ("gross_sales_amount", "Валовые продажи"),
    ("payout_amount", "Выплата маркетплейса"),
    ("marketplace_commission_amount", "Комиссия маркетплейса"),
    ("forward_logistics_amount", "Прямая логистика"),
    ("reverse_logistics_amount", "Обратная логистика"),
    ("storage_amount", "Хранение"),
    ("advertising_amount", "Реклама"),
    ("product_cost_amount", "Себестоимость товара"),
    ("other_expense_amount", "Прочие расходы"),
    ("tax_amount", "Налог"),
    ("net_profit_amount", "Чистая прибыль"),
)
_EXPENSE_KEYWORDS = (
    "cost",
    "expense",
    "commission",
    "logistic",
    "storage",
    "advert",
    "fine",
    "tax",
)


def _decimal(value: object) -> Decimal | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return result if result.is_finite() else None


def _state_style(state: object) -> str:
    normalized = str(state or "").upper()
    if normalized in {"VALID", "READY", "RECONCILED", "ADMITTED", "COMPLETE", "PILOT_RUN_COMPLETE"}:
        return "status_good"
    if normalized in {"CONFLICT", "ERROR", "REJECTED", "BLOCKED", "INVALID"}:
        return "status_bad"
    if normalized in {"PENDING", "WARNING", "PARTIAL", "CALCULATED_RECONCILIATION_PENDING"}:
        return "status_warn"
    return "status_neutral"


def _confidence_style(value: object) -> str:
    normalized = str(value or "").upper()
    if normalized in {"HIGH", "VALID"}:
        return "status_good"
    if normalized in {"MEDIUM", "PARTIAL"}:
        return "status_warn"
    return "status_neutral"


def _value_style(metric_id: str, metric: Mapping[str, Any]) -> str:
    currency = str(metric.get("currency") or "")
    unit = str(metric.get("unit") or "").upper()
    if currency:
        return "currency_expense" if any(word in metric_id.casefold() for word in _EXPENSE_KEYWORDS) else "currency"
    if unit in {"RATIO", "PERCENT", "RATE"}:
        return "percent"
    if unit in {"ITEM", "COUNT", "UNITS"}:
        return "integer"
    return "decimal"


def _typed_value_cell(metric_id: str, metric: Mapping[str, Any]) -> Cell:
    value = metric.get("value")
    number = _decimal(value)
    if metric.get("state") == "VALID" and number is not None:
        return Cell(number, _value_style(metric_id, metric), "number")
    return Cell("" if value is None else str(value), "body")


def _metric_rows(
    metrics: object,
    *,
    scope: str,
) -> list[list[Cell]]:
    if not isinstance(metrics, Mapping):
        return []
    rows: list[list[Cell]] = []
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
        state = str(metric.get("state") or "")
        rows.append(
            [
                Cell(scope, "technical"),
                Cell(str(metric_id), "label"),
                Cell(state, _state_style(state)),
                _typed_value_cell(str(metric_id), metric),
                Cell(str(metric.get("unit") or ""), "center"),
                Cell(str(metric.get("currency") or ""), "center"),
                Cell(str(metric.get("reason_code") or ""), "body_wrap"),
                Cell(str(metric.get("accounting_view") or ""), "body_wrap"),
                Cell(boundary_text, "body_wrap"),
                Cell(rounding_text, "technical"),
                Cell(source_text, "technical"),
            ]
        )
    return rows


def _observed_metric_rows(bundle: Mapping[str, Any]) -> list[list[Cell]]:
    return _metric_rows(
        bundle["analysis"].get("observed_metrics"),
        scope="SOURCE_AGGREGATE",
    )


def _calculation_metric_rows(bundle: Mapping[str, Any]) -> list[list[Cell]]:
    calculation = bundle.get("calculation")
    return _metric_rows(
        calculation.get("results") if isinstance(calculation, Mapping) else None,
        scope="CALCULATION_AGGREGATE",
    )


def _all_metric_rows(bundle: Mapping[str, Any]) -> list[list[Cell]]:
    return [*_observed_metric_rows(bundle), *_calculation_metric_rows(bundle)]


def _rows_matching(
    bundle: Mapping[str, Any],
    keywords: Sequence[str],
) -> list[list[Cell]]:
    matches = [
        row
        for row in _all_metric_rows(bundle)
        if any(keyword in str(row[1].value).casefold() for keyword in keywords)
    ]
    return matches or [
        [
            Cell("AGGREGATE_DATASET", "technical"),
            Cell("NO_MATCHING_METRICS", "label"),
            Cell("NOT_AVAILABLE", "status_neutral"),
            Cell("", "decimal"),
            Cell("", "center"),
            Cell("", "center"),
            Cell("SOURCE_OR_MAPPING_REQUIRED", "body_wrap"),
            Cell("", "body_wrap"),
            Cell("", "body_wrap"),
            Cell("", "technical"),
            Cell("", "technical"),
        ]
    ]


def _effect(effect: object) -> tuple[str, Decimal | None, str, str]:
    if not isinstance(effect, Mapping):
        return "", None, "", ""
    state = str(effect.get("state") or "")
    currency = str(effect.get("currency") or "")
    reason = str(effect.get("reason_code") or "")
    for key in ("amount", "value"):
        if key in effect:
            return state, _decimal(effect.get(key)), currency, reason
    minimum = _decimal(effect.get("amount_min"))
    maximum = _decimal(effect.get("amount_max"))
    if minimum is not None and maximum is not None and minimum == maximum:
        return state, minimum, currency, reason
    return state, None, currency, reason


def _effect_cell(value: Decimal | None, currency: str, reason: str) -> Cell:
    if value is not None:
        return Cell(value, "currency" if currency else "decimal", "number")
    return Cell(reason, "body_wrap")


def _recommendation_rows(bundle: Mapping[str, Any]) -> list[list[Cell]]:
    items = bundle["recommendations"].get("recommendations", [])
    if not isinstance(items, list):
        return []
    rows: list[list[Cell]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        current_state, current_value, current_currency, current_reason = _effect(
            item.get("current_effect")
        )
        min_state, min_value, min_currency, min_reason = _effect(
            item.get("forecast_effect_min") or item.get("forecast_effect")
        )
        max_state, max_value, max_currency, max_reason = _effect(
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
        severity_style = {
            "CRITICAL": "severity_critical",
            "HIGH": "severity_high",
            "MEDIUM": "severity_medium",
            "LOW": "severity_low",
        }.get(severity.upper(), "status_neutral")
        action = _ACTION_LABELS.get(action_code) or str(item.get("action") or action_code)
        rows.append(
            [
                Cell(_SEVERITY_LABELS.get(severity, severity), severity_style),
                Cell(str(item.get("priority_dimension") or ""), "center_wrap"),
                Cell(_CATEGORY_LABELS.get(category, category), "center_wrap"),
                Cell(action, "body_wrap"),
                Cell(str(item.get("reason") or ""), "body_wrap"),
                _effect_cell(current_value, current_currency, current_reason),
                _effect_cell(min_value, min_currency, min_reason),
                _effect_cell(max_value, max_currency, max_reason),
                Cell(confidence_state, _confidence_style(confidence_state)),
                Cell(
                    " | ".join(str(value) for value in evidence_refs)
                    if isinstance(evidence_refs, list)
                    else "",
                    "body_wrap",
                ),
                Cell(
                    " | ".join(str(value) for value in limitations)
                    if isinstance(limitations, list)
                    else "",
                    "body_wrap",
                ),
                Cell(str(item.get("recommendation_id") or ""), "technical"),
                Cell(action_code, "technical"),
                Cell(current_state, _state_style(current_state)),
                Cell(current_currency, "center"),
                Cell(min_state, _state_style(min_state)),
                Cell(min_currency, "center"),
                Cell(max_state, _state_style(max_state)),
                Cell(max_currency, "center"),
            ]
        )
    return rows


def _metric_entry(bundle: Mapping[str, Any], metric_id: str) -> Mapping[str, Any] | None:
    calculation = bundle.get("calculation")
    if isinstance(calculation, Mapping):
        results = calculation.get("results")
        metric = results.get(metric_id) if isinstance(results, Mapping) else None
        if isinstance(metric, Mapping):
            return metric
    observed = bundle["analysis"].get("observed_metrics")
    metric = observed.get(metric_id) if isinstance(observed, Mapping) else None
    return metric if isinstance(metric, Mapping) else None


def _result_decimal(bundle: Mapping[str, Any], metric_id: str) -> Decimal | None:
    metric = _metric_entry(bundle, metric_id)
    if not isinstance(metric, Mapping) or metric.get("state") != "VALID":
        return None
    return _decimal(metric.get("value"))


def _summary_financial_rows(bundle: Mapping[str, Any]) -> list[tuple[str, str, Decimal, str]]:
    rows: list[tuple[str, str, Decimal, str]] = []
    for metric_id, label in _FINANCIAL_LABELS:
        metric = _metric_entry(bundle, metric_id)
        if not isinstance(metric, Mapping) or metric.get("state") != "VALID":
            continue
        value = _decimal(metric.get("value"))
        if value is None:
            continue
        source = "CALCULATION" if metric_id in {
            "product_cost_amount",
            "other_expense_amount",
            "tax_amount",
            "net_profit_amount",
        } else "SOURCE"
        rows.append((label, metric_id, value, source))
    return rows


def _summary_control_rows(bundle: Mapping[str, Any]) -> list[tuple[str, object, str]]:
    calculation = bundle.get("calculation")
    publication = calculation.get("publication_state") if isinstance(calculation, Mapping) else None
    return [
        ("Статус запуска", bundle.get("run_status"), _state_style(bundle.get("run_status"))),
        ("Сверка", bundle["reconciliation"].get("state"), _state_style(bundle["reconciliation"].get("state"))),
        ("Рекомендации", bundle["recommendations"].get("recommendation_count", 0), "integer"),
        ("Блокирующие метрики", len(bundle["data_quality"].get("blocked_metrics", [])), "integer"),
        ("Статус публикации", publication or "NOT_AVAILABLE", _state_style(publication)),
        ("Marketplace writes", bundle["provenance"].get("runtime", {}).get("marketplace_write_enabled", False), "boolean"),
    ]


def _summary_technical_rows(bundle: Mapping[str, Any]) -> list[tuple[str, str]]:
    recommendations = bundle["recommendations"]
    policy_ref = recommendations.get("policy_ref")
    policy = _canonical_json_text(policy_ref) if isinstance(policy_ref, Mapping) else ""
    return [
        ("Идентификатор пакета", str(bundle["bundle_id"])),
        ("Набор данных", str(bundle["dataset_id"])),
        ("Тип источника", str(bundle.get("source_type") or "")),
        ("SHA-256 источника", str(bundle["source_sha256"])),
        ("Политика рекомендаций", policy),
        ("SHA-256 пакета", str(bundle["bundle_hash"])),
    ]


def _flatten_rows(value: object, prefix: str = "") -> list[list[Cell]]:
    rows: list[list[Cell]] = []
    if isinstance(value, Mapping):
        for key in sorted(value):
            path = f"{prefix}.{key}" if prefix else str(key)
            item = value[key]
            if isinstance(item, Mapping):
                rows.extend(_flatten_rows(item, path))
            elif isinstance(item, list):
                rows.append([Cell(path, "label"), Cell(_canonical_json_text(item), "technical")])
            elif isinstance(item, bool):
                rows.append([Cell(path, "label"), Cell(item, "boolean", "boolean")])
            elif isinstance(item, (int, float, Decimal)) and not isinstance(item, bool):
                rows.append([Cell(path, "label"), Cell(item, "decimal", "number")])
            else:
                rows.append([Cell(path, "label"), Cell("" if item is None else str(item), "technical")])
    else:
        rows.append([Cell(prefix or "value", "label"), Cell("" if value is None else str(value), "technical")])
    return rows


def _journal_rows(bundle: Mapping[str, Any]) -> list[list[Cell]]:
    rows = [
        [Cell(bundle["generated_at"], "technical"), Cell("BUNDLE_BUILT", "label"), Cell(bundle["bundle_hash"], "code")],
        [Cell(bundle["generated_at"], "technical"), Cell("SOURCE_BOUND", "label"), Cell(bundle["source_sha256"], "code")],
        [
            Cell(bundle["generated_at"], "technical"),
            Cell("RECOMMENDATIONS_BOUND", "label"),
            Cell(str(bundle["recommendations"].get("bundle_hash") or ""), "code"),
        ],
    ]
    calculation = bundle.get("calculation")
    if isinstance(calculation, Mapping):
        rows.append(
            [
                Cell(bundle["generated_at"], "technical"),
                Cell("CALCULATION_BOUND", "label"),
                Cell(str(calculation.get("result_hash") or ""), "code"),
            ]
        )
    rows.append(
        [
            Cell(bundle["generated_at"], "technical"),
            Cell("RECONCILIATION_BOUND", "label"),
            Cell(str(bundle["reconciliation"].get("state") or ""), _state_style(bundle["reconciliation"].get("state"))),
        ]
    )
    return rows


def _metric_headers() -> list[Cell]:
    return [
        Cell("Область", "header"),
        Cell("Метрика", "header"),
        Cell("Состояние", "header"),
        Cell("Значение", "header"),
        Cell("Единица", "header"),
        Cell("Валюта", "header"),
        Cell("Причина", "header"),
        Cell("Представление учёта", "header"),
        Cell("Граница расходов", "header"),
        Cell("Округление", "header"),
        Cell("Источник", "header"),
    ]


def _recommendation_headers() -> list[Cell]:
    return [
        Cell("Срочность", "header"),
        Cell("Приоритет цели", "header"),
        Cell("Категория", "header"),
        Cell("Действие", "header"),
        Cell("Причина", "header"),
        Cell("Текущий эффект", "header"),
        Cell("Прогноз min", "header"),
        Cell("Прогноз max", "header"),
        Cell("Уверенность", "header"),
        Cell("Ссылки на доказательства", "header"),
        Cell("Ограничения", "header"),
        Cell("ID", "header"),
        Cell("Код действия", "header"),
        Cell("Текущий статус", "header"),
        Cell("Валюта", "header"),
        Cell("Статус min", "header"),
        Cell("Валюта min", "header"),
        Cell("Статус max", "header"),
        Cell("Валюта max", "header"),
    ]
