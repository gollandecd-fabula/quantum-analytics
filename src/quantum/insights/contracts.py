from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256
import json
from typing import Any


_ACTION_TEXT = {
    "COMPLETE_REQUIRED_INPUTS": "Complete the listed governed inputs before publishing financial conclusions.",
    "INVESTIGATE_LOW_BUYOUT": "Review products, sizes, warehouses, and customer expectations behind the low buyout rate before increasing traffic.",
    "REVIEW_STOCKOUT": "Review replenishment for products with verified buyout and zero stock.",
    "REVIEW_STOCK_WITHOUT_BUYOUT": "Stop automatic replenishment for the affected scope and review why stock has no verified buyout.",
    "REVIEW_HIGH_STOCK_TO_BUYOUT_RATIO": "Review replenishment quantities and redistribute excess stock only after SKU-level demand validation.",
    "INVESTIGATE_HIGH_RETURN_RATE": "Identify return causes by product and size, then validate corrective actions in a financial scenario.",
    "REVIEW_COMMISSION_AND_PRICE_STRUCTURE": "Review commission and price structure and validate a scenario that preserves or increases profit per sold unit.",
    "REVIEW_FORWARD_LOGISTICS_COST": "Review forward-logistics drivers and validate warehouse or packaging changes before implementation.",
    "REVIEW_REVERSE_LOGISTICS_COST": "Review reverse-logistics drivers together with return causes before changing assortment or advertising.",
    "REVIEW_STORAGE_COST": "Review stock by product and warehouse and validate a storage-reduction scenario before replenishment.",
    "RECONCILE_SETTLEMENT_GAP": "Resolve the settlement gap against source evidence and control totals before acting on dependent recommendations.",
    "RESTORE_BREAK_EVEN": "Do not scale the current configuration. Validate a price and expense scenario that restores at least break-even profit.",
    "RESOLVE_RECONCILIATION_CONFLICT": "Resolve reconciliation differences before publishing profit or expense recommendations.",
}
_REASON_TEXT = {
    "COMPLETE_REQUIRED_INPUTS": "Required source classifications or calculation inputs remain blocked.",
    "INVESTIGATE_LOW_BUYOUT": "The verified buyout rate is below the explicit policy threshold.",
    "REVIEW_STOCKOUT": "Verified buyout exists while current aggregate stock is zero.",
    "REVIEW_STOCK_WITHOUT_BUYOUT": "Current stock is positive while verified buyout is zero.",
    "REVIEW_HIGH_STOCK_TO_BUYOUT_RATIO": "The aggregate stock-to-buyout ratio exceeds the explicit policy threshold.",
    "INVESTIGATE_HIGH_RETURN_RATE": "The verified return rate exceeds the explicit policy threshold.",
    "REVIEW_COMMISSION_AND_PRICE_STRUCTURE": "Marketplace commission exceeds the explicit share-of-sales threshold.",
    "REVIEW_FORWARD_LOGISTICS_COST": "Forward logistics exceeds the explicit share-of-sales threshold.",
    "REVIEW_REVERSE_LOGISTICS_COST": "Reverse logistics exceeds the explicit share-of-sales threshold.",
    "REVIEW_STORAGE_COST": "Paid storage exceeds the explicit share-of-sales threshold.",
    "RECONCILE_SETTLEMENT_GAP": "The deterministic settlement calculation differs from the verified payout.",
    "RESTORE_BREAK_EVEN": "The governed financial calculation reports negative net profit.",
    "RESOLVE_RECONCILIATION_CONFLICT": "Control totals conflict with the governed calculation result.",
}
_PRIORITY = {
    "DATA_QUALITY": "PROFIT",
    "RECONCILIATION": "PROFIT",
    "COST": "PROFIT",
    "LOGISTICS": "PROFIT",
    "RETURNS": "PROFIT",
    "FINANCIAL": "PROFIT",
    "INVENTORY": "SUSTAINABLE_GROWTH",
    "SALES": "SUSTAINABLE_GROWTH",
    "CONTENT": "TURNOVER",
}


class RecommendationContractError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise RecommendationContractError("RECOMMENDATION_CONTRACT_JSON_INVALID") from exc


def source_evidence_refs(analysis: Mapping[str, Any]) -> list[str]:
    refs: set[str] = set()
    for field, prefix in (
        ("source_id", ""),
        ("source_sha256", "source-sha256:"),
        ("canonical_ledger_sha256", "ledger-sha256:"),
        ("canonical_rows_sha256", "rows-sha256:"),
    ):
        value = analysis.get(field)
        if isinstance(value, str) and value:
            refs.add(prefix + value)
    metrics = analysis.get("observed_metrics")
    if isinstance(metrics, Mapping):
        for metric in metrics.values():
            if not isinstance(metric, Mapping):
                continue
            source_ids = metric.get("source_ids")
            if isinstance(source_ids, Sequence) and not isinstance(source_ids, (str, bytes)):
                refs.update(item for item in source_ids if isinstance(item, str) and item)
    return sorted(refs)


def normalized_scope(
    analysis: Mapping[str, Any],
    supplied: Mapping[str, Any] | None,
) -> dict[str, str]:
    result: dict[str, str] = {}
    for field in ("source_type", "source_id"):
        value = analysis.get(field)
        if isinstance(value, str) and value:
            result[field] = value
    if supplied is not None:
        if not isinstance(supplied, Mapping):
            raise RecommendationContractError("RECOMMENDATION_SCOPE_INVALID")
        for key, value in supplied.items():
            if not isinstance(key, str) or not key.strip() or not isinstance(value, str) or not value.strip():
                raise RecommendationContractError("RECOMMENDATION_SCOPE_INVALID")
            result[key.strip()] = value.strip()
    return dict(sorted(result.items()))


def _forecast_alias(effect: Mapping[str, Any], bound: str) -> dict[str, Any]:
    if effect.get("state") == "VALID":
        key = "amount_min" if bound == "min" else "amount_max"
        return {
            "state": "VALID",
            "value": effect.get(key),
            "currency": effect.get("currency"),
            "basis": effect.get("basis"),
            "reason_code": None,
        }
    return {
        "state": "BLOCKED",
        "value": None,
        "currency": effect.get("currency"),
        "basis": effect.get("basis"),
        "reason_code": effect.get("reason_code"),
    }


def enrich_recommendation(
    item: Mapping[str, Any],
    *,
    source_refs: Sequence[str],
    scope: Mapping[str, str],
) -> dict[str, Any]:
    if not isinstance(item, Mapping):
        raise RecommendationContractError("RECOMMENDATION_ITEM_INVALID")
    result = dict(item)
    action_code = str(result.get("action_code", "UNKNOWN"))
    result["action"] = _ACTION_TEXT.get(
        action_code,
        "Review the verified evidence and validate the proposed change in a scenario.",
    )
    reason = _REASON_TEXT.get(
        action_code,
        "The deterministic recommendation rule was triggered by verified metrics.",
    )
    evidence = result.get("evidence")
    rendered: list[str] = []
    refs = set(source_refs)
    if isinstance(evidence, list):
        for metric in evidence:
            if not isinstance(metric, Mapping):
                continue
            metric_id = metric.get("metric_id")
            value = metric.get("value")
            if isinstance(metric_id, str):
                refs.add("metric:" + metric_id)
                if value is not None:
                    rendered.append(f"{metric_id}={value}")
    result["reason"] = reason + (" Evidence: " + ", ".join(rendered) + "." if rendered else "")
    forecast = result.get("forecast_effect")
    if not isinstance(forecast, Mapping):
        raise RecommendationContractError("RECOMMENDATION_FORECAST_INVALID")
    result["forecast_effect_min"] = _forecast_alias(forecast, "min")
    result["forecast_effect_max"] = _forecast_alias(forecast, "max")
    result["evidence_refs"] = sorted(refs)
    merged_scope = dict(scope)
    existing_scope = result.get("scope")
    if isinstance(existing_scope, Mapping):
        merged_scope.update(
            {key: value for key, value in existing_scope.items() if isinstance(key, str) and isinstance(value, str)}
        )
    result["scope"] = dict(sorted(merged_scope.items()))
    confidence = result.get("confidence")
    result["confidence_level"] = (
        confidence.get("state")
        if isinstance(confidence, Mapping) and isinstance(confidence.get("state"), str)
        else "UNKNOWN"
    )
    result["priority_dimension"] = _PRIORITY.get(
        str(result.get("category", "")),
        "SUSTAINABLE_GROWTH",
    )
    payload = {key: value for key, value in result.items() if key != "recommendation_id"}
    result["recommendation_id"] = "rec-" + sha256(canonical_json(payload)).hexdigest()[:24]
    return result
