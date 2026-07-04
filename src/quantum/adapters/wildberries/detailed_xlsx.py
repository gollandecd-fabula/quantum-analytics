from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from typing import Any

from quantum.ingestion import XlsxInspectionLimits
from quantum.ingestion._xlsx_contracts import normalized_header_sha256

from .detailed_financial import normalize_detailed_financial_rows
from .source_bridge import WbSourceBridgeError, _sheet_rows


DETAILED_XLSX_SCHEMA_VERSION = "quantum-wb-detailed-xlsx-v1"


class WbDetailedXlsxError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _text(value: object, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WbDetailedXlsxError(code)
    return value.strip()


def _positive_int(value: object, code: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise WbDetailedXlsxError(code)
    return value


def _nonnegative_int(value: object, code: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise WbDetailedXlsxError(code)
    return value


def _headers(raw: object) -> tuple[str, ...]:
    if (
        not isinstance(raw, list)
        or not raw
        or any(not isinstance(item, str) or not item.strip() for item in raw)
    ):
        raise WbDetailedXlsxError("WB_DETAILED_XLSX_HEADERS_INVALID")
    headers = tuple(raw)
    normalized = tuple(" ".join(item.split()).casefold() for item in headers)
    if len(set(normalized)) != len(normalized):
        raise WbDetailedXlsxError("WB_DETAILED_XLSX_HEADERS_DUPLICATE")
    return headers


def _read_bound_rows(
    *,
    payload: bytes,
    schema_discovery: Mapping[str, Any],
    limits: XlsxInspectionLimits,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    if not isinstance(payload, bytes) or not payload:
        raise WbDetailedXlsxError("WB_DETAILED_XLSX_PAYLOAD_REQUIRED")
    if not isinstance(schema_discovery, Mapping):
        raise WbDetailedXlsxError(
            "WB_DETAILED_XLSX_SCHEMA_DISCOVERY_REQUIRED"
        )
    if not isinstance(limits, XlsxInspectionLimits):
        raise WbDetailedXlsxError("WB_DETAILED_XLSX_LIMITS_INVALID")

    sheet_name = _text(
        schema_discovery.get("sheet_name"),
        "WB_DETAILED_XLSX_SHEET_NAME_INVALID",
    )
    header_row_index = _positive_int(
        schema_discovery.get("header_row_index"),
        "WB_DETAILED_XLSX_HEADER_ROW_INVALID",
    )
    headers = _headers(schema_discovery.get("headers"))
    claimed_hash = _text(
        schema_discovery.get("header_sha256"),
        "WB_DETAILED_XLSX_HEADER_HASH_INVALID",
    )
    if normalized_header_sha256(headers) != claimed_hash:
        raise WbDetailedXlsxError(
            "WB_DETAILED_XLSX_DISCOVERY_HASH_MISMATCH"
        )
    expected_columns = schema_discovery.get("column_count", len(headers))
    expected_columns = _positive_int(
        expected_columns,
        "WB_DETAILED_XLSX_COLUMN_COUNT_INVALID",
    )
    if expected_columns != len(headers):
        raise WbDetailedXlsxError(
            "WB_DETAILED_XLSX_COLUMN_COUNT_MISMATCH"
        )
    expected_rows_raw = schema_discovery.get("data_row_count")
    expected_rows = None
    if expected_rows_raw is not None:
        expected_rows = _nonnegative_int(
            expected_rows_raw,
            "WB_DETAILED_XLSX_ROW_COUNT_INVALID",
        )

    try:
        parsed_rows = _sheet_rows(
            payload,
            sheet_name=sheet_name,
            limits=limits,
        )
    except WbSourceBridgeError as exc:
        raise WbDetailedXlsxError(
            "WB_DETAILED_XLSX_PARSE_FAILED:" + exc.code
        ) from exc

    header_matches = [
        values for row_index, values in parsed_rows
        if row_index == header_row_index
    ]
    if len(header_matches) != 1:
        raise WbDetailedXlsxError(
            "WB_DETAILED_XLSX_HEADER_ROW_NOT_UNIQUE"
        )
    actual_headers = header_matches[0]
    if actual_headers != headers:
        raise WbDetailedXlsxError("WB_DETAILED_XLSX_HEADER_CHANGED")
    if normalized_header_sha256(actual_headers) != claimed_hash:
        raise WbDetailedXlsxError("WB_DETAILED_XLSX_HEADER_HASH_MISMATCH")

    rows: list[dict[str, str]] = []
    row_numbers: list[int] = []
    for row_index, values in parsed_rows:
        if row_index <= header_row_index or not any(
            value.strip() for value in values
        ):
            continue
        if len(values) > len(headers):
            raise WbDetailedXlsxError(
                "WB_DETAILED_XLSX_DATA_COLUMN_OVERFLOW"
            )
        padded = values + ("",) * (len(headers) - len(values))
        rows.append(dict(zip(headers, padded, strict=True)))
        row_numbers.append(row_index)

    if expected_rows is not None and len(rows) != expected_rows:
        raise WbDetailedXlsxError("WB_DETAILED_XLSX_ROW_COUNT_MISMATCH")
    if len(row_numbers) != len(set(row_numbers)):
        raise WbDetailedXlsxError("WB_DETAILED_XLSX_ROW_INDEX_DUPLICATE")

    binding = {
        "schema_version": DETAILED_XLSX_SCHEMA_VERSION,
        "sheet_name": sheet_name,
        "header_row_index": header_row_index,
        "header_sha256": claimed_hash,
        "column_count": len(headers),
        "data_row_count": len(rows),
        "first_data_row_index": min(row_numbers) if row_numbers else None,
        "last_data_row_index": max(row_numbers) if row_numbers else None,
    }
    return rows, binding


def bridge_detailed_financial_xlsx(
    *,
    payload: bytes,
    schema_discovery: Mapping[str, Any],
    limits: XlsxInspectionLimits,
    source_id: str,
) -> dict[str, Any]:
    """Bridge an admitted ZIP/XLSX directly into the detailed mapper.

    The discovered header, row count and sheet identity are rebound to the
    actual workbook before normalization. Raw row mappings exist only inside
    this call and are not included in the returned report.
    """
    rows, binding = _read_bound_rows(
        payload=payload,
        schema_discovery=schema_discovery,
        limits=limits,
    )
    result = normalize_detailed_financial_rows(
        rows,
        source_id=source_id,
        source_sha256=sha256(payload).hexdigest(),
    )
    result["xlsx_binding"] = binding
    result["raw_rows_in_report"] = False
    return result
