from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from ._common import (
    FinanceError, _HASH_RE, _Value, _clone_json, _is_nonempty_string,
    _is_positive_int, _make_nonvalid, _make_valid, _value_to_dict,
)
from ._rounding import _propagate, _quantize


def _validate_ref(value: object, code: str) -> dict[str, Any]:
    if (
        not isinstance(value, Mapping)
        or set(value) != {"id", "version", "content_hash"}
        or not _is_nonempty_string(value.get("id"))
        or not _is_positive_int(value.get("version"))
        or not isinstance(value.get("content_hash"), str)
        or _HASH_RE.fullmatch(str(value.get("content_hash"))) is None
    ):
        raise FinanceError(code)
    return _clone_json(value)


def _metric(
    value: _Value,
    *,
    accounting_view: str,
    expense_boundary: Sequence[str],
    policy: Mapping[str, Any],
    final_round: bool,
) -> dict[str, Any]:
    scale: int | None = None
    rounding: dict[str, Any] | None = None
    if value.state == "VALID" and final_round and value.value_type in {"MONEY", "DECIMAL", "RATE"}:
        assert isinstance(value.value, Decimal)
        rounded, scale = _quantize(
            value.value, policy, "METRIC_FINAL_ACCOUNTING", value.value_type
        )
        value = _make_valid(
            rounded,
            value_type=value.value_type,
            unit=value.unit,
            currency=value.currency,
            source_ids=value.source_ids,
        )
        rounding = {
            "policy_ref": {
                "id": policy["policy_id"],
                "version": policy["version"],
                "content_hash": policy["content_hash"],
            },
            "application_point": "METRIC_FINAL_ACCOUNTING",
            "resolved_mode": policy["calculation_mode"],
            "resolved_scale": scale,
        }
    typed = _value_to_dict(value, scale=scale)
    typed.update({
        "accounting_view": accounting_view,
        "expense_boundary": list(expense_boundary),
        "rounding": rounding,
    })
    return typed


def _expect(
    inputs: Mapping[str, _Value],
    metric_id: str,
    *,
    value_type: str,
    unit: str,
    currency: str | None,
) -> _Value:
    if metric_id not in inputs:
        return _make_nonvalid(
            "BLOCKED",
            value_type=value_type,
            unit=unit,
            currency=currency,
            reason_code=f"INPUT_REQUIRED_MISSING:{metric_id}",
            source_ids=(metric_id,),
        )
    value = inputs[metric_id]
    if value.value_type != value_type or value.unit != unit:
        return _make_nonvalid(
            "BLOCKED",
            value_type=value_type,
            unit=unit,
            currency=currency,
            reason_code=f"INPUT_SIGNATURE_MISMATCH:{metric_id}",
            source_ids=value.source_ids,
        )
    if value.currency != currency:
        return _make_nonvalid(
            "BLOCKED",
            value_type=value_type,
            unit=unit,
            currency=currency,
            reason_code=f"CURRENCY_MISMATCH:{metric_id}",
            source_ids=value.source_ids,
        )
    return value


def _money_sum(
    terms: Sequence[tuple[int, _Value]],
    *,
    currency: str,
    reason_unit: str = "MONEY",
) -> _Value:
    values = [value for _, value in terms]
    propagated = _propagate(
        values, value_type="MONEY", unit=reason_unit, currency=currency
    )
    if propagated is not None:
        return propagated
    total = Decimal("0")
    sources: list[str] = []
    for sign, value in terms:
        if value.value_type != "MONEY" or value.currency != currency:
            return _make_nonvalid(
                "BLOCKED",
                value_type="MONEY",
                unit=reason_unit,
                currency=currency,
                reason_code="CURRENCY_OR_TYPE_MISMATCH",
                source_ids=tuple((*sources, *value.source_ids)),
            )
        assert isinstance(value.value, Decimal)
        total += Decimal(sign) * value.value
        sources.extend(value.source_ids)
    return _make_valid(
        total,
        value_type="MONEY",
        unit=reason_unit,
        currency=currency,
        source_ids=sources,
    )
