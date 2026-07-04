from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import json
from typing import Any

from quantum.insights import (
    RECOMMENDATION_BUNDLE_SCHEMA_VERSION,
    RECOMMENDATION_SCHEMA_VERSION,
    RecommendationError,
    build_recommendations,
)


_REQUIRED_BUNDLE_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "source_type",
        "policy_ref",
        "recommendation_count",
        "recommendations",
        "reason_codes",
        "bundle_hash",
    }
)


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


def _bundle_hash(bundle: Mapping[str, Any]) -> str:
    payload = {
        key: value
        for key, value in bundle.items()
        if key != "bundle_hash"
    }
    return sha256(_canonical_json(payload)).hexdigest()


def build_blocked_recommendation_bundle(
    *,
    source_type: str | None,
    reason_code: str,
) -> dict[str, Any]:
    if source_type is not None and (
        not isinstance(source_type, str) or not source_type.strip()
    ):
        raise RecommendationError("RECOMMENDATION_SOURCE_TYPE_INVALID")
    if not isinstance(reason_code, str) or not reason_code.strip():
        raise RecommendationError("RECOMMENDATION_REASON_CODE_INVALID")
    bundle: dict[str, Any] = {
        "schema_version": RECOMMENDATION_BUNDLE_SCHEMA_VERSION,
        "status": "BLOCKED",
        "source_type": source_type,
        "policy_ref": None,
        "recommendation_count": 0,
        "recommendations": [],
        "reason_codes": [reason_code],
        "bundle_hash": "",
    }
    bundle["bundle_hash"] = _bundle_hash(bundle)
    return bundle


def build_recommendation_bundle(
    analysis: Mapping[str, Any],
    policy: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return build_recommendations(analysis, policy)


def validate_recommendation_bundle(bundle: object) -> None:
    if not isinstance(bundle, Mapping):
        raise RecommendationError("RECOMMENDATION_BUNDLE_INVALID")
    if set(bundle) != _REQUIRED_BUNDLE_FIELDS:
        raise RecommendationError("RECOMMENDATION_BUNDLE_FIELDS_INVALID")
    if bundle.get("schema_version") != RECOMMENDATION_BUNDLE_SCHEMA_VERSION:
        raise RecommendationError("RECOMMENDATION_BUNDLE_SCHEMA_UNSUPPORTED")
    status = bundle.get("status")
    if status not in {"READY", "BLOCKED"}:
        raise RecommendationError("RECOMMENDATION_BUNDLE_STATUS_INVALID")
    recommendations = bundle.get("recommendations")
    reason_codes = bundle.get("reason_codes")
    if not isinstance(recommendations, list):
        raise RecommendationError("RECOMMENDATION_BUNDLE_ITEMS_INVALID")
    if not isinstance(reason_codes, list) or any(
        not isinstance(item, str) or not item
        for item in reason_codes
    ):
        raise RecommendationError("RECOMMENDATION_BUNDLE_REASONS_INVALID")
    count = bundle.get("recommendation_count")
    if (
        not isinstance(count, int)
        or isinstance(count, bool)
        or count < 0
        or count != len(recommendations)
    ):
        raise RecommendationError("RECOMMENDATION_BUNDLE_COUNT_INVALID")
    if status == "READY":
        if reason_codes:
            raise RecommendationError("RECOMMENDATION_BUNDLE_REASONS_INVALID")
        if not isinstance(bundle.get("policy_ref"), Mapping):
            raise RecommendationError("RECOMMENDATION_BUNDLE_POLICY_REF_INVALID")
    else:
        if recommendations or count != 0 or not reason_codes:
            raise RecommendationError("RECOMMENDATION_BUNDLE_BLOCKED_INVALID")
        if bundle.get("policy_ref") is not None:
            raise RecommendationError("RECOMMENDATION_BUNDLE_POLICY_REF_INVALID")
    if bundle.get("bundle_hash") != _bundle_hash(bundle):
        raise RecommendationError("RECOMMENDATION_BUNDLE_HASH_MISMATCH")
