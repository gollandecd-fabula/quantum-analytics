from __future__ import annotations
from decimal import Decimal,ROUND_CEILING,ROUND_DOWN,ROUND_FLOOR,ROUND_HALF_EVEN,ROUND_HALF_UP,ROUND_UP
from typing import Any

_ROUNDING={"HALF_EVEN":ROUND_HALF_EVEN,"HALF_UP":ROUND_HALF_UP,"DOWN":ROUND_DOWN,"UP":ROUND_UP,"FLOOR":ROUND_FLOOR,"CEILING":ROUND_CEILING}


def _q(value:Decimal,scale:int,mode:str)->Decimal:
    return value.quantize(Decimal(1).scaleb(-scale),rounding=_ROUNDING[mode])


def _text(value:Decimal,scale:int)->str:
    if value.is_zero(): value=abs(value)
    return f"{value:.{scale}f}"


def reference_calculate(case:dict[str,Any])->dict[str,dict[str,str|None]]:
    scale=int(case["money_scale"]); mode=str(case["rounding_mode"])
    inputs={key:Decimal(value) for key,value in case["inputs"].items()}
    gross_units=int(case["gross_sales_units"])
    returned_units=int(case["returned_units"])
    resalable_units=int(case["resalable_returned_units"])
    compensated_units=int(case["compensated_returned_units"])
    return_compensation=inputs["return_compensation_amount"]
    if (
        gross_units < 0
        or returned_units < 0
        or resalable_units < 0
        or compensated_units < 0
        or returned_units > gross_units
        or resalable_units + compensated_units > returned_units
    ):
        raise ValueError("RETURN_UNIT_SEMANTICS_INVALID")
    if (
        return_compensation < 0
        or (compensated_units == 0 and return_compensation != 0)
        or (compensated_units > 0 and return_compensation <= 0)
    ):
        raise ValueError("RETURN_COMPENSATION_SEMANTICS_INVALID")
    net_units=gross_units-returned_units
    cost=Decimal(case["cost_per_unit"])*Decimal(gross_units-resalable_units)
    other=sum((Decimal(item["value"])*Decimal(net_units) if item["unit"]=="MONEY_PER_ITEM" else Decimal(item["value"])) for item in case["other_expenses"])
    marketplace=(inputs["gross_sales_amount"]-inputs["discounts_amount"]+inputs["subsidies_amount"]+return_compensation-inputs["marketplace_commission_amount"]-inputs["forward_logistics_amount"]-inputs["reverse_logistics_amount"]-inputs["storage_amount"]-inputs["advertising_amount"]-inputs["fines_withholdings_amount"])
    bases={**inputs,"net_marketplace_income_amount":marketplace,"product_cost_amount":cost,"other_expense_amount":other}
    tax=bases[case["tax_base_metric_id"]]*Decimal(case["tax_rate"])
    profit=marketplace-cost-other-tax
    def valid(value:Decimal)->dict[str,str|None]:
        return {"state":"VALID","value":_text(_q(value,scale,mode),scale)}
    ppu={"state":"BLOCKED","value":None} if net_units<=0 else valid(profit/Decimal(net_units))
    return {"net_sold_units":{"state":"VALID","value":str(net_units)},"product_cost_amount":valid(cost),"other_expense_amount":valid(other),"tax_amount":valid(tax),"net_marketplace_income_amount":valid(marketplace),"net_profit_amount":valid(profit),"profit_per_sold_unit":ppu,"profitability_of_costs":{"state":"BLOCKED","value":None}}
