from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from ._common import (
    _Value, _make_nonvalid, _make_valid, _value_from_dict,
)
from ._metrics import _expect
from ._rounding import _normalize_value, _propagate


def calculate_units_and_product_cost(
    inputs: Mapping[str, _Value],
    cost_per_unit_raw: Mapping[str, Any],
    policy: Mapping[str, Any],
    currency: str,
) -> tuple[_Value, _Value]:
    gross_units = _expect(
        inputs, "gross_sales_units",
        value_type="INTEGER", unit="ITEM", currency=None,
    )
    returned_units = _expect(
        inputs, "returned_units",
        value_type="INTEGER", unit="ITEM", currency=None,
    )
    unit_dependencies = [gross_units, returned_units]
    propagated_units = _propagate(
        unit_dependencies, value_type="INTEGER", unit="ITEM", currency=None
    )
    if propagated_units is not None:
        net_units = propagated_units
    else:
        assert isinstance(gross_units.value, int) and isinstance(returned_units.value, int)
        net_units = _make_valid(
            gross_units.value - returned_units.value,
            value_type="INTEGER",
            unit="ITEM",
            currency=None,
            source_ids=tuple((*gross_units.source_ids, *returned_units.source_ids)),
        )

    cost_per_unit = _normalize_value(
        _value_from_dict(cost_per_unit_raw, source_id="cost_per_unit"), policy
    )
    cost_dependencies = [net_units, cost_per_unit]
    propagated_cost = _propagate(
        cost_dependencies,
        value_type="MONEY",
        unit="MONEY",
        currency=currency,
    )
    if propagated_cost is not None:
        product_cost = propagated_cost
    elif (
        cost_per_unit.value_type != "MONEY"
        or cost_per_unit.unit != "MONEY_PER_ITEM"
        or cost_per_unit.currency != currency
    ):
        product_cost = _make_nonvalid(
            "BLOCKED",
            value_type="MONEY",
            unit="MONEY",
            currency=currency,
            reason_code="COST_RULE_SIGNATURE_MISMATCH",
            source_ids=cost_per_unit.source_ids,
        )
    else:
        assert isinstance(net_units.value, int) and isinstance(cost_per_unit.value, Decimal)
        product_cost = _make_valid(
            Decimal(net_units.value) * cost_per_unit.value,
            value_type="MONEY",
            unit="MONEY",
            currency=currency,
            source_ids=tuple((*net_units.source_ids, *cost_per_unit.source_ids)),
        )

    return net_units, product_cost
