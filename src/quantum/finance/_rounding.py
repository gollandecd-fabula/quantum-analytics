from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from ._common import (
    FinanceError, _ACCOUNTING_POINTS, _CURRENCY_RE, _HASH_RE, _ID_RE,
    _PRESENTATION_POINTS, _STATE_PRECEDENCE,
    _ROUNDING_MODES, _Value, _decimal_text, _is_non_negative_int,
    _is_nonempty_string, _is_positive_int, _make_nonvalid, _make_valid,
    _parse_decimal, _parse_rfc3339, _validate_signature, _clone_json,
    canonical_hash,
)

def _normalize_value(value: _Value, policy: Mapping[str, Any]) -> _Value:
    if value.state != "VALID" or value.value_type not in {"MONEY", "DECIMAL", "RATE"}:
        return value
    assert isinstance(value.value, Decimal)
    normalized, _ = _quantize(
        value.value, policy, "RULE_INPUT_NORMALIZATION", value.value_type
    )
    return _make_valid(
        normalized,
        value_type=value.value_type,
        unit=value.unit,
        currency=value.currency,
        source_ids=value.source_ids,
    )


def _propagate(
    values: Sequence[_Value],
    *,
    value_type: str,
    unit: str,
    currency: str | None,
) -> _Value | None:
    for state in _STATE_PRECEDENCE:
        matches = sorted(
            (value for value in values if value.state == state),
            key=lambda item: (item.reason_code or "", item.source_ids),
        )
        if matches:
            chosen = matches[0]
            return _make_nonvalid(
                state,
                value_type=value_type,
                unit=unit,
                currency=currency,
                reason_code=f"DEPENDENCY_{state}:{chosen.reason_code}",
                source_ids=tuple(
                    sorted({source for value in matches for source in value.source_ids})
                ),
            )
    return None


def validate_rounding_policy(policy: object, *, preview: bool = True) -> dict[str, Any]:
    if not isinstance(policy, Mapping):
        raise FinanceError("ROUNDING_POLICY_MALFORMED")
    required = {
        "policy_id", "version", "content_hash", "status", "calculation_mode",
        "calculation_scale", "money_scale", "rate_scale", "presentation_mode",
        "presentation_scale", "currency_presentation_scales", "application_points",
        "max_input_precision", "max_input_scale", "actor", "created_at", "source",
        "change_reason", "approval_reference", "supersedes",
    }
    if set(policy) != required:
        raise FinanceError("ROUNDING_POLICY_MALFORMED")
    if not isinstance(policy["policy_id"], str) or _ID_RE.fullmatch(policy["policy_id"]) is None:
        raise FinanceError("ROUNDING_POLICY_MALFORMED")
    if not _is_positive_int(policy["version"]):
        raise FinanceError("ROUNDING_POLICY_MALFORMED")
    if not isinstance(policy["content_hash"], str) or _HASH_RE.fullmatch(policy["content_hash"]) is None:
        raise FinanceError("ROUNDING_HASH_MISMATCH")
    if canonical_hash(policy, exclude=frozenset({"content_hash"})) != policy["content_hash"]:
        raise FinanceError("ROUNDING_HASH_MISMATCH")
    allowed_statuses = {"SHADOW", "PILOT", "ACTIVE"} if preview else {"ACTIVE"}
    if policy["status"] not in allowed_statuses:
        raise FinanceError("ROUNDING_POLICY_NOT_APPROVED")
    if policy["calculation_mode"] not in _ROUNDING_MODES or policy["presentation_mode"] not in _ROUNDING_MODES:
        raise FinanceError("ROUNDING_MODE_UNSUPPORTED")
    for field in (
        "calculation_scale", "money_scale", "rate_scale", "presentation_scale",
        "max_input_precision", "max_input_scale",
    ):
        value = policy[field]
        if not _is_non_negative_int(value) or value > 1000:
            raise FinanceError("ROUNDING_SCALE_INVALID")
    if policy["max_input_precision"] < 1 or policy["max_input_scale"] > policy["max_input_precision"]:
        raise FinanceError("ROUNDING_SCALE_INVALID")
    points = policy["application_points"]
    if (
        not isinstance(points, list)
        or not points
        or len(points) != len(set(points))
        or any(point not in _ACCOUNTING_POINTS | _PRESENTATION_POINTS for point in points)
    ):
        raise FinanceError("ROUNDING_POINT_FORBIDDEN")
    currency_scales = policy["currency_presentation_scales"]
    if not isinstance(currency_scales, Mapping) or any(
        not isinstance(code, str)
        or _CURRENCY_RE.fullmatch(code) is None
        or not _is_non_negative_int(scale)
        or scale > 28
        for code, scale in currency_scales.items()
    ):
        raise FinanceError("ROUNDING_CURRENCY_INVALID")
    for field in ("actor", "source", "change_reason"):
        if not _is_nonempty_string(policy[field]):
            raise FinanceError("ROUNDING_POLICY_MALFORMED")
    _parse_rfc3339(policy["created_at"], "ROUNDING_POLICY_MALFORMED")
    if policy["approval_reference"] is not None and not _is_nonempty_string(policy["approval_reference"]):
        raise FinanceError("ROUNDING_POLICY_MALFORMED")
    if policy["supersedes"] is not None:
        supersedes = policy["supersedes"]
        if (
            not isinstance(supersedes, Mapping)
            or set(supersedes) != {"policy_id", "version"}
            or not _is_nonempty_string(supersedes["policy_id"])
            or not _is_positive_int(supersedes["version"])
        ):
            raise FinanceError("ROUNDING_POLICY_MALFORMED")
    return _clone_json(policy)


def _quantize(
    value: Decimal,
    policy: Mapping[str, Any],
    application_point: str,
    value_type: str,
) -> tuple[Decimal, int]:
    if application_point not in policy["application_points"]:
        raise FinanceError("ROUNDING_POINT_FORBIDDEN")
    if application_point in _ACCOUNTING_POINTS:
        mode = policy["calculation_mode"]
        if application_point == "METRIC_FINAL_ACCOUNTING":
            scale = policy["money_scale"] if value_type == "MONEY" else policy["rate_scale"]
        else:
            scale = policy["calculation_scale"]
    else:
        mode = policy["presentation_mode"]
        scale = policy["presentation_scale"]
    quantum = Decimal(1).scaleb(-scale)
    try:
        rounded = value.quantize(quantum, rounding=_ROUNDING_MODES[mode])
    except InvalidOperation as exc:
        raise FinanceError("ROUNDING_OPERATION_INVALID") from exc
    return rounded, scale


def _input_decimal(value: object, policy: Mapping[str, Any], *, code: str) -> Decimal:
    parsed = _parse_decimal(
        value,
        code=code,
        max_precision=policy["max_input_precision"],
        max_scale=policy["max_input_scale"],
    )
    rounded, _ = _quantize(parsed, policy, "RULE_INPUT_NORMALIZATION", "DECIMAL")
    return rounded
