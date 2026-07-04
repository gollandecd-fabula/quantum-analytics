from __future__ import annotations

from collections.abc import Mapping
from typing import Any

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
) -> dict[str, Any]:
    """Normalize compatible bridge blocker forms before recommendation rules."""
    if not isinstance(analysis, Mapping):
        return _build_recommendations(analysis, policy)
    normalized = dict(analysis)
    singular = normalized.get("finance_request_reason_code")
    plural = normalized.get("finance_request_reason_codes")
    if plural is None and isinstance(singular, str) and singular:
        normalized["finance_request_reason_codes"] = [singular]
    return _build_recommendations(normalized, policy)


__all__ = [
    "RECOMMENDATION_BUNDLE_SCHEMA_VERSION",
    "RECOMMENDATION_SCHEMA_VERSION",
    "RecommendationError",
    "build_recommendations",
    "validate_recommendation_policy",
]
