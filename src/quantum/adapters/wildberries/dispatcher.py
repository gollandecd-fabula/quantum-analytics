from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quantum.ingestion import XlsxInspectionLimits
from quantum.ingestion._xlsx_contracts import XlsxInspectionError

from .detailed_financial import (
    WbDetailedFinancialError,
    _ALIASES,
)
from .detailed_xlsx import (
    WbDetailedXlsxError,
    bridge_detailed_financial_xlsx,
)
from .source_bridge import (
    WbSourceBridgeError,
    bridge_admitted_xlsx,
)


DISPATCH_SCHEMA_VERSION = "quantum-wb-source-dispatch-v1"
_SUPPLIER_GOODS_HEADER_SHA256 = (
    "8253be37c607a7881ad7f4c028f05c347f17ee1b88fd28c65a08b5e24ed51313"
)
_DETAILED_REQUIRED_HEADER_FIELDS = (
    "doc_type",
    "operation",
    "quantity",
    "retail_amount",
    "sales_commission",
    "for_pay",
    "ppvz_reward",
    "acquiring_fee",
    "delivery_amount",
    "return_amount",
    "delivery_service",
    "paid_storage",
    "penalty",
    "deduction",
    "paid_acceptance",
    "rebill_logistic_cost",
    "additional_payment",
)


class WbSourceDispatchError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _headers(schema_discovery: Mapping[str, Any]) -> tuple[str, ...]:
    raw = schema_discovery.get("headers")
    if (
        not isinstance(raw, list)
        or not raw
        or any(not isinstance(item, str) or not item.strip() for item in raw)
    ):
        raise WbSourceDispatchError("WB_DISPATCH_HEADERS_INVALID")
    return tuple(raw)


def _normalized_headers(headers: tuple[str, ...]) -> set[str]:
    return {" ".join(item.split()).casefold() for item in headers}


def _matches_aliases(headers: set[str], field: str) -> bool:
    return any(
        " ".join(alias.split()).casefold() in headers
        for alias in _ALIASES[field]
    )


def _blocked_result(
    *,
    status: str,
    reason_code: str,
    schema_discovery: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": DISPATCH_SCHEMA_VERSION,
        "status": status,
        "header_sha256": schema_discovery.get("header_sha256"),
        "column_count": schema_discovery.get("column_count"),
        "data_row_count": schema_discovery.get("data_row_count"),
        "finance_request": None,
        "finance_request_state": "BLOCKED",
        "finance_request_reason_codes": [reason_code],
        "raw_rows_in_report": False,
    }


def bridge_reviewed_wb_source(
    *,
    payload: bytes,
    schema_discovery: Mapping[str, Any],
    limits: XlsxInspectionLimits,
    source_id: str,
    source_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Route one reviewed and admitted WB workbook without guessing a schema."""
    if not isinstance(schema_discovery, Mapping):
        raise WbSourceDispatchError("WB_DISPATCH_SCHEMA_DISCOVERY_REQUIRED")
    headers = _headers(schema_discovery)
    header_sha256 = schema_discovery.get("header_sha256")
    if header_sha256 == _SUPPLIER_GOODS_HEADER_SHA256:
        try:
            result = bridge_admitted_xlsx(
                payload=payload,
                schema_discovery=schema_discovery,
                limits=limits,
            )
        except (WbSourceBridgeError, XlsxInspectionError) as exc:
            return _blocked_result(
                status="SOURCE_BRIDGE_BLOCKED",
                reason_code=getattr(exc, "code", type(exc).__name__),
                schema_discovery=schema_discovery,
            )
        result["dispatch_schema_version"] = DISPATCH_SCHEMA_VERSION
        return result

    normalized = _normalized_headers(headers)
    if all(
        _matches_aliases(normalized, field)
        for field in _DETAILED_REQUIRED_HEADER_FIELDS
    ):
        try:
            result = bridge_detailed_financial_xlsx(
                payload=payload,
                schema_discovery=schema_discovery,
                limits=limits,
                source_id=source_id,
                source_context=source_context,
            )
        except (
            WbDetailedFinancialError,
            WbDetailedXlsxError,
            WbSourceBridgeError,
            XlsxInspectionError,
        ) as exc:
            return _blocked_result(
                status="SOURCE_BRIDGE_BLOCKED",
                reason_code=getattr(exc, "code", type(exc).__name__),
                schema_discovery=schema_discovery,
            )
        result["dispatch_schema_version"] = DISPATCH_SCHEMA_VERSION
        return result

    return _blocked_result(
        status="SOURCE_BRIDGE_UNSUPPORTED",
        reason_code="WB_SCHEMA_NOT_MAPPED",
        schema_discovery=schema_discovery,
    )
