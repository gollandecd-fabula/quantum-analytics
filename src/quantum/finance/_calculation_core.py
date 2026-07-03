from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from ._common import (
    FinanceError,
    _Value,
    _make_nonvalid,
    _make_valid,
    _value_from_dict,
)
from ._metrics import _expect
from ._rounding import _normalize_value, _propagate


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
    net = _propagate(
        [gross, returned],
        value_type="INTEGER",
        unit="ITEM",
        currency=None,
    )
    if net is None:
        assert isinstance(gross.value, int)
        assert isinstance(returned.value, int)
        net = _make_valid(
            gross.value - returned.value,
            value_type="INTEGER",
            unit="ITEM",
            currency=None,
            source_ids=(*gross.source_ids, *returned.source_ids),
        )

    cpu = _normalize_value(
        _value_from_dict(
            cost_per_unit_raw,
            source_id="cost_per_unit",
        ),
        policy,
    )
    if (
        cpu.value_type,
        cpu.unit,
        cpu.currency,
    ) != ("MONEY", "MONEY_PER_ITEM", currency):
        cost = _make_nonvalid(
            "BLOCKED",
            value_type="MONEY",
            unit="MONEY",
            currency=currency,
            reason_code="COST_RULE_SIGNATURE_MISMATCH",
            source_ids=cpu.source_ids,
        )
    elif cpu.state == "VALID" and cpu.value < 0:
        raise FinanceError("COST_PER_UNIT_NEGATIVE_FORBIDDEN")
    elif net.state == "VALID" and net.value < 0:
        cost = _make_nonvalid(
            "BLOCKED",
            value_type="MONEY",
            unit="MONEY",
            currency=currency,
            reason_code="RETURN_COST_RESTORATION_POLICY_REQUIRED",
            source_ids=(*net.source_ids, *cpu.source_ids),
        )
    else:
        cost = _propagate(
            [net, cpu],
            value_type="MONEY",
            unit="MONEY",
            currency=currency,
        )
        if cost is None:
            assert isinstance(net.value, int)
            assert isinstance(cpu.value, Decimal)
            cost = _make_valid(
                Decimal(net.value) * cpu.value,
                value_type="MONEY",
                unit="MONEY",
                currency=currency,
                source_ids=(*net.source_ids, *cpu.source_ids),
            )
    return net, cost
