from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from ._common import (
    _Value, _make_nonvalid, _make_valid, _value_from_dict,
)
from ._metrics import _expect, _money_sum
from ._rounding import _normalize_value, _propagate


def calculate_settlement_tax_profit(
    inputs: Mapping[str, _Value],
    tax_rate_raw: Mapping[str, Any],
    tax_base_metric_id: str,
    policy: Mapping[str, Any],
    currency: str,
    net_units: _Value,
    product_cost: _Value,
    other_expense: _Value,
) -> tuple[_Value, _Value, _Value, _Value, _Value]:
    settlement_ids = (
        "gross_sales_amount",
        "discounts_amount",
        "subsidies_amount",
        "marketplace_commission_amount",
        "forward_logistics_amount",
        "reverse_logistics_amount",
        "storage_amount",
        "advertising_amount",
        "fines_withholdings_amount",
    )
    settlement_values = {
        metric_id: _expect(
            inputs, metric_id,
            value_type="MONEY", unit="MONEY", currency=currency,
        )
        for metric_id in settlement_ids
    }
    net_marketplace_income = _money_sum(
        [
            (1, settlement_values["gross_sales_amount"]),
            (-1, settlement_values["discounts_amount"]),
            (1, settlement_values["subsidies_amount"]),
            (-1, settlement_values["marketplace_commission_amount"]),
            (-1, settlement_values["forward_logistics_amount"]),
            (-1, settlement_values["reverse_logistics_amount"]),
            (-1, settlement_values["storage_amount"]),
            (-1, settlement_values["advertising_amount"]),
            (-1, settlement_values["fines_withholdings_amount"]),
        ],
        currency=currency,
    )

    tax_rate = _normalize_value(
        _value_from_dict(tax_rate_raw, source_id="tax_rate"), policy
    )
    base_id = tax_base_metric_id
    available_bases = {
        **inputs,
        "net_marketplace_income_amount": net_marketplace_income,
        "product_cost_amount": product_cost,
        "other_expense_amount": other_expense,
    }
    tax_base = available_bases.get(base_id)
    if tax_base is None:
        tax_amount = _make_nonvalid(
            "BLOCKED",
            value_type="MONEY",
            unit="MONEY",
            currency=currency,
            reason_code=f"TAX_BASE_MISSING:{base_id}",
            source_ids=(base_id,),
        )
    else:
        propagated_tax = _propagate(
            [tax_rate, tax_base],
            value_type="MONEY",
            unit="MONEY",
            currency=currency,
        )
        if propagated_tax is not None:
            tax_amount = propagated_tax
        elif (
            tax_rate.value_type != "RATE"
            or tax_rate.unit != "RATE"
            or tax_rate.currency is not None
            or tax_base.value_type != "MONEY"
            or tax_base.unit != "MONEY"
            or tax_base.currency != currency
        ):
            tax_amount = _make_nonvalid(
                "BLOCKED",
                value_type="MONEY",
                unit="MONEY",
                currency=currency,
                reason_code="TAX_RULE_SIGNATURE_MISMATCH",
                source_ids=tuple((*tax_rate.source_ids, *tax_base.source_ids)),
            )
        else:
            assert isinstance(tax_rate.value, Decimal) and isinstance(tax_base.value, Decimal)
            tax_amount = _make_valid(
                tax_base.value * tax_rate.value,
                value_type="MONEY",
                unit="MONEY",
                currency=currency,
                source_ids=tuple((*tax_rate.source_ids, *tax_base.source_ids)),
            )

    net_profit = _money_sum(
        [
            (1, net_marketplace_income),
            (-1, product_cost),
            (-1, other_expense),
            (-1, tax_amount),
        ],
        currency=currency,
    )
    propagated_ppu = _propagate(
        [net_profit, net_units],
        value_type="MONEY",
        unit="MONEY_PER_ITEM",
        currency=currency,
    )
    if propagated_ppu is not None:
        profit_per_unit = propagated_ppu
    elif not isinstance(net_units.value, int) or net_units.value == 0:
        profit_per_unit = _make_nonvalid(
            "BLOCKED",
            value_type="MONEY",
            unit="MONEY_PER_ITEM",
            currency=currency,
            reason_code="ZERO_DENOMINATOR",
            source_ids=tuple((*net_profit.source_ids, *net_units.source_ids)),
        )
    elif net_units.value < 0:
        profit_per_unit = _make_nonvalid(
            "BLOCKED",
            value_type="MONEY",
            unit="MONEY_PER_ITEM",
            currency=currency,
            reason_code="NON_POSITIVE_DENOMINATOR",
            source_ids=tuple((*net_profit.source_ids, *net_units.source_ids)),
        )
    else:
        assert isinstance(net_profit.value, Decimal)
        profit_per_unit = _make_valid(
            net_profit.value / Decimal(net_units.value),
            value_type="MONEY",
            unit="MONEY_PER_ITEM",
            currency=currency,
            source_ids=tuple((*net_profit.source_ids, *net_units.source_ids)),
        )

    profitability = _make_nonvalid(
        "BLOCKED",
        value_type="RATE",
        unit="PERCENT",
        currency=None,
        reason_code="COST_DENOMINATOR_NOT_APPROVED",
        source_ids=(),
    )

    return net_marketplace_income, tax_amount, net_profit, profit_per_unit, profitability
