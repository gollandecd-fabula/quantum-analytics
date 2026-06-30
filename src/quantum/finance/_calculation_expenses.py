from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from ._common import (
    FinanceError, _Value, _is_nonempty_string, _make_nonvalid, _make_valid,
    _value_from_dict,
)
from ._metrics import _expect, _money_sum
from ._rounding import _normalize_value, _propagate

_SUPPORTED_EXPENSE_UNITS = {
    "MONEY",
    "MONEY_PER_PERIOD",
    "MONEY_PER_ITEM",
    "MONEY_PER_ORDER",
    "MONEY_PER_EVENT",
}


def calculate_other_expense(
    components_raw: object,
    inputs: Mapping[str, _Value],
    net_units: _Value,
    policy: Mapping[str, Any],
    currency: str,
) -> _Value:
    if not isinstance(components_raw, list):
        raise FinanceError("OTHER_EXPENSE_COMPONENTS_INVALID")
    component_ids: set[str] = set()
    expense_terms: list[tuple[int, _Value]] = []
    for component in components_raw:
        if (
            not isinstance(component, Mapping)
            or set(component) != {"component_id", "value"}
            or not _is_nonempty_string(component.get("component_id"))
            or component["component_id"] in component_ids
        ):
            raise FinanceError("OTHER_EXPENSE_COMPONENTS_INVALID")
        component_ids.add(component["component_id"])
        value = _normalize_value(
            _value_from_dict(
                component["value"],
                source_id=f"other_expense:{component['component_id']}",
            ),
            policy,
        )
        if value.value_type != "MONEY" or value.currency != currency:
            expense_terms.append((
                1,
                _make_nonvalid(
                    "BLOCKED",
                    value_type="MONEY",
                    unit="MONEY",
                    currency=currency,
                    reason_code="OTHER_EXPENSE_SIGNATURE_MISMATCH",
                    source_ids=value.source_ids,
                ),
            ))
            continue
        if value.unit not in _SUPPORTED_EXPENSE_UNITS:
            expense_terms.append((
                1,
                _make_nonvalid(
                    "BLOCKED",
                    value_type="MONEY",
                    unit="MONEY",
                    currency=currency,
                    reason_code="OTHER_EXPENSE_UNIT_UNSUPPORTED",
                    source_ids=value.source_ids,
                ),
            ))
            continue
        if value.state != "VALID":
            expense_terms.append((1, value))
            continue
        assert isinstance(value.value, Decimal)
        if value.unit in {"MONEY", "MONEY_PER_PERIOD"}:
            amount = value
            if value.unit != "MONEY":
                amount = _make_valid(
                    value.value,
                    value_type="MONEY",
                    unit="MONEY",
                    currency=currency,
                    source_ids=value.source_ids,
                )
        elif value.unit == "MONEY_PER_ITEM":
            propagated = _propagate(
                [net_units, value],
                value_type="MONEY",
                unit="MONEY",
                currency=currency,
            )
            if propagated is not None:
                amount = propagated
            else:
                assert isinstance(net_units.value, int)
                amount = _make_valid(
                    Decimal(net_units.value) * value.value,
                    value_type="MONEY",
                    unit="MONEY",
                    currency=currency,
                    source_ids=tuple((*net_units.source_ids, *value.source_ids)),
                )
        elif value.unit == "MONEY_PER_ORDER":
            orders = _expect(
                inputs, "orders_count",
                value_type="INTEGER", unit="ORDER", currency=None,
            )
            propagated = _propagate(
                [orders, value],
                value_type="MONEY",
                unit="MONEY",
                currency=currency,
            )
            if propagated is not None:
                amount = propagated
            else:
                assert isinstance(orders.value, int)
                amount = _make_valid(
                    Decimal(orders.value) * value.value,
                    value_type="MONEY",
                    unit="MONEY",
                    currency=currency,
                    source_ids=tuple((*orders.source_ids, *value.source_ids)),
                )
        else:
            events = _expect(
                inputs, "event_count",
                value_type="INTEGER", unit="EVENT", currency=None,
            )
            propagated = _propagate(
                [events, value],
                value_type="MONEY",
                unit="MONEY",
                currency=currency,
            )
            if propagated is not None:
                amount = propagated
            else:
                assert isinstance(events.value, int)
                amount = _make_valid(
                    Decimal(events.value) * value.value,
                    value_type="MONEY",
                    unit="MONEY",
                    currency=currency,
                    source_ids=tuple((*events.source_ids, *value.source_ids)),
                )
        expense_terms.append((1, amount))
    return (
        _money_sum(expense_terms, currency=currency)
        if expense_terms
        else _make_nonvalid(
            "BLOCKED",
            value_type="MONEY",
            unit="MONEY",
            currency=currency,
            reason_code="OTHER_EXPENSE_RULE_REQUIRED_MISSING",
            source_ids=(),
        )
    )
