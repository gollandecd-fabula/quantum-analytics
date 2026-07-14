from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
import re
from typing import Any

from .contracts import enrich_recommendation


_DECIMAL = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")


class FinancialRecommendationError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _decimal(value: object, code: str) -> Decimal:
    if not isinstance(value, str) or _DECIMAL.fullmatch(value) is None:
        raise FinancialRecommendationError(code)
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise FinancialRecommendationError(code) from exc
    if not result.is_finite():
        raise FinancialRecommendationError(code)
    return result


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def _typed_result(results: Mapping[str, Any], metric_id: str) -> Decimal | None:
    raw = results.get(metric_id)
    if not isinstance(raw, Mapping) or raw.get("state") != "VALID":
        return None
    return _decimal(
        raw.get("value"),
        "FINANCIAL_RECOMMENDATION_METRIC_INVALID:" + metric_id,
    )


def _blocked_effect(reason_code: str) -> dict[str, Any]:
    return {
        "state": "BLOCKED",
        "amount_min": None,
        "amount_max": None,
        "currency": "RUB",
        "reason_code": reason_code,
    }


def _reconciliation_conflict(
    *,
    source_type: str | None,
    source_refs: Sequence[str],
    scope: Mapping[str, str],
) -> dict[str, Any]:
    item = {
        "schema_version": "quantum-recommendation-v1",
        "source_type": source_type,
        "category": "DATA_QUALITY",
        "severity": "CRITICAL",
        "action_code": "RESOLVE_RECONCILIATION_CONFLICT",
        "scope": dict(scope),
        "evidence": [],
        "current_effect": {
            "state": "BLOCKED",
            "amount": None,
            "currency": "RUB",
            "reason_code": "RECONCILIATION_CONFLICT",
        },
        "forecast_effect": _blocked_effect("RECONCILIATION_CONFLICT"),
        "confidence": {
            "state": "HIGH",
            "reasons": ["EXPLICIT_RECONCILIATION_CONFLICT"],
        },
        "limitations": ["FINANCIAL_RECOMMENDATIONS_SUPPRESSED"],
        "parameters": {},
    }
    return enrich_recommendation(item, source_refs=source_refs, scope=scope)


def _negative_profit(
    *,
    results: Mapping[str, Any],
    reconciliation_state: str,
    source_type: str | None,
    source_refs: Sequence[str],
    scope: Mapping[str, str],
) -> dict[str, Any] | None:
    net_profit = _typed_result(results, "net_profit_amount")
    net_units = _typed_result(results, "net_sold_units")
    profit_per_unit = _typed_result(results, "profit_per_sold_unit")
    if (
        net_profit is None
        or net_units is None
        or profit_per_unit is None
        or net_units <= 0
        or net_profit >= 0
    ):
        return None
    if net_units != net_units.to_integral_value():
        raise FinancialRecommendationError(
            "FINANCIAL_RECOMMENDATION_NET_UNITS_INVALID"
        )
    loss = abs(net_profit)
    required_per_unit = loss / net_units
    limitations: list[str] = []
    if reconciliation_state != "RECONCILED":
        limitations.append("CONTROL_TOTAL_RECONCILIATION_NOT_COMPLETE")
    item = {
        "schema_version": "quantum-recommendation-v1",
        "source_type": source_type,
        "category": "FINANCIAL",
        "severity": "CRITICAL",
        "action_code": "RESTORE_BREAK_EVEN",
        "scope": dict(scope),
        "evidence": [
            {
                "metric_id": "net_profit_amount",
                "value": _money(net_profit),
                "unit": "MONEY",
                "currency": "RUB",
            },
            {
                "metric_id": "net_sold_units",
                "value": str(int(net_units)),
                "unit": "ITEM",
                "currency": None,
            },
            {
                "metric_id": "profit_per_sold_unit",
                "value": _money(profit_per_unit),
                "unit": "MONEY_PER_ITEM",
                "currency": "RUB",
            },
        ],
        "current_effect": {
            "state": "VALID",
            "amount": _money(net_profit),
            "currency": "RUB",
            "reason_code": None,
        },
        "forecast_effect": {
            "state": "VALID",
            "amount_min": _money(loss),
            "amount_max": _money(loss),
            "currency": "RUB",
            "reason_code": None,
            "basis": "BREAK_EVEN_UPLIFT_REQUIRED",
            "upper_bound_not_expected_savings": False,
        },
        "confidence": {
            "state": (
                "HIGH"
                if reconciliation_state == "RECONCILED" and source_refs
                else "MEDIUM"
            ),
            "reasons": [
                "GOVERNED_NET_PROFIT_RESULT",
                "POSITIVE_NET_SOLD_UNIT_DENOMINATOR",
            ],
        },
        "limitations": limitations,
        "parameters": {
            "required_uplift_per_sold_unit": _money(required_per_unit),
        },
    }
    return enrich_recommendation(item, source_refs=source_refs, scope=scope)


def build_financial_recommendations(
    *,
    calculation: Mapping[str, Any] | None,
    reconciliation: Mapping[str, Any] | None,
    source_type: str | None,
    source_refs: Sequence[str],
    scope: Mapping[str, str],
) -> list[dict[str, Any]]:
    if calculation is None:
        return []
    if not isinstance(calculation, Mapping):
        raise FinancialRecommendationError(
            "FINANCIAL_RECOMMENDATION_CALCULATION_INVALID"
        )
    results = calculation.get("results")
    if not isinstance(results, Mapping):
        raise FinancialRecommendationError(
            "FINANCIAL_RECOMMENDATION_RESULTS_INVALID"
        )
    reconciliation_state = "PENDING"
    if reconciliation is not None:
        if not isinstance(reconciliation, Mapping):
            raise FinancialRecommendationError(
                "FINANCIAL_RECOMMENDATION_RECONCILIATION_INVALID"
            )
        state = reconciliation.get("state")
        if state not in {"RECONCILED", "PENDING", "NOT_REQUESTED", "CONFLICT"}:
            raise FinancialRecommendationError(
                "FINANCIAL_RECOMMENDATION_RECONCILIATION_STATE_INVALID"
            )
        reconciliation_state = str(state)
    if reconciliation_state == "CONFLICT":
        return [
            _reconciliation_conflict(
                source_type=source_type,
                source_refs=source_refs,
                scope=scope,
            )
        ]
    negative = _negative_profit(
        results=results,
        reconciliation_state=reconciliation_state,
        source_type=source_type,
        source_refs=source_refs,
        scope=scope,
    )
    return [] if negative is None else [negative]
