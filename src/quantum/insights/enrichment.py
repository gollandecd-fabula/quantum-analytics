from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from typing import Any

from .contracts import (
    canonical_json,
    enrich_recommendation,
    normalized_scope,
    source_evidence_refs,
)
from .financial import build_financial_recommendations


class RecommendationEnrichmentError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def enrich_recommendation_bundle(
    bundle: Mapping[str, Any],
    analysis: Mapping[str, Any],
    *,
    calculation: Mapping[str, Any] | None = None,
    reconciliation: Mapping[str, Any] | None = None,
    scope: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(bundle, Mapping) or not isinstance(analysis, Mapping):
        raise RecommendationEnrichmentError(
            "RECOMMENDATION_ENRICHMENT_INPUT_INVALID"
        )
    result = dict(bundle)
    raw_items = result.get("recommendations")
    if not isinstance(raw_items, list):
        raise RecommendationEnrichmentError(
            "RECOMMENDATION_ENRICHMENT_BUNDLE_INVALID"
        )
    refs = source_evidence_refs(analysis)
    resolved_scope = normalized_scope(analysis, scope)
    enriched = [
        enrich_recommendation(
            item,
            source_refs=refs,
            scope=resolved_scope,
        )
        for item in raw_items
    ]

    reason_codes = result.get("reason_codes", [])
    if not isinstance(reason_codes, list):
        raise RecommendationEnrichmentError(
            "RECOMMENDATION_ENRICHMENT_REASON_CODES_INVALID"
        )
    may_use_finance = not (
        result.get("status") == "BLOCKED"
        or "RECOMMENDATION_POLICY_REQUIRED" in reason_codes
        or "SOURCE_BRIDGE_NOT_COMPLETE" in reason_codes
    )
    if may_use_finance:
        source_type = analysis.get("source_type")
        enriched.extend(
            build_financial_recommendations(
                calculation=calculation,
                reconciliation=reconciliation,
                source_type=(source_type if isinstance(source_type, str) else None),
                source_refs=refs,
                scope=resolved_scope,
            )
        )

    unique = {
        item["recommendation_id"]: item
        for item in enriched
    }
    ordered = sorted(
        unique.values(),
        key=lambda item: (
            {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(
                item.get("severity"), 9
            ),
            {"PROFIT": 0, "SUSTAINABLE_GROWTH": 1, "TURNOVER": 2}.get(
                item.get("priority_dimension"), 9
            ),
            item.get("category", ""),
            item["recommendation_id"],
        ),
    )
    result["recommendations"] = ordered
    result["recommendation_count"] = len(ordered)
    result["priority_order"] = [
        "PROFIT",
        "SUSTAINABLE_GROWTH",
        "TURNOVER",
    ]
    result["source_evidence_refs"] = refs
    result["bundle_hash"] = sha256(
        canonical_json(
            {
                key: value
                for key, value in result.items()
                if key != "bundle_hash"
            }
        )
    ).hexdigest()
    return result
