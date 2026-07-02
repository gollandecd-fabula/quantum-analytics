from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from ._common import _Value, _make_nonvalid, _make_valid, _value_from_dict
from ._metrics import _expect
from ._rounding import _normalize_value, _propagate


def _return_semantics_blocked(source_ids: tuple[str, ...]) -> _Value:
    return _make_nonvalid(
        "BLOCKED",
        value_type="INTEGER",
        unit="ITEM",
        currency=None,
        reason_code="RETURN_UNIT_SEMANTICS_INVALID",
        source_ids=source_ids,
    )


def calculate_units_and_product_cost(
    inputs: Mapping[str, _Value],
    cost_per_unit_raw: Mapping[str, Any],
    policy: Mapping[str, Any],
    currency: str,
) -> tuple[_Value, _Value]:
    gross = _expect(
        inputs,
        "gross_sales_units",
        value_type="INTEGER",
        unit="ITEM",
        currency=None,
    )
    returned = _expect(
        inputs,
        "returned_units",
        value_type="INTEGER",
        unit="ITEM",
        currency=None,
    )
    resalable = _expect(
        inputs,
        "resalable_returned_units",
        value_type="INTEGER",
        unit="ITEM",
        currency=None,
    )
    compensated = _expect(
        inputs,
        "compensated_returned_units",
        value_type="INTEGER",
        unit="ITEM",
        currency=None,
    )

    net = _propagate(
        [gross, returned],
        value_type="INTEGER",
        unit="ITEM",
        currency=None,
    )
    if net is None:
        assert isinstance(gross.value, int) and isinstance(returned.value, int)
        sources = (*gross.source_ids, *returned.source_ids)
        if gross.value < 0 or returned.value < 0 or returned.value > gross.value:
            net = _return_semantics_blocked(sources)
        else:
            net = _make_valid(
                gross.value - returned.value,
                value_type="INTEGER",
                unit="ITEM",
                currency=None,
                source_ids=sources,
            )

    cost_units = _propagate(
        [gross, returned, resalable, compensated],
        value_type="INTEGER",
        unit="ITEM",
        currency=None,
    )
    if cost_units is None:
        assert isinstance(gross.value, int)
        assert isinstance(returned.value, int)
        assert isinstance(resalable.value, int)
        assert isinstance(compensated.value, int)
        sources = (
            *gross.source_ids,
            *returned.source_ids,
            *resalable.source_ids,
            *compensated.source_ids,
        )
        if (
            gross.value < 0
            or returned.value < 0
            or resalable.value < 0
            or compensated.value < 0
            or returned.value > gross.value
            or resalable.value + compensated.value > returned.value
        ):
            cost_units = _return_semantics_blocked(sources)
        else:
            cost_units = _make_valid(
                gross.value - resalable.value,
                value_type="INTEGER",
                unit="ITEM",
                currency=None,
                source_ids=sources,
            )

    cpu = _normalize_value(
        _value_from_dict(cost_per_unit_raw, source_id="cost_per_unit"),
        policy,
    )
    if (cpu.value_type, cpu.unit, cpu.currency) != (
        "MONEY",
        "MONEY_PER_ITEM",
        currency,
    ):
        cost = _make_nonvalid(
            "BLOCKED",
            value_type="MONEY",
            unit="MONEY",
            currency=currency,
            reason_code="COST_RULE_SIGNATURE_MISMATCH",
            source_ids=cpu.source_ids,
        )
    else:
        cost = _propagate(
            [cost_units, cpu],
            value_type="MONEY",
            unit="MONEY",
            currency=currency,
        )
        if cost is None:
            assert isinstance(cost_units.value, int)
            assert isinstance(cpu.value, Decimal)
            cost = _make_valid(
                Decimal(cost_units.value) * cpu.value,
                value_type="MONEY",
                unit="MONEY",
                currency=currency,
                source_ids=(*cost_units.source_ids, *cpu.source_ids),
            )
    return net, cost
