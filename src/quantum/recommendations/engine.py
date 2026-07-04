from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re
from typing import Any


RECOMMENDATION_SCHEMA_VERSION = "quantum-recommendation-v1"
RECOMMENDATION_BUNDLE_SCHEMA_VERSION = "quantum-recommendation-bundle-v1"

_SEVERITY_RANK = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
_CATEGORY_RANK = {
    "REQUIRES_DATA": 0,
    "FINANCIAL": 1,
    "ADVERTISING": 2,
    "STORAGE": 3,
    "ASSORTMENT": 4,
    "CONTENT": 5,
}
_TYPED_STATES = {
    "VALID",
    "EMPTY",
    "BLOCKED",
    "UNAVAILABLE",
    "CONFLICT",
    "INVALID",
    "NOT_APPLICABLE",
}
_POLICY_FIELDS = {
    "minimum_profit_per_unit",
    "storage_share_alert",
    "storage_savings_rate_min",
    "storage_savings_rate_max",
    "fines_share_alert",
    "fines_savings_rate_min",
    "fines_savings_rate_max",
    "advertising_share_alert",
    "advertising_savings_rate_min",
    "advertising_savings_rate_max",
}
_RATE_FIELDS = {
    "storage_share_alert",
    "storage_savings_rate_min",
    "storage_savings_rate_max",
    "fines_share_alert",
    "fines_savings_rate_min",
    "fines_savings_rate_max",
    "advertising_share_alert",
    "advertising_savings_rate_min",
    "advertising_savings_rate_max",
}
_DECIMAL = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")

_DATA_ACTIONS = {
    "EVENT_LEVEL_FINANCIAL_SOURCE_REQUIRED_FOR_KERNEL": (
        "Import an admitted event-level Wildberries financial report before "
        "publishing profit recommendations."
    ),
    "RETURN_TREATMENT_INPUT_REQUIRED": (
        "Classify returned units as resalable, compensated, or unresolved for "
        "the selected period."
    ),
    "RETURN_COMPENSATION_CLASSIFICATION_REQUIRED": (
        "Classify return-compensation payments and bind them to the verified "
        "return evidence."
    ),
    "DISCOUNTS_SOURCE_OR_EXPLICIT_ZERO_REQUIRED": (
        "Import the discounts source or explicitly attest a verified zero for "
        "the selected scope and period."
    ),
    "SUBSIDIES_SOURCE_OR_EXPLICIT_ZERO_REQUIRED": (
        "Import the subsidies source or explicitly attest a verified zero for "
        "the selected scope and period."
    ),
    "ADVERTISING_SOURCE_OR_EXPLICIT_ZERO_REQUIRED": (
        "Import advertising expenses or explicitly attest a verified zero for "
        "the selected scope and period."
    ),
    "CALCULATION_PROFILE_REQUIRED": (
        "Create an explicit calculation profile with scoped product cost, tax "
        "rate, tax base, other expenses, and rounding policy."
    ),
    "LOGISTICS_DIRECTION_UNCLASSIFIED": (
        "Classify the direction of every unresolved logistics operation before "
        "running the financial kernel."
    ),
    "PAID_ACCEPTANCE_OUTSIDE_KERNEL_EXPENSE_BOUNDARY": (
        "Approve and map paid-acceptance expenses into the calculation profile."
    ),
    "REBILL_LOGISTICS_OUTSIDE_APPROVED_MAPPING": (
        "Review rebilled logistics and approve its expense-boundary mapping."
    ),
    "ADDITIONAL_PAYMENT_CLASSIFICATION_REQUIRED": (
        "Classify every additional Wildberries payment before calculation."
    ),
    "RECONCILIATION_CONFLICT": (
        "Resolve the control-total differences before acting on financial "
        "recommendations."
    ),
    "CALCULATION_RESULT_REQUIRED": (
        "Complete the governed financial calculation before requesting profit "
        "or expense recommendations."
    ),
    "SOURCE_BRIDGE_NOT_AVAILABLE": (
        "Complete reviewed source admission and source mapping before requesting "
        "recommendations."
    ),
}


class RecommendationError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise RecommendationError("RECOMMENDATION_JSON_INVALID") from exc


def _text(value: object, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RecommendationError(code)
    return " ".join(value.split())


def _scope(value: Mapping[str, Any] | None) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise RecommendationError("RECOMMENDATION_SCOPE_INVALID")
    result: dict[str, str] = {}
    for key, item in value.items():
        normalized_key = _text(key, "RECOMMENDATION_SCOPE_INVALID")
        normalized_value = _text(item, "RECOMMENDATION_SCOPE_INVALID")
        result[normalized_key] = normalized_value
    return dict(sorted(result.items()))


def _decimal(value: object, code: str) -> Decimal:
    if not isinstance(value, str) or _DECIMAL.fullmatch(value) is None:
        raise RecommendationError(code)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise RecommendationError(code) from exc
    if not parsed.is_finite():
        raise RecommendationError(code)
    return parsed


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def _ratio(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000001")), "f")


def _policy(value: Mapping[str, Any] | None) -> dict[str, Decimal]:
    if value is None:
        return {}
    if not isinstance(value, Mapping) or set(value) - _POLICY_FIELDS:
        raise RecommendationError("RECOMMENDATION_POLICY_INVALID")
    result: dict[str, Decimal] = {}
    for field, raw in value.items():
        parsed = _decimal(raw, "RECOMMENDATION_POLICY_VALUE_INVALID:" + field)
        if parsed < 0:
            raise RecommendationError("RECOMMENDATION_POLICY_VALUE_INVALID:" + field)
        if field in _RATE_FIELDS and parsed > 1:
            raise RecommendationError("RECOMMENDATION_POLICY_RATE_INVALID:" + field)
        result[field] = parsed
    for prefix in ("storage", "fines", "advertising"):
        threshold = result.get(prefix + "_share_alert")
        minimum = result.get(prefix + "_savings_rate_min")
        maximum = result.get(prefix + "_savings_rate_max")
        present = sum(item is not None for item in (threshold, minimum, maximum))
        if present not in {0, 3}:
            raise RecommendationError(
                "RECOMMENDATION_POLICY_SAVINGS_RANGE_INCOMPLETE:" + prefix
            )
        if minimum is not None and maximum is not None and minimum > maximum:
            raise RecommendationError(
                "RECOMMENDATION_POLICY_SAVINGS_RANGE_INVALID:" + prefix
            )
    return result


def _typed_metric(
    results: Mapping[str, Any],
    metric_id: str,
) -> tuple[Decimal | None, str | None]:
    raw = results.get(metric_id)
    if raw is None:
        return None, "METRIC_NOT_AVAILABLE:" + metric_id
    if not isinstance(raw, Mapping):
        raise RecommendationError("RECOMMENDATION_METRIC_INVALID:" + metric_id)
    state = raw.get("state")
    if state not in _TYPED_STATES:
        raise RecommendationError("RECOMMENDATION_METRIC_STATE_INVALID:" + metric_id)
    if state != "VALID":
        reason = raw.get("reason_code")
        if not isinstance(reason, str) or not reason:
            reason = "METRIC_NOT_VALID:" + metric_id
        return None, reason
    return _decimal(
        raw.get("value"),
        "RECOMMENDATION_METRIC_VALUE_INVALID:" + metric_id,
    ), None


def _effect_valid(value: Decimal, basis: str) -> dict[str, Any]:
    return {
        "state": "VALID",
        "value": _money(value),
        "currency": "RUB",
        "basis": basis,
        "reason_code": None,
    }


def _effect_blocked(reason_code: str) -> dict[str, Any]:
    return {
        "state": "BLOCKED",
        "value": None,
        "currency": "RUB",
        "basis": None,
        "reason_code": reason_code,
    }


def _evidence_refs(source_bridge: Mapping[str, Any] | None) -> list[str]:
    if source_bridge is None:
        return []
    if not isinstance(source_bridge, Mapping):
        raise RecommendationError("RECOMMENDATION_SOURCE_BRIDGE_INVALID")
    values: set[str] = set()
    for field, prefix in (
        ("source_id", ""),
        ("source_sha256", "source-sha256:"),
        ("canonical_ledger_sha256", "ledger-sha256:"),
        ("canonical_rows_sha256", "rows-sha256:"),
    ):
        value = source_bridge.get(field)
        if isinstance(value, str) and value:
            values.add(prefix + value)
    metrics = source_bridge.get("observed_metrics")
    if isinstance(metrics, Mapping):
        for metric in metrics.values():
            if not isinstance(metric, Mapping):
                continue
            source_ids = metric.get("source_ids")
            if isinstance(source_ids, Sequence) and not isinstance(
                source_ids, (str, bytes)
            ):
                for item in source_ids:
                    if isinstance(item, str) and item:
                        values.add(item)
    return sorted(values)


def _confidence(
    *,
    reconciliation_state: str,
    evidence_refs: Sequence[str],
) -> tuple[str, list[str]]:
    limitations: list[str] = []
    if reconciliation_state == "RECONCILED" and evidence_refs:
        return "HIGH", limitations
    if reconciliation_state in {"PENDING", "NOT_REQUESTED"} and evidence_refs:
        limitations.append("CONTROL_TOTAL_RECONCILIATION_NOT_COMPLETE")
        return "MEDIUM", limitations
    if not evidence_refs:
        limitations.append("EVIDENCE_REFERENCE_INCOMPLETE")
    if reconciliation_state != "RECONCILED":
        limitations.append("CONTROL_TOTAL_RECONCILIATION_NOT_COMPLETE")
    return "LOW", sorted(set(limitations))


def _recommendation(
    *,
    category: str,
    severity: str,
    scope: Mapping[str, str],
    action: str,
    reason: str,
    current_effect: Mapping[str, Any],
    forecast_effect_min: Mapping[str, Any],
    forecast_effect_max: Mapping[str, Any],
    confidence: str,
    evidence_refs: Sequence[str],
    limitations: Sequence[str],
) -> dict[str, Any]:
    if category not in _CATEGORY_RANK or severity not in _SEVERITY_RANK:
        raise RecommendationError("RECOMMENDATION_CLASSIFICATION_INVALID")
    payload = {
        "schema_version": RECOMMENDATION_SCHEMA_VERSION,
        "category": category,
        "severity": severity,
        "scope": dict(scope),
        "action": _text(action, "RECOMMENDATION_ACTION_INVALID"),
        "reason": _text(reason, "RECOMMENDATION_REASON_INVALID"),
        "current_effect": dict(current_effect),
        "forecast_effect_min": dict(forecast_effect_min),
        "forecast_effect_max": dict(forecast_effect_max),
        "confidence": confidence,
        "evidence_refs": sorted(set(evidence_refs)),
        "limitations": sorted(set(limitations)),
    }
    identifier = sha256(_canonical_json(payload)).hexdigest()[:24]
    return {"recommendation_id": "rec-" + identifier, **payload}


def _data_recommendation(
    *,
    reason_code: str,
    scope: Mapping[str, str],
    evidence_refs: Sequence[str],
) -> dict[str, Any]:
    action = _DATA_ACTIONS.get(
        reason_code,
        "Provide or classify the governed input identified by " + reason_code + ".",
    )
    effect = _effect_blocked(reason_code)
    return _recommendation(
        category="REQUIRES_DATA",
        severity="CRITICAL",
        scope=scope,
        action=action,
        reason=(
            "A required governed input is missing, blocked, or conflicting: "
            + reason_code
            + "."
        ),
        current_effect=effect,
        forecast_effect_min=effect,
        forecast_effect_max=effect,
        confidence="HIGH" if evidence_refs else "MEDIUM",
        evidence_refs=evidence_refs,
        limitations=["FINANCIAL_EFFECT_NOT_ESTIMATED"],
    )


def _source_blockers(source_bridge: Mapping[str, Any] | None) -> list[str]:
    if source_bridge is None:
        return ["SOURCE_BRIDGE_NOT_AVAILABLE"]
    raw = source_bridge.get("finance_request_reason_codes")
    if raw is None:
        single = source_bridge.get("finance_request_reason_code")
        raw = [] if single is None else [single]
    if not isinstance(raw, list) or any(
        not isinstance(item, str) or not item for item in raw
    ):
        raise RecommendationError("RECOMMENDATION_SOURCE_BLOCKERS_INVALID")
    return sorted(set(raw))


def _expense_rule(
    *,
    recommendations: list[dict[str, Any]],
    results: Mapping[str, Any],
    policy: Mapping[str, Decimal],
    scope: Mapping[str, str],
    evidence_refs: Sequence[str],
    reconciliation_state: str,
    prefix: str,
    metric_id: str,
    category: str,
    label: str,
) -> None:
    threshold = policy.get(prefix + "_share_alert")
    minimum_rate = policy.get(prefix + "_savings_rate_min")
    maximum_rate = policy.get(prefix + "_savings_rate_max")
    if threshold is None or minimum_rate is None or maximum_rate is None:
        return
    gross_sales, gross_reason = _typed_metric(results, "gross_sales_amount")
    expense, expense_reason = _typed_metric(results, metric_id)
    if gross_reason is not None or expense_reason is not None:
        return
    assert gross_sales is not None and expense is not None
    if gross_sales <= 0:
        return
    share = expense / gross_sales
    if share <= threshold:
        return
    confidence, confidence_limitations = _confidence(
        reconciliation_state=reconciliation_state,
        evidence_refs=evidence_refs,
    )
    recommendations.append(
        _recommendation(
            category=category,
            severity="HIGH",
            scope=scope,
            action=(
                f"Review {label} and validate a reduction scenario before the "
                "next replenishment or advertising decision."
            ),
            reason=(
                f"{label.capitalize()} equals {_money(expense)} RUB and "
                f"{_ratio(share)} of verified gross sales, above the explicit "
                f"policy threshold {_ratio(threshold)}."
            ),
            current_effect=_effect_valid(expense, "CURRENT_EXPENSE_AMOUNT"),
            forecast_effect_min=_effect_valid(
                expense * minimum_rate,
                "POLICY_SAVINGS_ESTIMATE",
            ),
            forecast_effect_max=_effect_valid(
                expense * maximum_rate,
                "POLICY_SAVINGS_ESTIMATE",
            ),
            confidence=confidence,
            evidence_refs=evidence_refs,
            limitations=confidence_limitations,
        )
    )


def _bundle(
    *,
    recommendations: Sequence[Mapping[str, Any]],
    blocked_reason_codes: Sequence[str],
    evidence_refs: Sequence[str],
) -> dict[str, Any]:
    unique = {
        str(item["recommendation_id"]): dict(item)
        for item in recommendations
    }
    ordered = sorted(
        unique.values(),
        key=lambda item: (
            _SEVERITY_RANK[item["severity"]],
            _CATEGORY_RANK[item["category"]],
            item["recommendation_id"],
        ),
    )
    if ordered:
        status = "RECOMMENDATIONS_AVAILABLE"
    elif blocked_reason_codes:
        status = "BLOCKED"
    else:
        status = "NO_ACTIONS"
    bundle = {
        "schema_version": RECOMMENDATION_BUNDLE_SCHEMA_VERSION,
        "status": status,
        "priority_order": ["PROFIT", "SUSTAINABLE_GROWTH", "TURNOVER"],
        "recommendation_count": len(ordered),
        "recommendations": ordered,
        "blocked_reason_codes": sorted(set(blocked_reason_codes)),
        "source_evidence_refs": sorted(set(evidence_refs)),
        "bundle_hash": "",
    }
    bundle["bundle_hash"] = sha256(
        _canonical_json({key: value for key, value in bundle.items() if key != "bundle_hash"})
    ).hexdigest()
    return bundle


def build_blocked_recommendation_bundle(
    *,
    reason_code: str,
    scope: Mapping[str, Any] | None = None,
    evidence_refs: Sequence[str] = (),
) -> dict[str, Any]:
    normalized_scope = _scope(scope)
    recommendation = _data_recommendation(
        reason_code=_text(reason_code, "RECOMMENDATION_REASON_CODE_INVALID"),
        scope=normalized_scope,
        evidence_refs=evidence_refs,
    )
    return _bundle(
        recommendations=[recommendation],
        blocked_reason_codes=[reason_code],
        evidence_refs=evidence_refs,
    )


def build_recommendation_bundle(
    *,
    source_bridge: Mapping[str, Any] | None,
    calculation: Mapping[str, Any] | None,
    reconciliation: Mapping[str, Any] | None,
    policy: Mapping[str, Any] | None = None,
    scope: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build deterministic recommendations without inventing missing inputs."""
    normalized_scope = _scope(scope)
    normalized_policy = _policy(policy)
    evidence_refs = _evidence_refs(source_bridge)
    blockers = _source_blockers(source_bridge)
    reconciliation_state = "PENDING"
    if reconciliation is not None:
        if not isinstance(reconciliation, Mapping):
            raise RecommendationError("RECOMMENDATION_RECONCILIATION_INVALID")
        raw_state = reconciliation.get("state")
        if raw_state not in {"RECONCILED", "PENDING", "NOT_REQUESTED", "CONFLICT"}:
            raise RecommendationError("RECOMMENDATION_RECONCILIATION_STATE_INVALID")
        reconciliation_state = str(raw_state)
    if reconciliation_state == "CONFLICT":
        blockers.append("RECONCILIATION_CONFLICT")

    recommendations: list[dict[str, Any]] = [
        _data_recommendation(
            reason_code=reason_code,
            scope=normalized_scope,
            evidence_refs=evidence_refs,
        )
        for reason_code in sorted(set(blockers))
    ]

    if calculation is None:
        if not blockers:
            blockers.append("CALCULATION_RESULT_REQUIRED")
            recommendations.append(
                _data_recommendation(
                    reason_code="CALCULATION_RESULT_REQUIRED",
                    scope=normalized_scope,
                    evidence_refs=evidence_refs,
                )
            )
        return _bundle(
            recommendations=recommendations,
            blocked_reason_codes=blockers,
            evidence_refs=evidence_refs,
        )
    if not isinstance(calculation, Mapping):
        raise RecommendationError("RECOMMENDATION_CALCULATION_INVALID")
    results = calculation.get("results")
    if not isinstance(results, Mapping):
        raise RecommendationError("RECOMMENDATION_RESULTS_INVALID")

    if reconciliation_state == "CONFLICT":
        return _bundle(
            recommendations=recommendations,
            blocked_reason_codes=blockers,
            evidence_refs=evidence_refs,
        )

    net_profit, net_profit_reason = _typed_metric(results, "net_profit_amount")
    net_units, net_units_reason = _typed_metric(results, "net_sold_units")
    profit_per_unit, profit_per_unit_reason = _typed_metric(
        results,
        "profit_per_sold_unit",
    )
    for reason in (net_profit_reason, net_units_reason, profit_per_unit_reason):
        if reason is not None:
            blockers.append(reason)
            recommendations.append(
                _data_recommendation(
                    reason_code=reason,
                    scope=normalized_scope,
                    evidence_refs=evidence_refs,
                )
            )

    if net_units is not None and net_units != net_units.to_integral_value():
        raise RecommendationError("RECOMMENDATION_NET_SOLD_UNITS_INVALID")
    if (
        net_profit is not None
        and net_units is not None
        and profit_per_unit is not None
        and net_units > 0
    ):
        confidence, confidence_limitations = _confidence(
            reconciliation_state=reconciliation_state,
            evidence_refs=evidence_refs,
        )
        if net_profit < 0:
            loss = abs(net_profit)
            required_per_unit = loss / net_units
            recommendations.append(
                _recommendation(
                    category="FINANCIAL",
                    severity="CRITICAL",
                    scope=normalized_scope,
                    action=(
                        "Do not scale the current configuration. Validate a "
                        f"scenario that improves contribution by at least "
                        f"{_money(required_per_unit)} RUB per sold unit or "
                        f"{_money(loss)} RUB for the same volume."
                    ),
                    reason=(
                        f"Verified net profit is {_money(net_profit)} RUB for "
                        f"{int(net_units)} net sold units."
                    ),
                    current_effect=_effect_valid(
                        net_profit,
                        "CURRENT_NET_PROFIT",
                    ),
                    forecast_effect_min=_effect_valid(
                        loss,
                        "BREAK_EVEN_UPLIFT_REQUIRED",
                    ),
                    forecast_effect_max=_effect_valid(
                        loss,
                        "BREAK_EVEN_UPLIFT_REQUIRED",
                    ),
                    confidence=confidence,
                    evidence_refs=evidence_refs,
                    limitations=confidence_limitations,
                )
            )
        minimum_profit = normalized_policy.get("minimum_profit_per_unit")
        if minimum_profit is not None and profit_per_unit < minimum_profit:
            uplift = (minimum_profit - profit_per_unit) * net_units
            recommendations.append(
                _recommendation(
                    category="FINANCIAL",
                    severity="HIGH",
                    scope=normalized_scope,
                    action=(
                        "Validate price and expense scenarios until profit per "
                        f"sold unit reaches the explicit target "
                        f"{_money(minimum_profit)} RUB."
                    ),
                    reason=(
                        f"Profit per sold unit is {_money(profit_per_unit)} RUB, "
                        f"below the explicit target {_money(minimum_profit)} RUB."
                    ),
                    current_effect=_effect_valid(
                        profit_per_unit,
                        "CURRENT_PROFIT_PER_SOLD_UNIT",
                    ),
                    forecast_effect_min=_effect_valid(
                        uplift,
                        "TARGET_PROFIT_UPLIFT",
                    ),
                    forecast_effect_max=_effect_valid(
                        uplift,
                        "TARGET_PROFIT_UPLIFT",
                    ),
                    confidence=confidence,
                    evidence_refs=evidence_refs,
                    limitations=confidence_limitations,
                )
            )

    _expense_rule(
        recommendations=recommendations,
        results=results,
        policy=normalized_policy,
        scope=normalized_scope,
        evidence_refs=evidence_refs,
        reconciliation_state=reconciliation_state,
        prefix="storage",
        metric_id="storage_amount",
        category="STORAGE",
        label="paid storage",
    )
    _expense_rule(
        recommendations=recommendations,
        results=results,
        policy=normalized_policy,
        scope=normalized_scope,
        evidence_refs=evidence_refs,
        reconciliation_state=reconciliation_state,
        prefix="fines",
        metric_id="fines_withholdings_amount",
        category="FINANCIAL",
        label="fines and withholdings",
    )
    _expense_rule(
        recommendations=recommendations,
        results=results,
        policy=normalized_policy,
        scope=normalized_scope,
        evidence_refs=evidence_refs,
        reconciliation_state=reconciliation_state,
        prefix="advertising",
        metric_id="advertising_amount",
        category="ADVERTISING",
        label="advertising expense",
    )
    return _bundle(
        recommendations=recommendations,
        blocked_reason_codes=blockers,
        evidence_refs=evidence_refs,
    )


def validate_recommendation_bundle(bundle: Mapping[str, Any]) -> None:
    if not isinstance(bundle, Mapping):
        raise RecommendationError("RECOMMENDATION_BUNDLE_INVALID")
    required = {
        "schema_version",
        "status",
        "priority_order",
        "recommendation_count",
        "recommendations",
        "blocked_reason_codes",
        "source_evidence_refs",
        "bundle_hash",
    }
    if set(bundle) != required:
        raise RecommendationError("RECOMMENDATION_BUNDLE_INVALID")
    if bundle.get("schema_version") != RECOMMENDATION_BUNDLE_SCHEMA_VERSION:
        raise RecommendationError("RECOMMENDATION_BUNDLE_SCHEMA_INVALID")
    recommendations = bundle.get("recommendations")
    if not isinstance(recommendations, list):
        raise RecommendationError("RECOMMENDATION_BUNDLE_INVALID")
    if bundle.get("recommendation_count") != len(recommendations):
        raise RecommendationError("RECOMMENDATION_BUNDLE_COUNT_INVALID")
    expected_hash = sha256(
        _canonical_json(
            {key: value for key, value in bundle.items() if key != "bundle_hash"}
        )
    ).hexdigest()
    if bundle.get("bundle_hash") != expected_hash:
        raise RecommendationError("RECOMMENDATION_BUNDLE_HASH_MISMATCH")
