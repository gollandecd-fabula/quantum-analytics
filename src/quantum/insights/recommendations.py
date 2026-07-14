from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re
from typing import Any


RECOMMENDATION_SCHEMA_VERSION = "quantum-recommendation-v1"
RECOMMENDATION_BUNDLE_SCHEMA_VERSION = "quantum-recommendation-bundle-v1"
_POLICY_SCHEMA_VERSION = "quantum-recommendation-policy-v1"
_DECIMAL = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_REQUIRED_THRESHOLDS = frozenset(
    {
        "buyout_rate_warning",
        "buyout_rate_critical",
        "return_rate_warning",
        "return_rate_critical",
        "commission_ratio_warning",
        "logistics_ratio_warning",
        "storage_ratio_warning",
        "stock_to_bought_warning",
        "reconciliation_gap_amount_warning",
    }
)
_REQUIRED_EFFECT_BOUNDS = frozenset(
    {
        "commission_cost_reduction_max",
        "logistics_cost_reduction_max",
        "storage_cost_reduction_max",
        "return_related_cost_reduction_max",
    }
)
_SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


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
    return value.strip()


def _positive_int(value: object, code: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise RecommendationError(code)
    return value


def _decimal(value: object, code: str) -> Decimal:
    if not isinstance(value, str) or _DECIMAL.fullmatch(value) is None:
        raise RecommendationError(code)
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise RecommendationError(code) from exc
    if not result.is_finite():
        raise RecommendationError(code)
    return result


def _ratio(value: object, code: str) -> Decimal:
    result = _decimal(value, code)
    if result < 0:
        raise RecommendationError(code)
    return result


def _bounded_rate(value: object, code: str) -> Decimal:
    result = _ratio(value, code)
    if result > 1:
        raise RecommendationError(code)
    return result


def validate_recommendation_policy(policy: object) -> dict[str, Any]:
    if not isinstance(policy, Mapping):
        raise RecommendationError("RECOMMENDATION_POLICY_INVALID")
    expected = {
        "schema_version",
        "policy_id",
        "version",
        "thresholds",
        "effect_bounds",
    }
    if set(policy) != expected:
        raise RecommendationError("RECOMMENDATION_POLICY_FIELDS_INVALID")
    if policy.get("schema_version") != _POLICY_SCHEMA_VERSION:
        raise RecommendationError("RECOMMENDATION_POLICY_SCHEMA_UNSUPPORTED")
    policy_id = _text(
        policy.get("policy_id"),
        "RECOMMENDATION_POLICY_ID_INVALID",
    )
    version = _positive_int(
        policy.get("version"),
        "RECOMMENDATION_POLICY_VERSION_INVALID",
    )
    thresholds_raw = policy.get("thresholds")
    effects_raw = policy.get("effect_bounds")
    if not isinstance(thresholds_raw, Mapping) or set(thresholds_raw) != _REQUIRED_THRESHOLDS:
        raise RecommendationError("RECOMMENDATION_THRESHOLDS_INVALID")
    if not isinstance(effects_raw, Mapping) or set(effects_raw) != _REQUIRED_EFFECT_BOUNDS:
        raise RecommendationError("RECOMMENDATION_EFFECT_BOUNDS_INVALID")

    thresholds = {
        key: _ratio(
            thresholds_raw[key],
            "RECOMMENDATION_THRESHOLD_INVALID:" + key,
        )
        for key in sorted(_REQUIRED_THRESHOLDS)
    }
    for key in (
        "buyout_rate_warning",
        "buyout_rate_critical",
        "return_rate_warning",
        "return_rate_critical",
        "commission_ratio_warning",
        "logistics_ratio_warning",
        "storage_ratio_warning",
    ):
        if thresholds[key] > 1:
            raise RecommendationError(
                "RECOMMENDATION_RATE_THRESHOLD_OUT_OF_RANGE:" + key
            )
    if thresholds["buyout_rate_critical"] >= thresholds["buyout_rate_warning"]:
        raise RecommendationError("RECOMMENDATION_BUYOUT_THRESHOLDS_INVALID")
    if thresholds["return_rate_warning"] >= thresholds["return_rate_critical"]:
        raise RecommendationError("RECOMMENDATION_RETURN_THRESHOLDS_INVALID")

    effects = {
        key: _bounded_rate(
            effects_raw[key],
            "RECOMMENDATION_EFFECT_BOUND_INVALID:" + key,
        )
        for key in sorted(_REQUIRED_EFFECT_BOUNDS)
    }
    normalized = {
        "schema_version": _POLICY_SCHEMA_VERSION,
        "policy_id": policy_id,
        "version": version,
        "thresholds": {
            key: format(value, "f") for key, value in thresholds.items()
        },
        "effect_bounds": {
            key: format(value, "f") for key, value in effects.items()
        },
    }
    normalized["content_hash"] = sha256(_canonical_json(normalized)).hexdigest()
    return normalized


def _typed_metric(analysis: Mapping[str, Any], metric_id: str) -> Mapping[str, Any]:
    metrics = analysis.get("observed_metrics")
    if not isinstance(metrics, Mapping):
        raise RecommendationError("RECOMMENDATION_METRICS_REQUIRED")
    metric = metrics.get(metric_id)
    if not isinstance(metric, Mapping):
        raise RecommendationError("RECOMMENDATION_METRIC_REQUIRED:" + metric_id)
    state = metric.get("state")
    if state != "VALID":
        raise RecommendationError("RECOMMENDATION_METRIC_NOT_VALID:" + metric_id)
    return metric


def _metric_decimal(analysis: Mapping[str, Any], metric_id: str) -> Decimal:
    metric = _typed_metric(analysis, metric_id)
    raw = metric.get("value")
    if raw is None:
        raise RecommendationError("RECOMMENDATION_METRIC_VALUE_INVALID:" + metric_id)
    return _decimal(str(raw), "RECOMMENDATION_METRIC_VALUE_INVALID:" + metric_id)


def _evidence(
    analysis: Mapping[str, Any],
    metric_ids: Sequence[str],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for metric_id in metric_ids:
        metric = _typed_metric(analysis, metric_id)
        result.append(
            {
                "metric_id": metric_id,
                "value": str(metric.get("value")),
                "unit": metric.get("unit"),
                "currency": metric.get("currency"),
            }
        )
    return result


def _blocked_effect(reason_code: str) -> dict[str, Any]:
    return {
        "state": "BLOCKED",
        "amount_min": None,
        "amount_max": None,
        "currency": None,
        "reason_code": reason_code,
    }


def _current_amount(amount: Decimal) -> dict[str, Any]:
    return {
        "state": "VALID",
        "amount": format(amount.quantize(Decimal("0.01")), "f"),
        "currency": "RUB",
        "reason_code": None,
    }


def _forecast_from_cost(amount: Decimal, max_rate: Decimal, basis: str) -> dict[str, Any]:
    upper = (amount * max_rate).quantize(Decimal("0.01"))
    return {
        "state": "VALID",
        "amount_min": "0.00",
        "amount_max": format(upper, "f"),
        "currency": "RUB",
        "reason_code": None,
        "basis": basis,
        "upper_bound_not_expected_savings": True,
    }


def _recommendation(
    *,
    source_type: str,
    category: str,
    severity: str,
    action_code: str,
    evidence: list[dict[str, Any]],
    current_effect: dict[str, Any],
    forecast_effect: dict[str, Any],
    confidence: str,
    confidence_reasons: Sequence[str],
    limitations: Sequence[str],
    parameters: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    payload = {
        "schema_version": RECOMMENDATION_SCHEMA_VERSION,
        "source_type": source_type,
        "category": category,
        "severity": severity,
        "action_code": action_code,
        "scope": {"source_type": source_type},
        "evidence": evidence,
        "current_effect": current_effect,
        "forecast_effect": forecast_effect,
        "confidence": {
            "state": confidence,
            "reasons": list(confidence_reasons),
        },
        "limitations": list(limitations),
        "parameters": dict(parameters or {}),
    }
    payload["recommendation_id"] = (
        "rec-" + sha256(_canonical_json(payload)).hexdigest()[:24]
    )
    return payload


def _data_completion_recommendation(
    source_type: str,
    reason_codes: Sequence[str],
) -> dict[str, Any]:
    unique = sorted(set(reason_codes))
    return _recommendation(
        source_type=source_type,
        category="DATA_QUALITY",
        severity="HIGH",
        action_code="COMPLETE_REQUIRED_INPUTS",
        evidence=[],
        current_effect={
            "state": "BLOCKED",
            "amount": None,
            "currency": None,
            "reason_code": "FINANCIAL_EFFECT_NOT_COMPUTABLE",
        },
        forecast_effect=_blocked_effect("FINANCIAL_EFFECT_NOT_COMPUTABLE"),
        confidence="HIGH",
        confidence_reasons=["EXPLICIT_SOURCE_BLOCKERS"],
        limitations=unique,
        parameters={"reason_codes": "|".join(unique)},
    )


def _supplier_goods_recommendations(
    analysis: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> list[dict[str, Any]]:
    thresholds = policy["thresholds"]
    ordered = _metric_decimal(analysis, "ordered_units")
    bought = _metric_decimal(analysis, "bought_units")
    stock = _metric_decimal(analysis, "current_stock_units")
    result: list[dict[str, Any]] = []
    source_type = "WB_SUPPLIER_GOODS"

    if ordered > 0:
        buyout_rate = bought / ordered
        critical = Decimal(thresholds["buyout_rate_critical"])
        warning = Decimal(thresholds["buyout_rate_warning"])
        if buyout_rate < warning:
            severity = "CRITICAL" if buyout_rate < critical else "HIGH"
            result.append(
                _recommendation(
                    source_type=source_type,
                    category="SALES",
                    severity=severity,
                    action_code="INVESTIGATE_LOW_BUYOUT",
                    evidence=_evidence(
                        analysis,
                        ("ordered_units", "bought_units"),
                    ),
                    current_effect={
                        "state": "BLOCKED",
                        "amount": None,
                        "currency": None,
                        "reason_code": "ORDER_LEVEL_CAUSE_MODEL_REQUIRED",
                    },
                    forecast_effect=_blocked_effect(
                        "APPROVED_BUYOUT_EFFECT_MODEL_REQUIRED"
                    ),
                    confidence="HIGH",
                    confidence_reasons=["DIRECT_ORDER_AND_BUY_COUNTS"],
                    limitations=["CAUSE_NOT_IDENTIFIED"],
                    parameters={
                        "observed_rate": format(buyout_rate.quantize(Decimal("0.0001")), "f"),
                        "warning_threshold": thresholds["buyout_rate_warning"],
                    },
                )
            )
    if stock == 0 and bought > 0:
        result.append(
            _recommendation(
                source_type=source_type,
                category="INVENTORY",
                severity="CRITICAL",
                action_code="REVIEW_STOCKOUT",
                evidence=_evidence(
                    analysis,
                    ("bought_units", "current_stock_units"),
                ),
                current_effect={
                    "state": "BLOCKED",
                    "amount": None,
                    "currency": None,
                    "reason_code": "SKU_LEVEL_DEMAND_REQUIRED",
                },
                forecast_effect=_blocked_effect("SKU_LEVEL_FORECAST_REQUIRED"),
                confidence="HIGH",
                confidence_reasons=["DIRECT_STOCK_AND_BUY_COUNTS"],
                limitations=["AGGREGATE_SCOPE_ONLY"],
            )
        )
    if bought == 0 and stock > 0:
        result.append(
            _recommendation(
                source_type=source_type,
                category="INVENTORY",
                severity="HIGH",
                action_code="REVIEW_STOCK_WITHOUT_BUYOUT",
                evidence=_evidence(
                    analysis,
                    ("bought_units", "current_stock_units"),
                ),
                current_effect={
                    "state": "BLOCKED",
                    "amount": None,
                    "currency": None,
                    "reason_code": "STOCK_COST_SOURCE_REQUIRED",
                },
                forecast_effect=_blocked_effect("STOCK_COST_SOURCE_REQUIRED"),
                confidence="HIGH",
                confidence_reasons=["DIRECT_STOCK_AND_BUY_COUNTS"],
                limitations=["PERIOD_LENGTH_NOT_MODELED"],
            )
        )
    elif bought > 0:
        stock_to_bought = stock / bought
        threshold = Decimal(thresholds["stock_to_bought_warning"])
        if stock_to_bought >= threshold:
            result.append(
                _recommendation(
                    source_type=source_type,
                    category="INVENTORY",
                    severity="MEDIUM",
                    action_code="REVIEW_HIGH_STOCK_TO_BUYOUT_RATIO",
                    evidence=_evidence(
                        analysis,
                        ("bought_units", "current_stock_units"),
                    ),
                    current_effect={
                        "state": "BLOCKED",
                        "amount": None,
                        "currency": None,
                        "reason_code": "STOCK_COST_SOURCE_REQUIRED",
                    },
                    forecast_effect=_blocked_effect("STOCK_COST_SOURCE_REQUIRED"),
                    confidence="MEDIUM",
                    confidence_reasons=["AGGREGATE_STOCK_TO_BUYOUT_PROXY"],
                    limitations=["NOT_DAYS_OF_SUPPLY", "AGGREGATE_SCOPE_ONLY"],
                    parameters={
                        "observed_ratio": format(
                            stock_to_bought.quantize(Decimal("0.0001")),
                            "f",
                        ),
                        "warning_threshold": thresholds["stock_to_bought_warning"],
                    },
                )
            )
    return result


def _ratio_recommendation(
    *,
    analysis: Mapping[str, Any],
    policy: Mapping[str, Any],
    metric_id: str,
    threshold_id: str,
    effect_bound_id: str,
    action_code: str,
    category: str,
    severity: str,
) -> dict[str, Any] | None:
    sales = _metric_decimal(analysis, "gross_sales_amount")
    amount = _metric_decimal(analysis, metric_id)
    if sales <= 0:
        return None
    ratio = amount / sales
    threshold = Decimal(policy["thresholds"][threshold_id])
    if ratio < threshold:
        return None
    max_rate = Decimal(policy["effect_bounds"][effect_bound_id])
    return _recommendation(
        source_type="WB_DETAILED_FINANCIAL",
        category=category,
        severity=severity,
        action_code=action_code,
        evidence=_evidence(analysis, ("gross_sales_amount", metric_id)),
        current_effect=_current_amount(amount),
        forecast_effect=_forecast_from_cost(
            amount,
            max_rate,
            "POLICY_MAX_REDUCTION_RATE",
        ),
        confidence="MEDIUM",
        confidence_reasons=["DIRECT_EXPENSE_AND_SALES_AMOUNTS"],
        limitations=["UPPER_BOUND_IS_NOT_EXPECTED_SAVINGS"],
        parameters={
            "observed_ratio": format(ratio.quantize(Decimal("0.0001")), "f"),
            "warning_threshold": policy["thresholds"][threshold_id],
            "max_reduction_rate": policy["effect_bounds"][effect_bound_id],
        },
    )


def _detailed_financial_recommendations(
    analysis: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> list[dict[str, Any]]:
    thresholds = policy["thresholds"]
    effects = policy["effect_bounds"]
    result: list[dict[str, Any]] = []
    sold = _metric_decimal(analysis, "gross_sales_units")
    returned = _metric_decimal(analysis, "returned_units")
    sales = _metric_decimal(analysis, "gross_sales_amount")
    reverse_logistics = _metric_decimal(analysis, "reverse_logistics_amount")

    if sold > 0:
        return_rate = returned / sold
        warning = Decimal(thresholds["return_rate_warning"])
        critical = Decimal(thresholds["return_rate_critical"])
        if return_rate >= warning:
            severity = "CRITICAL" if return_rate >= critical else "HIGH"
            return_cost_pool = reverse_logistics
            result.append(
                _recommendation(
                    source_type="WB_DETAILED_FINANCIAL",
                    category="RETURNS",
                    severity=severity,
                    action_code="INVESTIGATE_HIGH_RETURN_RATE",
                    evidence=_evidence(
                        analysis,
                        (
                            "gross_sales_units",
                            "returned_units",
                            "reverse_logistics_amount",
                        ),
                    ),
                    current_effect=_current_amount(return_cost_pool),
                    forecast_effect=_forecast_from_cost(
                        return_cost_pool,
                        Decimal(effects["return_related_cost_reduction_max"]),
                        "POLICY_MAX_RETURN_COST_REDUCTION_RATE",
                    ),
                    confidence="MEDIUM",
                    confidence_reasons=["DIRECT_SALE_RETURN_COUNTS"],
                    limitations=[
                        "RETURN_CAUSE_NOT_IDENTIFIED",
                        "UPPER_BOUND_IS_NOT_EXPECTED_SAVINGS",
                    ],
                    parameters={
                        "observed_rate": format(
                            return_rate.quantize(Decimal("0.0001")),
                            "f",
                        ),
                        "warning_threshold": thresholds["return_rate_warning"],
                        "critical_threshold": thresholds["return_rate_critical"],
                    },
                )
            )

    ratio_rules = (
        (
            "marketplace_commission_amount",
            "commission_ratio_warning",
            "commission_cost_reduction_max",
            "REVIEW_COMMISSION_AND_PRICE_STRUCTURE",
            "COST",
            "HIGH",
        ),
        (
            "forward_logistics_amount",
            "logistics_ratio_warning",
            "logistics_cost_reduction_max",
            "REVIEW_FORWARD_LOGISTICS_COST",
            "LOGISTICS",
            "HIGH",
        ),
        (
            "reverse_logistics_amount",
            "logistics_ratio_warning",
            "logistics_cost_reduction_max",
            "REVIEW_REVERSE_LOGISTICS_COST",
            "LOGISTICS",
            "HIGH",
        ),
        (
            "storage_amount",
            "storage_ratio_warning",
            "storage_cost_reduction_max",
            "REVIEW_STORAGE_COST",
            "INVENTORY",
            "HIGH",
        ),
    )
    for rule in ratio_rules:
        item = _ratio_recommendation(
            analysis=analysis,
            policy=policy,
            metric_id=rule[0],
            threshold_id=rule[1],
            effect_bound_id=rule[2],
            action_code=rule[3],
            category=rule[4],
            severity=rule[5],
        )
        if item is not None:
            result.append(item)

    if sales > 0:
        commission = _metric_decimal(analysis, "marketplace_commission_amount")
        forward = _metric_decimal(analysis, "forward_logistics_amount")
        reverse = _metric_decimal(analysis, "reverse_logistics_amount")
        storage = _metric_decimal(analysis, "storage_amount")
        fines = _metric_decimal(analysis, "fines_withholdings_amount")
        payout = _metric_decimal(analysis, "payout_amount")
        expected = sales - commission - forward - reverse - storage - fines
        gap = abs(expected - payout)
        tolerance = Decimal(thresholds["reconciliation_gap_amount_warning"])
        if gap >= tolerance:
            result.append(
                _recommendation(
                    source_type="WB_DETAILED_FINANCIAL",
                    category="RECONCILIATION",
                    severity="HIGH",
                    action_code="RECONCILE_SETTLEMENT_GAP",
                    evidence=_evidence(
                        analysis,
                        (
                            "gross_sales_amount",
                            "marketplace_commission_amount",
                            "forward_logistics_amount",
                            "reverse_logistics_amount",
                            "storage_amount",
                            "fines_withholdings_amount",
                            "payout_amount",
                        ),
                    ),
                    current_effect=_current_amount(gap),
                    forecast_effect=_blocked_effect(
                        "SETTLEMENT_GAP_CAUSE_CLASSIFICATION_REQUIRED"
                    ),
                    confidence="MEDIUM",
                    confidence_reasons=["DETERMINISTIC_SETTLEMENT_RECONCILIATION"],
                    limitations=[
                        "ADDITIONAL_PAYMENT_AND_OTHER_FLOWS_MAY_EXPLAIN_GAP"
                    ],
                    parameters={
                        "gap_amount": format(gap.quantize(Decimal("0.01")), "f"),
                        "warning_threshold": thresholds[
                            "reconciliation_gap_amount_warning"
                        ],
                    },
                )
            )
    return result


def _blocked_bundle(
    *,
    source_type: str | None,
    reason_code: str,
) -> dict[str, Any]:
    bundle = {
        "schema_version": RECOMMENDATION_BUNDLE_SCHEMA_VERSION,
        "status": "BLOCKED",
        "source_type": source_type,
        "policy_ref": None,
        "recommendation_count": 0,
        "recommendations": [],
        "reason_codes": [reason_code],
        "bundle_hash": "",
    }
    bundle["bundle_hash"] = sha256(
        _canonical_json({key: value for key, value in bundle.items() if key != "bundle_hash"})
    ).hexdigest()
    return bundle


def build_recommendations(
    analysis: Mapping[str, Any],
    policy: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(analysis, Mapping):
        raise RecommendationError("RECOMMENDATION_ANALYSIS_INVALID")
    source_type_raw = analysis.get("source_type")
    source_type = source_type_raw if isinstance(source_type_raw, str) else None
    if analysis.get("status") != "SOURCE_BRIDGE_COMPLETE":
        return _blocked_bundle(
            source_type=source_type,
            reason_code="SOURCE_BRIDGE_NOT_COMPLETE",
        )
    if policy is None:
        return _blocked_bundle(
            source_type=source_type,
            reason_code="RECOMMENDATION_POLICY_REQUIRED",
        )
    normalized_policy = validate_recommendation_policy(policy)

    recommendations: list[dict[str, Any]] = []
    blockers = analysis.get("finance_request_reason_codes", [])
    if blockers is None:
        blockers = []
    if not isinstance(blockers, list) or any(
        not isinstance(item, str) or not item for item in blockers
    ):
        raise RecommendationError("RECOMMENDATION_BLOCKERS_INVALID")
    if blockers:
        recommendations.append(
            _data_completion_recommendation(source_type or "UNKNOWN", blockers)
        )

    if source_type == "WB_SUPPLIER_GOODS":
        recommendations.extend(
            _supplier_goods_recommendations(analysis, normalized_policy)
        )
    elif source_type == "WB_DETAILED_FINANCIAL":
        recommendations.extend(
            _detailed_financial_recommendations(analysis, normalized_policy)
        )
    else:
        return _blocked_bundle(
            source_type=source_type,
            reason_code="RECOMMENDATION_SOURCE_TYPE_UNSUPPORTED",
        )

    recommendations.sort(
        key=lambda item: (
            _SEVERITY_ORDER[item["severity"]],
            item["category"],
            item["action_code"],
            item["recommendation_id"],
        )
    )
    bundle = {
        "schema_version": RECOMMENDATION_BUNDLE_SCHEMA_VERSION,
        "status": "READY",
        "source_type": source_type,
        "policy_ref": {
            "id": normalized_policy["policy_id"],
            "version": normalized_policy["version"],
            "content_hash": normalized_policy["content_hash"],
        },
        "recommendation_count": len(recommendations),
        "recommendations": recommendations,
        "reason_codes": [],
        "bundle_hash": "",
    }
    bundle["bundle_hash"] = sha256(
        _canonical_json({key: value for key, value in bundle.items() if key != "bundle_hash"})
    ).hexdigest()
    return bundle
