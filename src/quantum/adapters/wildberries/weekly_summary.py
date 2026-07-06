from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re
from typing import Any

from quantum.ingestion import XlsxInspectionLimits
from quantum.ingestion._xlsx_contracts import normalized_header_sha256

from .source_bridge import WbSourceBridgeError, _sheet_rows


WEEKLY_SUMMARY_SCHEMA_VERSION = "quantum-wb-weekly-summary-v1"
WEEKLY_SUMMARY_SOURCE_TYPE = "WB_WEEKLY_SUMMARY"
EXPECTED_WEEKLY_SUMMARY_HEADERS = (
    "№ отчета",
    "Юридическое лицо",
    "Дата начала",
    "Дата конца",
    "Дата формирования",
    "Тип отчета",
    "Продажа",
    "В том числе компенсация скидки по программе лояльности",
    "К перечислению за товар",
    "Согласованная скидка, %",
    "Стоимость логистики",
    "Стоимость хранения",
    "Стоимость операций на приемке",
    "Прочие удержания/выплаты",
    "Общая сумма штрафов",
    "Корректировка Вознаграждения Вайлдберриз (ВВ)",
    "Стоимость участия в программе лояльности",
    "Сумма баллов, удержанных по программе лояльности",
    "Разовое изменение срока перечисления денежных средств",
    "Итого к оплате",
    "Валюта",
)
EXPECTED_WEEKLY_SUMMARY_HEADER_SHA256 = (
    "729a36febccee863448036974fcf34ff919c21955ebe442a25fea0e67b256134"
)
_DECIMAL = re.compile(r"^[+-]?(?:0|[1-9][0-9]*)(?:[.,][0-9]+)?$")
_REPORT_ID = re.compile(r"^[0-9]+$")
_MONEY_FIELDS = {
    "gross_sales_amount": "Продажа",
    "loyalty_compensation_amount": (
        "В том числе компенсация скидки по программе лояльности"
    ),
    "goods_payable_amount": "К перечислению за товар",
    "total_logistics_amount": "Стоимость логистики",
    "storage_amount": "Стоимость хранения",
    "paid_acceptance_amount": "Стоимость операций на приемке",
    "other_withholdings_payments_amount": "Прочие удержания/выплаты",
    "fines_amount": "Общая сумма штрафов",
    "wb_reward_adjustment_amount": (
        "Корректировка Вознаграждения Вайлдберриз (ВВ)"
    ),
    "loyalty_program_cost_amount": (
        "Стоимость участия в программе лояльности"
    ),
    "loyalty_points_withheld_amount": (
        "Сумма баллов, удержанных по программе лояльности"
    ),
    "payment_term_change_amount": (
        "Разовое изменение срока перечисления денежных средств"
    ),
    "payout_amount": "Итого к оплате",
}


class WbWeeklySummaryError(ValueError):
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
        raise WbWeeklySummaryError("WB_WEEKLY_JSON_INVALID") from exc


def _text(value: object, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WbWeeklySummaryError(code)
    return " ".join(value.replace("\u00a0", " ").split())


def _positive_int(value: object, code: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise WbWeeklySummaryError(code)
    return value


def _decimal(value: object, code: str, *, allow_empty: bool = False) -> Decimal:
    if not isinstance(value, str):
        raise WbWeeklySummaryError(code)
    normalized = value.replace("\u00a0", "").replace(" ", "").strip()
    if not normalized:
        if allow_empty:
            return Decimal("0")
        raise WbWeeklySummaryError(code)
    if not _DECIMAL.fullmatch(normalized):
        raise WbWeeklySummaryError(code)
    try:
        parsed = Decimal(normalized.replace(",", "."))
    except InvalidOperation as exc:
        raise WbWeeklySummaryError(code) from exc
    if not parsed.is_finite():
        raise WbWeeklySummaryError(code)
    return parsed


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def _typed_money(value: Decimal, source_ids: Sequence[str]) -> dict[str, Any]:
    return {
        "state": "VALID",
        "value": _money(value),
        "value_type": "MONEY",
        "unit": "MONEY",
        "currency": "RUB",
        "reason_code": None,
        "source_ids": list(source_ids),
    }


def _typed_integer(value: int, source_ids: Sequence[str]) -> dict[str, Any]:
    return {
        "state": "VALID",
        "value": str(value),
        "value_type": "INTEGER",
        "unit": "COUNT",
        "currency": None,
        "reason_code": None,
        "source_ids": list(source_ids),
    }


def _header_row(
    rows: list[tuple[int, tuple[str, ...]]],
    header_row_index: int,
) -> tuple[str, ...]:
    matches = [values for index, values in rows if index == header_row_index]
    if len(matches) != 1:
        raise WbWeeklySummaryError("WB_WEEKLY_HEADER_ROW_NOT_UNIQUE")
    headers = matches[0]
    if headers != EXPECTED_WEEKLY_SUMMARY_HEADERS:
        raise WbWeeklySummaryError("WB_WEEKLY_HEADERS_UNSUPPORTED")
    if normalized_header_sha256(headers) != EXPECTED_WEEKLY_SUMMARY_HEADER_SHA256:
        raise WbWeeklySummaryError("WB_WEEKLY_HEADER_HASH_MISMATCH")
    return headers


def bridge_weekly_summary_xlsx(
    *,
    payload: bytes,
    schema_discovery: Mapping[str, Any],
    limits: XlsxInspectionLimits,
    source_id: str,
    source_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract direct WB weekly-summary aggregates without inventing finance inputs."""
    if not isinstance(payload, bytes) or not payload:
        raise WbWeeklySummaryError("WB_WEEKLY_PAYLOAD_REQUIRED")
    if not isinstance(schema_discovery, Mapping):
        raise WbWeeklySummaryError("WB_WEEKLY_SCHEMA_DISCOVERY_REQUIRED")
    if not isinstance(limits, XlsxInspectionLimits):
        raise WbWeeklySummaryError("WB_WEEKLY_LIMITS_INVALID")
    source_id = _text(source_id, "WB_WEEKLY_SOURCE_ID_INVALID")
    sheet_name = _text(
        schema_discovery.get("sheet_name"),
        "WB_WEEKLY_SHEET_NAME_INVALID",
    )
    header_row_index = _positive_int(
        schema_discovery.get("header_row_index"),
        "WB_WEEKLY_HEADER_ROW_INDEX_INVALID",
    )
    raw_headers = schema_discovery.get("headers")
    if not isinstance(raw_headers, list) or any(
        not isinstance(item, str) for item in raw_headers
    ):
        raise WbWeeklySummaryError("WB_WEEKLY_HEADERS_INVALID")
    headers = tuple(raw_headers)
    claimed_hash = _text(
        schema_discovery.get("header_sha256"),
        "WB_WEEKLY_HEADER_HASH_INVALID",
    )
    if normalized_header_sha256(headers) != claimed_hash:
        raise WbWeeklySummaryError("WB_WEEKLY_DISCOVERY_HASH_MISMATCH")
    if (
        headers != EXPECTED_WEEKLY_SUMMARY_HEADERS
        or claimed_hash != EXPECTED_WEEKLY_SUMMARY_HEADER_SHA256
    ):
        raise WbWeeklySummaryError("WB_WEEKLY_SCHEMA_UNSUPPORTED")

    expected_row_count = schema_discovery.get("data_row_count")
    if (
        not isinstance(expected_row_count, int)
        or isinstance(expected_row_count, bool)
        or expected_row_count < 0
    ):
        raise WbWeeklySummaryError("WB_WEEKLY_ROW_COUNT_INVALID")

    rows = _sheet_rows(payload, sheet_name=sheet_name, limits=limits)
    _header_row(rows, header_row_index)
    data_rows = [
        (index, values)
        for index, values in rows
        if index > header_row_index and any(value.strip() for value in values)
    ]
    if len(data_rows) != expected_row_count:
        raise WbWeeklySummaryError("WB_WEEKLY_ROW_COUNT_MISMATCH")
    if not data_rows:
        raise WbWeeklySummaryError("WB_WEEKLY_ROWS_REQUIRED")

    totals = {metric_id: Decimal("0") for metric_id in _MONEY_FIELDS}
    report_ids: set[str] = set()
    report_types: set[str] = set()
    periods: set[tuple[str, str]] = set()
    legal_entity_hashes: set[str] = set()
    currencies: set[str] = set()
    row_hashes: list[str] = []
    blank_money_cells = 0

    for row_index, values in data_rows:
        padded = values + ("",) * (len(headers) - len(values))
        if len(padded) != len(headers):
            raise WbWeeklySummaryError("WB_WEEKLY_COLUMN_COUNT_INVALID")
        row = dict(zip(headers, padded, strict=True))
        report_id = _text(row["№ отчета"], "WB_WEEKLY_REPORT_ID_REQUIRED")
        if not _REPORT_ID.fullmatch(report_id):
            raise WbWeeklySummaryError("WB_WEEKLY_REPORT_ID_INVALID")
        date_from = _text(row["Дата начала"], "WB_WEEKLY_DATE_FROM_REQUIRED")
        date_to = _text(row["Дата конца"], "WB_WEEKLY_DATE_TO_REQUIRED")
        report_type = _text(row["Тип отчета"], "WB_WEEKLY_REPORT_TYPE_REQUIRED")
        legal_entity = _text(
            row["Юридическое лицо"],
            "WB_WEEKLY_LEGAL_ENTITY_REQUIRED",
        )
        currency = _text(row["Валюта"], "WB_WEEKLY_CURRENCY_REQUIRED").upper()
        if currency not in {"RUB", "RUR", "РУБ"}:
            raise WbWeeklySummaryError("WB_WEEKLY_CURRENCY_UNSUPPORTED")
        currency = "RUB"

        amounts: dict[str, str] = {}
        for metric_id, header in _MONEY_FIELDS.items():
            raw_value = row[header]
            if not raw_value.strip():
                blank_money_cells += 1
            amount = _decimal(
                raw_value,
                "WB_WEEKLY_AMOUNT_INVALID:" + metric_id,
                allow_empty=True,
            )
            totals[metric_id] += amount
            amounts[metric_id] = _money(amount)

        discount = _decimal(
            row["Согласованная скидка, %"],
            "WB_WEEKLY_DISCOUNT_INVALID",
            allow_empty=True,
        )
        if discount < 0 or discount > 100:
            raise WbWeeklySummaryError("WB_WEEKLY_DISCOUNT_OUT_OF_RANGE")

        report_ids.add(report_id)
        report_types.add(report_type)
        periods.add((date_from, date_to))
        currencies.add(currency)
        legal_entity_hashes.add(sha256(legal_entity.encode("utf-8")).hexdigest())
        canonical_row = {
            "row_index": row_index,
            "report_id": report_id,
            "date_from": date_from,
            "date_to": date_to,
            "report_type": report_type,
            "currency": currency,
            "amounts": amounts,
            "agreed_discount_percent": format(discount, "f"),
        }
        row_hashes.append(sha256(_canonical_json(canonical_row)).hexdigest())

    if currencies != {"RUB"}:
        raise WbWeeklySummaryError("WB_WEEKLY_CURRENCY_CONFLICT")
    source_sha256 = sha256(payload).hexdigest()
    ledger_sha256 = sha256(_canonical_json(sorted(row_hashes))).hexdigest()
    evidence = (
        source_id,
        "source-sha256:" + source_sha256,
        "weekly-ledger-sha256:" + ledger_sha256,
    )
    observed_metrics = {
        metric_id: _typed_money(value, evidence)
        for metric_id, value in totals.items()
    }
    observed_metrics["report_count"] = _typed_integer(len(report_ids), evidence)

    blockers = [
        "SOLD_UNITS_SOURCE_REQUIRED",
        "RETURN_EVENTS_SOURCE_REQUIRED",
        "PRODUCT_COST_PROFILE_REQUIRED",
        "TAX_PROFILE_REQUIRED",
        "OTHER_EXPENSE_PROFILE_REQUIRED",
        "ADVERTISING_SOURCE_OR_EXPLICIT_ZERO_REQUIRED",
        "MARKETPLACE_COMMISSION_NOT_SEPARATELY_REPORTED",
        "LOGISTICS_DIRECTION_NOT_AVAILABLE",
        "SIGNED_ADJUSTMENT_CLASSIFICATION_REQUIRED",
        "CALCULATION_PROFILE_REQUIRED",
    ]
    limitations = [
        "AGGREGATED_WEEKLY_SOURCE_NOT_EVENT_LEDGER",
        "RAW_ROWS_NOT_EXPOSED",
        "NO_NET_PROFIT_WITHOUT_EXPLICIT_COST_AND_TAX_INPUTS",
        "ADJUSTMENTS_PRESERVED_AS_SEPARATE_SIGNED_METRICS",
    ]
    if blank_money_cells:
        limitations.append("BLANK_MONETARY_CELLS_RECORDED_AS_SOURCE_ZERO")

    return {
        "schema_version": WEEKLY_SUMMARY_SCHEMA_VERSION,
        "status": "SOURCE_BRIDGE_COMPLETE",
        "source_type": WEEKLY_SUMMARY_SOURCE_TYPE,
        "source_id": source_id,
        "source_sha256": source_sha256,
        "sheet_name": sheet_name,
        "header_row_index": header_row_index,
        "header_sha256": EXPECTED_WEEKLY_SUMMARY_HEADER_SHA256,
        "row_count": len(data_rows),
        "report_ids": sorted(report_ids),
        "report_types": sorted(report_types),
        "periods": [
            {"date_from": date_from, "date_to": date_to}
            for date_from, date_to in sorted(periods)
        ],
        "currency": "RUB",
        "legal_entity_count": len(legal_entity_hashes),
        "canonical_ledger_sha256": ledger_sha256,
        "observed_metrics": observed_metrics,
        "finance_request": None,
        "finance_request_state": "BLOCKED",
        "finance_request_reason_codes": blockers,
        "diagnostics": [],
        "limitations": limitations,
        "blank_money_cell_count": blank_money_cells,
        "source_context": dict(source_context) if source_context else None,
        "raw_rows_in_report": False,
    }


__all__ = [
    "EXPECTED_WEEKLY_SUMMARY_HEADERS",
    "EXPECTED_WEEKLY_SUMMARY_HEADER_SHA256",
    "WEEKLY_SUMMARY_SOURCE_TYPE",
    "WbWeeklySummaryError",
    "bridge_weekly_summary_xlsx",
]
