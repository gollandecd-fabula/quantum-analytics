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
    ids = (
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
    values = {
        metric_id: _expect(
            inputs,
            metric_id,
            value_type="MONEY",
            unit="MONEY",
            currency=currency,
        )
        for metric_id in ids
    }
    income = _money_sum(
        [
            (1, values[ids[0]]),
            (-1, values[ids[1]]),
            (1, values[ids[2]]),
            (-1, values[ids[3]]),
            (-1, values[ids[4]]),
            (-1, values[ids[5]]),
            (-1, values[ids[6]]),
            (-1, values[ids[7]]),
            (-1, values[ids[8]]),
        ],
        currency=currency,
    )
    rate = _normalize_value(
        _value_from_dict(tax_rate_raw, source_id="tax_rate"),
        policy,
    )
    if rate.state == "VALID":
        assert isinstance(rate.value, Decimal)
        if rate.value < 0 or rate.value > 1:
            raise FinanceError("TAX_RATE_OUT_OF_RANGE")

    bases = {
        **inputs,
        "net_marketplace_income_amount": income,
        "product_cost_amount": product_cost,
        "other_expense_amount": other_expense,
    }
    base = bases.get(tax_base_metric_id)
    if base is None:
        tax = _make_nonvalid(
            "BLOCKED",
            value_type="MONEY",
            unit="MONEY",
            currency=currency,
            reason_code="TAX_BASE_MISSING:" + tax_base_metric_id,
            source_ids=(tax_base_metric_id,),
        )
    elif (
        rate.value_type,
        rate.unit,
        rate.currency,
    ) != ("RATE", "RATE", None) or (
        base.value_type,
        base.unit,
        base.currency,
    ) != ("MONEY", "MONEY", currency):
        tax = _make_nonvalid(
            "BLOCKED",
            value_type="MONEY",
            unit="MONEY",
            currency=currency,
            reason_code="TAX_RULE_SIGNATURE_MISMATCH",
            source_ids=rate.source_ids + base.source_ids,
        )
    elif base.state == "VALID" and base.value < 0:
        tax = _make_nonvalid(
            "BLOCKED",
            value_type="MONEY",
            unit="MONEY",
            currency=currency,
            reason_code="TAX_BASE_NEGATIVE_POLICY_REQUIRED",
            source_ids=rate.source_ids + base.source_ids,
        )
    else:
        tax = _propagate(
            [rate, base],
            value_type="MONEY",
            unit="MONEY",
            currency=currency,
        )
        if tax is None:
            assert isinstance(rate.value, Decimal)
            assert isinstance(base.value, Decimal)
            tax = _make_valid(
                base.value * rate.value,
                value_type="MONEY",
                unit="MONEY",
                currency=currency,
                source_ids=rate.source_ids + base.source_ids,
            )
    profit = _money_sum(
        [
            (1, income),
            (-1, product_cost),
            (-1, other_expense),
            (-1, tax),
        ],
        currency=currency,
    )
    ppu = _propagate(
        [profit, net_units],
        value_type="MONEY",
        unit="MONEY_PER_ITEM",
        currency=currency,
    )
    if ppu is None:
        if not isinstance(net_units.value, int) or net_units.value <= 0:
            code = (
                "ZERO_DENOMINATOR"
                if net_units.value == 0
                else "NON_POSITIVE_DENOMINATOR"
            )
            ppu = _make_nonvalid(
                "BLOCKED",
                value_type="MONEY",
                unit="MONEY_PER_ITEM",
                currency=currency,
                reason_code=code,
                source_ids=profit.source_ids + net_units.source_ids,
            )
        else:
            assert isinstance(profit.value, Decimal)
            ppu = _make_valid(
                profit.value / Decimal(net_units.value),
                value_type="MONEY",
                unit="MONEY_PER_ITEM",
                currency=currency,
                source_ids=profit.source_ids + net_units.source_ids,
            )
    profitability = _make_nonvalid(
        "BLOCKED",
        value_type="RATE",
        unit="PERCENT",
        currency=None,
        reason_code="COST_DENOMINATOR_NOT_APPROVED",
        source_ids=(),
    )
    return income, tax, profit, ppu, profitability
