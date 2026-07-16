from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .enrichment import enrich_recommendation_bundle
from .recommendations import (
    RECOMMENDATION_BUNDLE_SCHEMA_VERSION,
    RECOMMENDATION_SCHEMA_VERSION,
    RecommendationError,
    build_recommendations as _build_recommendations,
    validate_recommendation_policy,
)


def build_recommendations(
    analysis: Mapping[str, Any],
    policy: Mapping[str, Any] | None,
    *,
    calculation: Mapping[str, Any] | None = None,
    reconciliation: Mapping[str, Any] | None = None,
    scope: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build source rules and enrich them with governed finance results."""
    if not isinstance(analysis, Mapping):
        return _build_recommendations(analysis, policy)
    normalized = dict(analysis)
    singular = normalized.get("finance_request_reason_code")
    plural = normalized.get("finance_request_reason_codes")
    if plural is None and isinstance(singular, str) and singular:
        normalized["finance_request_reason_codes"] = [singular]
    bundle = _build_recommendations(normalized, policy)
    return enrich_recommendation_bundle(
        bundle,
        normalized,
        calculation=calculation,
        reconciliation=reconciliation,
        scope=scope,
    )


__all__ = [
    "RECOMMENDATION_BUNDLE_SCHEMA_VERSION",
    "RECOMMENDATION_SCHEMA_VERSION",
    "RecommendationError",
    "build_recommendations",
    "validate_recommendation_policy",
]
