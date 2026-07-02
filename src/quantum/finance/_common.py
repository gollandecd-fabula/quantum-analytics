from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import (
    Decimal,
    InvalidOperation,
    ROUND_CEILING,
    ROUND_DOWN,
    ROUND_FLOOR,
    ROUND_HALF_EVEN,
    ROUND_HALF_UP,
    ROUND_UP,
)
from typing import Any

KERNEL_SCHEMA_VERSION = "quantum-financial-kernel-result-v1"
RESOLVER_CONTRACT_VERSION = "quantum-rule-resolver-v1"
PUBLICATION_STATE = "PREVIEW_ONLY"

_STATES = frozenset({"VALID", "EMPTY", "BLOCKED", "UNAVAILABLE", "CONFLICT"})
_STATE_PRECEDENCE = ("CONFLICT", "BLOCKED", "UNAVAILABLE", "EMPTY")
_NUMERIC_TYPES = frozenset({"MONEY", "DECIMAL", "RATE", "INTEGER"})
_VALUE_TYPES = _NUMERIC_TYPES | {"BOOLEAN"}
_ROUNDING_MODES = {
    "HALF_EVEN": ROUND_HALF_EVEN,
    "HALF_UP": ROUND_HALF_UP,
    "DOWN": ROUND_DOWN,
    "UP": ROUND_UP,
    "FLOOR": ROUND_FLOOR,
    "CEILING": ROUND_CEILING,
}
_ACCOUNTING_POINTS = frozenset({
    "RULE_INPUT_NORMALIZATION",
    "RULE_COMPONENT_RESULT",
    "METRIC_FINAL_ACCOUNTING",
})
_PRESENTATION_POINTS = frozenset({"REPORT_PRESENTATION", "EXPORT_PRESENTATION"})
_SCOPE_ORDER = (
    "product_id",
    "product_group_id",
    "marketplace_account_id",
    "marketplace",
    "calculation_profile_id",
    "scenario_id",
)
_DECIMAL_RE = re.compile(r"^-?(0|[1-9][0-9]*)(?:\.([0-9]+))?$")
_INTEGER_RE = re.compile(r"^-?(0|[1-9][0-9]*)$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_HASH_RE = re.compile(r"^[a-f0-9]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_RFC3339_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$"
)

_MAX_EXPRESSION_NODES = 128
_MAX_EXPRESSION_DEPTH = 24
_MAX_EXPRESSION_ARGUMENTS = 16
_MAX_EXPRESSION_DEPENDENCIES = 128
_MAX_DECIMAL_INPUT_PRECISION = 1000
_MAX_DECIMAL_INPUT_SCALE = 1000
_MAX_OTHER_EXPENSE_COMPONENTS = 64


class FinanceError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class _Value:
    state: str
    value: Decimal | int | bool | None
    value_type: str
    unit: str
    currency: str | None
    reason_code: str | None
    source_ids: tuple[str, ...]


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise FinanceError("FINANCE_JSON_INVALID") from exc


def canonical_hash(document: Mapping[str, Any], *, exclude: frozenset[str] = frozenset()) -> str:
    payload = {key: value for key, value in document.items() if key not in exclude}
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _clone_json(value: Any) -> Any:
    return json.loads(_canonical_json(value))


def _is_nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _is_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_non_negative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _parse_rfc3339(value: object, code: str) -> datetime:
    if not isinstance(value, str) or _RFC3339_RE.fullmatch(value) is None:
        raise FinanceError(code)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise FinanceError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FinanceError(code)
    return parsed


def _parse_decimal(
    value: object,
    *,
    code: str,
    max_precision: int | None = None,
    max_scale: int | None = None,
) -> Decimal:
    if not isinstance(value, str) or _DECIMAL_RE.fullmatch(value) is None:
        raise FinanceError(code)
    match = _DECIMAL_RE.fullmatch(value)
    assert match is not None
    fractional = match.group(2) or ""
    digits = value.lstrip("-").replace(".", "")
    if max_precision is not None and len(digits) > max_precision:
        raise FinanceError("ROUNDING_INPUT_PRECISION_EXCEEDED")
    if max_scale is not None and len(fractional) > max_scale:
        raise FinanceError("ROUNDING_INPUT_SCALE_EXCEEDED")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise FinanceError(code) from exc
    if not parsed.is_finite():
        raise FinanceError(code)
    return parsed


def _parse_integer(
    value: object,
    *,
    code: str,
    max_precision: int | None = None,
) -> int:
    if not isinstance(value, str) or _INTEGER_RE.fullmatch(value) is None:
        raise FinanceError(code)
    if max_precision is not None and len(value.lstrip("-")) > max_precision:
        raise FinanceError("ROUNDING_INPUT_PRECISION_EXCEEDED")
    try:
        return int(value)
    except ValueError as exc:
        raise FinanceError(code) from exc


def _decimal_text(value: Decimal, scale: int | None = None) -> str:
    if value.is_zero():
        value = abs(value)
    if scale is not None:
        return f"{value:.{scale}f}"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _validate_signature(value_type: object, unit: object, currency: object) -> tuple[str, str, str | None]:
    if value_type not in _VALUE_TYPES or not _is_nonempty_string(unit):
        raise FinanceError("VALUE_SIGNATURE_INVALID")
    value_type = str(value_type)
    unit = str(unit)
    if value_type == "MONEY":
        if not isinstance(currency, str) or _CURRENCY_RE.fullmatch(currency) is None:
            raise FinanceError("VALUE_CURRENCY_INVALID")
        return value_type, unit, currency
    if currency is not None:
        raise FinanceError("VALUE_CURRENCY_INVALID")
    return value_type, unit, None


def _make_nonvalid(
    state: str,
    *,
    value_type: str,
    unit: str,
    currency: str | None,
    reason_code: str,
    source_ids: Sequence[str] = (),
) -> _Value:
    if state not in _STATES or state == "VALID":
        raise FinanceError("VALUE_STATE_INVALID")
    if not _is_nonempty_string(reason_code):
        raise FinanceError("VALUE_REASON_INVALID")
    _validate_signature(value_type, unit, currency)
    return _Value(
        state=state,
        value=None,
        value_type=value_type,
        unit=unit,
        currency=currency,
        reason_code=reason_code,
        source_ids=tuple(sorted(set(source_ids))),
    )


def _make_valid(
    value: Decimal | int | bool,
    *,
    value_type: str,
    unit: str,
    currency: str | None,
    source_ids: Sequence[str] = (),
) -> _Value:
    _validate_signature(value_type, unit, currency)
    if value_type == "BOOLEAN":
        if not isinstance(value, bool):
            raise FinanceError("VALUE_TYPE_INVALID")
    elif value_type == "INTEGER":
        if not isinstance(value, int) or isinstance(value, bool):
            raise FinanceError("VALUE_TYPE_INVALID")
    elif not isinstance(value, Decimal):
        raise FinanceError("VALUE_TYPE_INVALID")
    return _Value(
        state="VALID",
        value=value,
        value_type=value_type,
        unit=unit,
        currency=currency,
        reason_code=None,
        source_ids=tuple(sorted(set(source_ids))),
    )


def _value_to_dict(value: _Value, *, scale: int | None = None) -> dict[str, Any]:
    if value.state != "VALID":
        encoded: str | bool | None = None
    elif value.value_type == "BOOLEAN":
        encoded = bool(value.value)
    elif value.value_type == "INTEGER":
        encoded = str(value.value)
    else:
        assert isinstance(value.value, Decimal)
        encoded = _decimal_text(value.value, scale)
    return {
        "state": value.state,
        "value": encoded,
        "value_type": value.value_type,
        "unit": value.unit,
        "currency": value.currency,
        "reason_code": value.reason_code,
        "source_ids": list(value.source_ids),
    }


def _value_from_dict(raw: object, *, source_id: str) -> _Value:
    if not isinstance(raw, Mapping):
        raise FinanceError("TYPED_VALUE_MALFORMED")
    required = {
        "state", "value", "value_type", "unit", "currency", "reason_code", "source_ids",
    }
    if set(raw) != required:
        raise FinanceError("TYPED_VALUE_MALFORMED")
    value_type, unit, currency = _validate_signature(
        raw.get("value_type"), raw.get("unit"), raw.get("currency")
    )
    state = raw.get("state")
    if state not in _STATES:
        raise FinanceError("VALUE_STATE_INVALID")
    source_ids_raw = raw.get("source_ids")
    if (
        not isinstance(source_ids_raw, list)
        or any(not _is_nonempty_string(item) for item in source_ids_raw)
        or len(source_ids_raw) != len(set(source_ids_raw))
    ):
        raise FinanceError("VALUE_SOURCES_INVALID")
    source_ids = tuple(sorted(set([source_id, *source_ids_raw])))
    if state != "VALID":
        if raw.get("value") is not None or not _is_nonempty_string(raw.get("reason_code")):
            raise FinanceError("TYPED_VALUE_MALFORMED")
        return _make_nonvalid(
            str(state),
            value_type=value_type,
            unit=unit,
            currency=currency,
            reason_code=str(raw["reason_code"]),
            source_ids=source_ids,
        )
    if raw.get("reason_code") is not None:
        raise FinanceError("TYPED_VALUE_MALFORMED")
    if value_type == "BOOLEAN":
        if not isinstance(raw.get("value"), bool):
            raise FinanceError("VALUE_TYPE_INVALID")
        return _make_valid(
            bool(raw["value"]),
            value_type=value_type,
            unit=unit,
            currency=currency,
            source_ids=source_ids,
        )
    if value_type == "INTEGER":
        return _make_valid(
            _parse_integer(
                raw.get("value"),
                code="VALUE_TYPE_INVALID",
                max_precision=_MAX_DECIMAL_INPUT_PRECISION,
            ),
            value_type=value_type,
            unit=unit,
            currency=currency,
            source_ids=source_ids,
        )
    return _make_valid(
        _parse_decimal(
            raw.get("value"),
            code="VALUE_DECIMAL_INVALID",
            max_precision=_MAX_DECIMAL_INPUT_PRECISION,
            max_scale=_MAX_DECIMAL_INPUT_SCALE,
        ),
        value_type=value_type,
        unit=unit,
        currency=currency,
        source_ids=source_ids,
    )
