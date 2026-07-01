from collections.abc import Mapping
from decimal import Decimal
from typing import Any
from ._common import _Value,_make_nonvalid,_make_valid,_value_from_dict
from ._metrics import _money_sum
from ._rounding import _normalize_value,_propagate

def calculate_other_expense(raw:object,inputs:Mapping[str,_Value],net:_Value,policy:Mapping[str,Any],currency:str)->_Value:
    if not isinstance(raw,list) or not raw:
        return _make_nonvalid("BLOCKED",value_type="MONEY",unit="MONEY",currency=currency,reason_code="OTHER_EXPENSE_RULE_REQUIRED_MISSING")
    terms=[]
    for item in raw:
        value=_normalize_value(_value_from_dict(item["value"],source_id="other_expense"),policy)
        if value.value_type!="MONEY" or value.currency!=currency or value.unit not in {"MONEY","MONEY_PER_ITEM"}:
            return _make_nonvalid("BLOCKED",value_type="MONEY",unit="MONEY",currency=currency,reason_code="OTHER_EXPENSE_SIGNATURE_MISMATCH",source_ids=value.source_ids)
        amount=value
        if value.unit=="MONEY_PER_ITEM":
            amount=_propagate([net,value],value_type="MONEY",unit="MONEY",currency=currency)
            if amount is None:
                assert isinstance(net.value,int) and isinstance(value.value,Decimal)
                amount=_make_valid(Decimal(net.value)*value.value,value_type="MONEY",unit="MONEY",currency=currency,source_ids=net.source_ids+value.source_ids)
        terms.append((1,amount))
    return _money_sum(terms,currency=currency)
