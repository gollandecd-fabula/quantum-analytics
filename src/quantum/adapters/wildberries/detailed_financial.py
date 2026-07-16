from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re
from typing import Any


DETAILED_FINANCIAL_SCHEMA_VERSION = "quantum-wb-detailed-financial-v1"
DETAILED_FINANCIAL_SOURCE_TYPE = "WB_DETAILED_FINANCIAL"
_DECIMAL = re.compile(r"^[+-]?(?:0|[1-9][0-9]*)(?:[.,][0-9]+)?$")

_ALIASES: dict[str, tuple[str, ...]] = {
    "report_id": ("reportId", "realizationreport_id", "№ отчёта"),
    "row_id": ("rrdId", "rrd_id", "№ строки"),
    "date_from": ("dateFrom", "date_from", "Начало периода"),
    "date_to": ("dateTo", "date_to", "Конец периода"),
    "currency": ("currency", "currency_name", "Валюта"),
    "vendor_code": ("vendorCode", "sa_name", "Артикул"),
    "tech_size": ("techSize", "ts_name", "Размер"),
    "sku": ("sku", "barcode", "Баркод"),
    "doc_type": ("docTypeName", "doc_type_name", "Тип документа"),
    "operation": (
        "sellerOperName",
        "supplier_oper_name",
        "Обоснование",
        "Обоснование для оплаты",
    ),
    "quantity": ("quantity", "Кол-во"),
    "retail_amount": ("retailAmount", "retail_amount", "Продажи/возвраты, ₽"),
    "sales_commission": (
        "ppvzSalesCommission",
        "ppvz_sales_commission",
        "Комиссия WB, ₽",
    ),
    "for_pay": ("forPay", "ppvz_for_pay", "К перечислению продавцу, ₽"),
    "ppvz_reward": ("ppvzReward", "ppvz_reward", "ПВЗ, ₽"),
    "acquiring_fee": ("acquiringFee", "acquiring_fee", "Платёжные услуги, ₽"),
    "delivery_amount": ("deliveryAmount", "delivery_amount"),
    "return_amount": ("returnAmount", "return_amount"),
    "delivery_service": ("deliveryService", "delivery_rub", "Логистика, ₽"),
    "paid_storage": ("paidStorage", "storage_fee", "Хранение, ₽"),
    "penalty": ("penalty", "Штрафы, ₽"),
    "deduction": ("deduction", "Удержания, ₽"),
    "paid_acceptance": ("paidAcceptance", "acceptance", "Приёмка, ₽"),
    "rebill_logistic_cost": (
        "rebillLogisticCost",
        "rebill_logistic_cost",
        "Перевозка/склад, ₽",
    ),
    "additional_payment": (
        "additionalPayment",
        "additional_payment",
        "Корректировка WB, ₽",
    ),
    "order_dt": ("orderDt", "order_dt", "Дата заказа"),
    "sale_dt": ("saleDt", "sale_dt", "Дата продажи"),
    "srid": ("srid", "Srid"),
}

_OPERATION_TYPES = {
    "Продажа": "SALE",
    "Возврат": "RETURN",
    "Логистика": "LOGISTICS",
    "Коррекция логистики": "LOGISTICS_CORRECTION",
    "Обработка товара": "ACCEPTANCE_PROCESSING",
    "Хранение": "STORAGE",
    "Штраф": "PENALTY",
    "Удержание": "WITHHOLDING",
    "Возмещение издержек по перевозке/по складским операциям с товаром": (
        "WB_REIMBURSEMENT_ADJUSTMENT"
    ),
    "Возмещение за выдачу и возврат товаров на ПВЗ": (
        "PVZ_REIMBURSEMENT_ADJUSTMENT"
    ),
    "Компенсация скидки по программе лояльности": "LOYALTY_COMPENSATION",
    "Добровольная компенсация при возврате": "LOSS_COMPENSATION_CANDIDATE",
}


class WbDetailedFinancialError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise WbDetailedFinancialError("WB_DETAILED_JSON_INVALID") from exc


def _pick(row: Mapping[str, Any], field: str, *, required: bool) -> Any:
    found = [(alias, row[alias]) for alias in _ALIASES[field] if alias in row]
    if not found:
        if required:
            raise WbDetailedFinancialError(
                "WB_DETAILED_FIELD_REQUIRED:" + field
            )
        return None
    baseline = found[0][1]
    if any(value != baseline for _, value in found[1:]):
        raise WbDetailedFinancialError(
            "WB_DETAILED_ALIAS_CONFLICT:" + field
        )
    return baseline


def _text(value: Any, code: str, *, allow_empty: bool = False) -> str:
    if value is None:
        if allow_empty:
            return ""
        raise WbDetailedFinancialError(code)
    text = " ".join(str(value).replace("\u00a0", " ").split())
    if not text and not allow_empty:
        raise WbDetailedFinancialError(code)
    return text


def _decimal(value: Any, code: str, *, default_zero: bool = False) -> Decimal:
    if value is None or value == "":
        if default_zero:
            return Decimal("0")
        raise WbDetailedFinancialError(code)
    if isinstance(value, bool):
        raise WbDetailedFinancialError(code)
    text = str(value).replace("\u00a0", "").replace(" ", "").strip()
    if not _DECIMAL.fullmatch(text):
        raise WbDetailedFinancialError(code)
    try:
        parsed = Decimal(text.replace(",", "."))
    except InvalidOperation as exc:
        raise WbDetailedFinancialError(code) from exc
    if not parsed.is_finite():
        raise WbDetailedFinancialError(code)
    return parsed


def _nonnegative_integer(value: Any, code: str, *, default_zero: bool = False) -> int:
    parsed = _decimal(value, code, default_zero=default_zero)
    if parsed < 0 or parsed != parsed.to_integral_value():
        raise WbDetailedFinancialError(code)
    return int(parsed)


def _required_id(value: Any, code: str) -> str:
    if isinstance(value, bool):
        raise WbDetailedFinancialError(code)
    text = _text(value, code)
    if not re.fullmatch(r"[0-9]+", text):
        raise WbDetailedFinancialError(code)
    return text


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def _typed(
    state: str,
    value: str | int | None,
    *,
    value_type: str,
    unit: str,
    currency: str | None = None,
    reason_code: str | None = None,
    source_ids: Sequence[str] = (),
) -> dict[str, Any]:
    if state == "VALID":
        if value is None or reason_code is not None:
            raise WbDetailedFinancialError("WB_DETAILED_TYPED_VALUE_INVALID")
    else:
        if value is not None or not reason_code:
            raise WbDetailedFinancialError("WB_DETAILED_TYPED_VALUE_INVALID")
    return {
        "state": state,
        "value": None if value is None else str(value),
        "value_type": value_type,
        "unit": unit,
        "currency": currency,
        "reason_code": reason_code,
        "source_ids": list(source_ids),
    }


def _operation_type(doc_type: str, operation: str) -> str:
    result = _OPERATION_TYPES.get(operation)
    if result is None:
        raise WbDetailedFinancialError(
            "WB_DETAILED_OPERATION_UNSUPPORTED:" + operation
        )
    if result == "SALE" and doc_type != "Продажа":
        raise WbDetailedFinancialError("WB_DETAILED_SALE_DOCUMENT_MISMATCH")
    if result == "RETURN" and doc_type != "Возврат":
        raise WbDetailedFinancialError("WB_DETAILED_RETURN_DOCUMENT_MISMATCH")
    if result not in {"SALE", "RETURN"} and doc_type not in {"", "Продажа", "Возврат"}:
        raise WbDetailedFinancialError("WB_DETAILED_DOCUMENT_TYPE_UNSUPPORTED")
    return result


def _event_amount_sign(event_type: str) -> int:
    return -1 if event_type == "RETURN" else 1


def _component(row: Mapping[str, Any], field: str) -> Decimal:
    return _decimal(
        _pick(row, field, required=True),
        "WB_DETAILED_AMOUNT_INVALID:" + field,
    )


def _event_from_row(row: Mapping[str, Any], source_id: str) -> dict[str, Any]:
    report_id = _required_id(
        _pick(row, "report_id", required=True),
        "WB_DETAILED_REPORT_ID_INVALID",
    )
    row_id = _required_id(
        _pick(row, "row_id", required=True),
        "WB_DETAILED_ROW_ID_INVALID",
    )
    doc_type = _text(
        _pick(row, "doc_type", required=True),
        "WB_DETAILED_DOCUMENT_TYPE_INVALID",
        allow_empty=True,
    )
    operation = _text(
        _pick(row, "operation", required=True),
        "WB_DETAILED_OPERATION_REQUIRED",
    )
    event_type = _operation_type(doc_type, operation)
    currency_raw = _text(
        _pick(row, "currency", required=True),
        "WB_DETAILED_CURRENCY_INVALID",
    ).casefold().rstrip(".")
    if currency_raw not in {"rub", "руб"}:
        raise WbDetailedFinancialError("WB_DETAILED_CURRENCY_UNSUPPORTED")
    currency = "RUB"
    date_from = _text(
        _pick(row, "date_from", required=True),
        "WB_DETAILED_DATE_FROM_INVALID",
    )
    date_to = _text(
        _pick(row, "date_to", required=True),
        "WB_DETAILED_DATE_TO_INVALID",
    )
    quantity = _nonnegative_integer(
        _pick(row, "quantity", required=True),
        "WB_DETAILED_QUANTITY_INVALID",
    )
    if event_type in {"SALE", "RETURN"} and quantity < 1:
        raise WbDetailedFinancialError("WB_DETAILED_PHYSICAL_QUANTITY_REQUIRED")
    if event_type not in {"SALE", "RETURN"}:
        quantity = 0

    amounts = {
        field: _component(row, field)
        for field in (
            "retail_amount",
            "sales_commission",
            "for_pay",
            "ppvz_reward",
            "acquiring_fee",
            "delivery_service",
            "paid_storage",
            "penalty",
            "deduction",
            "paid_acceptance",
            "rebill_logistic_cost",
            "additional_payment",
        )
    }
    delivery_count = _nonnegative_integer(
        _pick(row, "delivery_amount", required=True),
        "WB_DETAILED_DELIVERY_COUNT_INVALID",
    )
    return_count = _nonnegative_integer(
        _pick(row, "return_amount", required=True),
        "WB_DETAILED_RETURN_COUNT_INVALID",
    )
    if delivery_count and return_count:
        raise WbDetailedFinancialError(
            "WB_DETAILED_LOGISTICS_DIRECTION_AMBIGUOUS"
        )
    logistics_direction = None
    if amounts["delivery_service"] != 0:
        if return_count:
            logistics_direction = "REVERSE"
        elif delivery_count:
            logistics_direction = "FORWARD"
        elif event_type == "LOGISTICS_CORRECTION":
            logistics_direction = "CORRECTION_UNCLASSIFIED"
        else:
            logistics_direction = "UNCLASSIFIED"

    vendor_code = _text(
        _pick(row, "vendor_code", required=False),
        "WB_DETAILED_VENDOR_CODE_INVALID",
        allow_empty=True,
    )
    tech_size = _text(
        _pick(row, "tech_size", required=False),
        "WB_DETAILED_TECH_SIZE_INVALID",
        allow_empty=True,
    )
    sku = _text(
        _pick(row, "sku", required=False),
        "WB_DETAILED_SKU_INVALID",
        allow_empty=True,
    )
    order_dt = _text(
        _pick(row, "order_dt", required=False),
        "WB_DETAILED_ORDER_DATE_INVALID",
        allow_empty=True,
    )
    sale_dt = _text(
        _pick(row, "sale_dt", required=False),
        "WB_DETAILED_SALE_DATE_INVALID",
        allow_empty=True,
    )
    srid = _text(
        _pick(row, "srid", required=False),
        "WB_DETAILED_SRID_INVALID",
        allow_empty=True,
    )

    identity = {
        "report_id": report_id,
        "row_id": row_id,
        "date_from": date_from,
        "date_to": date_to,
        "event_type": event_type,
        "operation": operation,
        "doc_type": doc_type,
        "vendor_code": vendor_code,
        "tech_size": tech_size,
        "sku": sku,
        "order_dt": order_dt,
        "sale_dt": sale_dt,
        "quantity": quantity,
        "amounts": {key: str(value) for key, value in amounts.items()},
        "delivery_count": delivery_count,
        "return_count": return_count,
        "srid": srid,
    }
    event_id = "wb-fin-" + sha256(_canonical_json(identity)).hexdigest()
    return {
        "event_id": event_id,
        "source_id": source_id,
        "report_id": report_id,
        "row_id": row_id,
        "date_from": date_from,
        "date_to": date_to,
        "event_type": event_type,
        "operation": operation,
        "doc_type": doc_type,
        "vendor_code": vendor_code,
        "tech_size": tech_size,
        "sku": sku,
        "order_dt": order_dt,
        "sale_dt": sale_dt,
        "quantity": quantity,
        "amounts": amounts,
        "delivery_count": delivery_count,
        "return_count": return_count,
        "logistics_direction": logistics_direction,
        "srid": srid,
    }


def normalize_detailed_financial_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    source_id: str,
    source_sha256: str,
) -> dict[str, Any]:
    """Normalize admitted WB detailed-financial rows into a canonical ledger."""
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)) or not rows:
        raise WbDetailedFinancialError("WB_DETAILED_ROWS_REQUIRED")
    source_id = _text(source_id, "WB_DETAILED_SOURCE_ID_INVALID")
    if not isinstance(source_sha256, str) or not re.fullmatch(
        r"[0-9a-f]{64}", source_sha256
    ):
        raise WbDetailedFinancialError("WB_DETAILED_SOURCE_SHA256_INVALID")

    events: list[dict[str, Any]] = []
    seen: set[str] = set()
    report_ids: set[str] = set()
    report_periods: dict[str, tuple[str, str]] = {}
    gross_sales_units = 0
    returned_units = 0
    gross_sales_amount = Decimal("0")
    marketplace_commission = Decimal("0")
    forward_logistics = Decimal("0")
    reverse_logistics = Decimal("0")
    storage = Decimal("0")
    fines_withholdings = Decimal("0")
    payout = Decimal("0")
    unsupported_acceptance = Decimal("0")
    unsupported_rebill = Decimal("0")
    unclassified_logistics = Decimal("0")
    unsupported_additional_payment = Decimal("0")

    for raw in rows:
        if not isinstance(raw, Mapping):
            raise WbDetailedFinancialError("WB_DETAILED_ROW_INVALID")
        event = _event_from_row(raw, source_id)
        if event["event_id"] in seen:
            raise WbDetailedFinancialError("WB_DETAILED_EVENT_DUPLICATE")
        seen.add(event["event_id"])
        events.append(event)
        report_id = event["report_id"]
        report_ids.add(report_id)
        period = (event["date_from"], event["date_to"])
        previous_period = report_periods.setdefault(report_id, period)
        if previous_period != period:
            raise WbDetailedFinancialError(
                "WB_DETAILED_REPORT_PERIOD_CONFLICT"
            )
        event_type = event["event_type"]
        sign = _event_amount_sign(event_type)
        quantity = event["quantity"]
        amounts = event["amounts"]

        if event_type == "SALE":
            gross_sales_units += quantity
            gross_sales_amount += abs(amounts["retail_amount"])
        elif event_type == "RETURN":
            returned_units += quantity
            gross_sales_amount -= abs(amounts["retail_amount"])

        settlement_fees = (
            abs(amounts["sales_commission"])
            + abs(amounts["acquiring_fee"])
            + abs(amounts["ppvz_reward"])
        )
        if event_type in {"SALE", "RETURN"}:
            marketplace_commission += Decimal(sign) * settlement_fees
            payout += Decimal(sign) * abs(amounts["for_pay"])
        else:
            marketplace_commission += (
                amounts["sales_commission"]
                + amounts["acquiring_fee"]
                + amounts["ppvz_reward"]
            )
            payout += amounts["for_pay"]
        direction = event["logistics_direction"]
        if direction == "FORWARD":
            forward_logistics += amounts["delivery_service"]
        elif direction == "REVERSE":
            reverse_logistics += amounts["delivery_service"]
        elif direction in {"UNCLASSIFIED", "CORRECTION_UNCLASSIFIED"}:
            unclassified_logistics += amounts["delivery_service"]
        storage += amounts["paid_storage"]
        fines_withholdings += amounts["penalty"] + amounts["deduction"]
        unsupported_acceptance += amounts["paid_acceptance"]
        unsupported_rebill += amounts["rebill_logistic_cost"]
        unsupported_additional_payment += amounts["additional_payment"]

    magnitude_totals = {
        "gross_sales_amount": gross_sales_amount,
        "marketplace_commission_amount": marketplace_commission,
        "forward_logistics_amount": forward_logistics,
        "reverse_logistics_amount": reverse_logistics,
        "storage_amount": storage,
        "fines_withholdings_amount": fines_withholdings,
    }
    for metric_id, value in magnitude_totals.items():
        if value < 0:
            raise WbDetailedFinancialError(
                "WB_DETAILED_NEGATIVE_AGGREGATE:" + metric_id
            )
    event_ids = sorted(event["event_id"] for event in events)
    ledger_sha256 = sha256(_canonical_json(event_ids)).hexdigest()
    evidence = (
        source_id,
        "source-sha256:" + source_sha256,
        "ledger-sha256:" + ledger_sha256,
    )

    observed_metrics = {
        "gross_sales_units": _typed(
            "VALID",
            gross_sales_units,
            value_type="INTEGER",
            unit="ITEM",
            source_ids=evidence,
        ),
        "returned_units": _typed(
            "VALID",
            returned_units,
            value_type="INTEGER",
            unit="ITEM",
            source_ids=evidence,
        ),
        "gross_sales_amount": _typed(
            "VALID",
            _money(gross_sales_amount),
            value_type="MONEY",
            unit="MONEY",
            currency="RUB",
            source_ids=evidence,
        ),
        "marketplace_commission_amount": _typed(
            "VALID",
            _money(marketplace_commission),
            value_type="MONEY",
            unit="MONEY",
            currency="RUB",
            source_ids=evidence,
        ),
        "forward_logistics_amount": _typed(
            "VALID",
            _money(forward_logistics),
            value_type="MONEY",
            unit="MONEY",
            currency="RUB",
            source_ids=evidence,
        ),
        "reverse_logistics_amount": _typed(
            "VALID",
            _money(reverse_logistics),
            value_type="MONEY",
            unit="MONEY",
            currency="RUB",
            source_ids=evidence,
        ),
        "storage_amount": _typed(
            "VALID",
            _money(storage),
            value_type="MONEY",
            unit="MONEY",
            currency="RUB",
            source_ids=evidence,
        ),
        "fines_withholdings_amount": _typed(
            "VALID",
            _money(fines_withholdings),
            value_type="MONEY",
            unit="MONEY",
            currency="RUB",
            source_ids=evidence,
        ),
        "payout_amount": _typed(
            "VALID",
            _money(payout),
            value_type="MONEY",
            unit="MONEY",
            currency="RUB",
            source_ids=evidence,
        ),
    }

    blockers: list[str] = []
    if unclassified_logistics != 0:
        blockers.append("LOGISTICS_DIRECTION_UNCLASSIFIED")
    if unsupported_acceptance != 0:
        blockers.append("PAID_ACCEPTANCE_OUTSIDE_KERNEL_EXPENSE_BOUNDARY")
    if unsupported_rebill != 0:
        blockers.append("REBILL_LOGISTICS_OUTSIDE_APPROVED_MAPPING")
    if unsupported_additional_payment != 0:
        blockers.append("ADDITIONAL_PAYMENT_CLASSIFICATION_REQUIRED")
    blockers.extend(
        [
            "RETURN_TREATMENT_INPUT_REQUIRED",
            "RETURN_COMPENSATION_CLASSIFICATION_REQUIRED",
            "DISCOUNTS_SOURCE_OR_EXPLICIT_ZERO_REQUIRED",
            "SUBSIDIES_SOURCE_OR_EXPLICIT_ZERO_REQUIRED",
            "ADVERTISING_SOURCE_OR_EXPLICIT_ZERO_REQUIRED",
            "CALCULATION_PROFILE_REQUIRED",
        ]
    )
    return {
        "schema_version": DETAILED_FINANCIAL_SCHEMA_VERSION,
        "status": "SOURCE_BRIDGE_COMPLETE",
        "source_type": DETAILED_FINANCIAL_SOURCE_TYPE,
        "source_id": source_id,
        "source_sha256": source_sha256,
        "report_ids": sorted(report_ids),
        "report_periods": {
            report_id: {
                "date_from": period[0],
                "date_to": period[1],
            }
            for report_id, period in sorted(report_periods.items())
        },
        "event_count": len(events),
        "canonical_ledger_sha256": ledger_sha256,
        "observed_metrics": observed_metrics,
        "unsupported_components": {
            "paid_acceptance_amount": _money(unsupported_acceptance),
            "rebill_logistic_cost_amount": _money(unsupported_rebill),
            "unclassified_logistics_amount": _money(unclassified_logistics),
            "additional_payment_amount": _money(
                unsupported_additional_payment
            ),
        },
        "kernel_inputs": {
            **observed_metrics,
            "resalable_returned_units": _typed(
                "BLOCKED",
                None,
                value_type="INTEGER",
                unit="ITEM",
                reason_code="RETURN_TREATMENT_INPUT_REQUIRED",
                source_ids=evidence,
            ),
            "compensated_returned_units": _typed(
                "BLOCKED",
                None,
                value_type="INTEGER",
                unit="ITEM",
                reason_code="RETURN_TREATMENT_INPUT_REQUIRED",
                source_ids=evidence,
            ),
            "return_compensation_amount": _typed(
                "BLOCKED",
                None,
                value_type="MONEY",
                unit="MONEY",
                currency="RUB",
                reason_code="RETURN_COMPENSATION_CLASSIFICATION_REQUIRED",
                source_ids=evidence,
            ),
            "discounts_amount": _typed(
                "BLOCKED",
                None,
                value_type="MONEY",
                unit="MONEY",
                currency="RUB",
                reason_code="DISCOUNTS_SOURCE_OR_EXPLICIT_ZERO_REQUIRED",
                source_ids=evidence,
            ),
            "subsidies_excluding_return_compensation_amount": _typed(
                "BLOCKED",
                None,
                value_type="MONEY",
                unit="MONEY",
                currency="RUB",
                reason_code="SUBSIDIES_SOURCE_OR_EXPLICIT_ZERO_REQUIRED",
                source_ids=evidence,
            ),
            "advertising_amount": _typed(
                "BLOCKED",
                None,
                value_type="MONEY",
                unit="MONEY",
                currency="RUB",
                reason_code="ADVERTISING_SOURCE_OR_EXPLICIT_ZERO_REQUIRED",
                source_ids=evidence,
            ),
        },
        "finance_request": None,
        "finance_request_state": "BLOCKED",
        "finance_request_reason_codes": blockers,
        "limitations": [
            "SRID_NOT_USED_AS_UNIQUE_EVENT_ID",
            "SALE_RETURN_DIRECTION_FROM_DOCUMENT_AND_OPERATION",
            "RAW_ROWS_NOT_EXPOSED",
            "NO_MISSING_TO_ZERO_FOR_REQUIRED_FIELDS",
        ],
        "raw_rows_in_report": False,
    }
