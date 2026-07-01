from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal,InvalidOperation
from pathlib import Path

from quantum.ingestion.fingerprints import structural_fingerprint
from quantum.ingestion.schema_registry import SchemaDetection

SCHEMA_ID="wb-local-pilot-financial-v1"
ADAPTER_ID="wildberries-local-financial"
ADAPTER_VERSION="1.0"
HEADERS=(
    "row_id","product_id","event_time","gross_sales_units","returned_units",
    "gross_sales_amount","discounts_amount","subsidies_amount",
    "marketplace_commission_amount","forward_logistics_amount",
    "reverse_logistics_amount","storage_amount","advertising_amount",
    "fines_withholdings_amount","currency",
)
_DECIMAL=re.compile(r"^-?(0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_INTEGER=re.compile(r"^(0|[1-9][0-9]*)$")
_CURRENCY=re.compile(r"^[A-Z]{3}$")
_MONEY_FIELDS=HEADERS[5:14]
_MAX_ROWS=100000


class FinancialCsvError(ValueError):
    def __init__(self,code:str)->None:
        super().__init__(code);self.code=code


@dataclass(frozen=True,slots=True)
class ProductTotals:
    product_id:str
    gross_sales_units:int
    returned_units:int
    gross_sales_amount:Decimal
    discounts_amount:Decimal
    subsidies_amount:Decimal
    marketplace_commission_amount:Decimal
    forward_logistics_amount:Decimal
    reverse_logistics_amount:Decimal
    storage_amount:Decimal
    advertising_amount:Decimal
    fines_withholdings_amount:Decimal
    currency:str
    source_row_hashes:tuple[str,...]


@dataclass(frozen=True,slots=True)
class FinancialDataset:
    schema_id:str
    adapter_id:str
    adapter_version:str
    currency:str
    row_count:int
    products:tuple[ProductTotals,...]


def _decimal(value:str)->Decimal:
    if not isinstance(value,str) or _DECIMAL.fullmatch(value) is None:raise FinancialCsvError("FINANCIAL_DECIMAL_INVALID")
    try:parsed=Decimal(value)
    except InvalidOperation as exc:raise FinancialCsvError("FINANCIAL_DECIMAL_INVALID") from exc
    if not parsed.is_finite():raise FinancialCsvError("FINANCIAL_DECIMAL_INVALID")
    return parsed


def _integer(value:str)->int:
    if not isinstance(value,str) or _INTEGER.fullmatch(value) is None:raise FinancialCsvError("FINANCIAL_INTEGER_INVALID")
    return int(value)


def _time(value:str)->None:
    if not isinstance(value,str) or not value:raise FinancialCsvError("FINANCIAL_TIME_INVALID")
    normalized=value[:-1]+"+00:00" if value.endswith("Z") else value
    try:parsed=datetime.fromisoformat(normalized)
    except ValueError as exc:raise FinancialCsvError("FINANCIAL_TIME_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:raise FinancialCsvError("FINANCIAL_TIME_INVALID")


def _row_hash(row:dict[str,str])->str:
    payload=json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _unknown(fingerprint:dict[str,object],headers:tuple[str,...])->SchemaDetection:
    expected=set(HEADERS);actual=set(headers);diagnostics=[]
    missing=sorted(expected-actual);unexpected=sorted(actual-expected)
    if missing:diagnostics.append("missing_columns="+",".join(missing))
    if unexpected:diagnostics.append("unexpected_columns="+",".join(unexpected))
    if not missing and not unexpected and headers!=HEADERS:diagnostics.append("column_order_changed")
    if not diagnostics:diagnostics.append("no_registered_schema")
    return SchemaDetection("UNKNOWN",None,None,None,fingerprint,tuple(diagnostics))


def inspect_financial_csv(path:Path)->tuple[SchemaDetection,FinancialDataset|None]:
    fingerprint=structural_fingerprint(path)
    headers=tuple(fingerprint["descriptor"]["headers"])
    if headers!=HEADERS:return _unknown(fingerprint,headers),None
    try:
        with path.open("r",encoding="utf-8-sig",newline="") as handle:
            reader=csv.DictReader(handle)
            seen=set();currency=None;groups:dict[str,dict[str,object]]={};row_count=0
            for row in reader:
                row_count+=1
                if row_count>_MAX_ROWS:raise FinancialCsvError("FINANCIAL_ROW_LIMIT_EXCEEDED")
                if None in row or set(row)!=set(HEADERS):raise FinancialCsvError("FINANCIAL_ROW_MALFORMED")
                row_id=row["row_id"];product_id=row["product_id"]
                if not row_id or row_id in seen:raise FinancialCsvError("FINANCIAL_ROW_ID_INVALID")
                if not product_id:raise FinancialCsvError("FINANCIAL_PRODUCT_ID_INVALID")
                seen.add(row_id);_time(row["event_time"])
                current_currency=row["currency"]
                if _CURRENCY.fullmatch(current_currency or "") is None:raise FinancialCsvError("FINANCIAL_CURRENCY_INVALID")
                if currency is None:currency=current_currency
                elif currency!=current_currency:raise FinancialCsvError("FINANCIAL_CURRENCY_CONFLICT")
                gross=_integer(row["gross_sales_units"]);returned=_integer(row["returned_units"])
                money={field:_decimal(row[field]) for field in _MONEY_FIELDS}
                group=groups.setdefault(product_id,{"gross":0,"returned":0,"money":{field:Decimal("0") for field in _MONEY_FIELDS},"hashes":[]})
                group["gross"]+=gross;group["returned"]+=returned
                for field,value in money.items():group["money"][field]+=value
                group["hashes"].append(_row_hash(dict(row)))
        if row_count==0 or currency is None:raise FinancialCsvError("FINANCIAL_DATASET_EMPTY")
        products=[]
        for product_id in sorted(groups):
            group=groups[product_id];money=group["money"]
            products.append(ProductTotals(product_id,group["gross"],group["returned"],*(money[field] for field in _MONEY_FIELDS),currency,tuple(sorted(group["hashes"]))))
        detection=SchemaDetection("MATCHED",SCHEMA_ID,ADAPTER_ID,ADAPTER_VERSION,fingerprint,())
        return detection,FinancialDataset(SCHEMA_ID,ADAPTER_ID,ADAPTER_VERSION,currency,row_count,tuple(products))
    except (OSError,UnicodeError,csv.Error,FinancialCsvError) as exc:
        code=exc.code if isinstance(exc,FinancialCsvError) else "FINANCIAL_CSV_MALFORMED"
        return SchemaDetection("MALFORMED",None,None,None,fingerprint,(code,)),None
