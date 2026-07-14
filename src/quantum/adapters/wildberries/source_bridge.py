from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import BytesIO
import json
import re
from typing import Any
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from quantum.ingestion import XlsxInspectionLimits
from quantum.ingestion._xlsx_archive import (
    _cell_position,
    _cell_text,
    _extract_workbook,
    _read_limited,
    _shared_strings,
    _xml_root,
)
from quantum.ingestion._xlsx_contracts import normalized_header_sha256


BRIDGE_SCHEMA_VERSION = "quantum-wb-source-bridge-v1"
SUPPLIER_GOODS_SOURCE_TYPE = "WB_SUPPLIER_GOODS"
_SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_RELATIONSHIP_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_OFFICE_RELATIONSHIP_NS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)
_RELATIONSHIP = f"{{{_RELATIONSHIP_NS}}}Relationship"
_DECIMAL = re.compile(r"^[+-]?(?:0|[1-9][0-9]*)(?:[.,][0-9]+)?$")
_EXPECTED_SUPPLIER_GOODS_HEADERS = (
    "Бренд",
    "Предмет",
    "Сезон",
    "Коллекция",
    "Наименование",
    "Артикул продавца",
    "Артикул WB",
    "Баркод",
    "Размер",
    "Контракт",
    "Склад",
    "шт.",
    "Сумма заказов минус комиссия WB, руб.",
    "Выкупили, шт.",
    "К перечислению за товар, руб.",
    "Текущий остаток, шт.",
)
_EXPECTED_SUPPLIER_GOODS_HEADER_HASH = (
    "8253be37c607a7881ad7f4c028f05c347f17ee1b88fd28c65a08b5e24ed51313"
)


class WbSourceBridgeError(ValueError):
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
        raise WbSourceBridgeError("WB_BRIDGE_JSON_INVALID") from exc


def _text(value: object, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WbSourceBridgeError(code)
    return " ".join(value.replace("\u00a0", " ").split())


def _positive_int(value: object, code: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise WbSourceBridgeError(code)
    return value


def _safe_workbook_target(target: str) -> str:
    if not isinstance(target, str):
        raise WbSourceBridgeError("WB_BRIDGE_RELATIONSHIP_INVALID")
    normalized = target.replace("\\", "/")
    if (
        not normalized
        or normalized.startswith("//")
        or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", normalized)
        or ":" in normalized
    ):
        raise WbSourceBridgeError("WB_BRIDGE_RELATIONSHIP_INVALID")
    package_absolute = normalized.startswith("/")
    if package_absolute:
        normalized = normalized[1:]
    pieces = normalized.split("/")
    if any(not piece or piece in {".", ".."} for piece in pieces):
        raise WbSourceBridgeError("WB_BRIDGE_RELATIONSHIP_INVALID")
    joined = "/".join(pieces)
    if package_absolute:
        if not joined.casefold().startswith("xl/"):
            raise WbSourceBridgeError("WB_BRIDGE_RELATIONSHIP_INVALID")
        return joined
    if joined.casefold().startswith("xl/"):
        return joined
    return "xl/" + joined


def _worksheet_path(
    archive: ZipFile,
    *,
    sheet_name: str,
    limits: XlsxInspectionLimits,
) -> str:
    workbook = _xml_root(
        _read_limited(archive, "xl/workbook.xml", limits),
        "WB_BRIDGE_WORKBOOK_INVALID",
    )
    relationships = _xml_root(
        _read_limited(archive, "xl/_rels/workbook.xml.rels", limits),
        "WB_BRIDGE_RELATIONSHIPS_INVALID",
    )
    relationship_map: dict[str, str] = {}
    for relation in relationships.findall(_RELATIONSHIP):
        relation_id = relation.get("Id")
        if not relation_id or relation_id in relationship_map:
            raise WbSourceBridgeError("WB_BRIDGE_RELATIONSHIPS_INVALID")
        relationship_map[relation_id] = _safe_workbook_target(
            relation.get("Target") or ""
        )

    sheets = workbook.find(f"{{{_SPREADSHEET_NS}}}sheets")
    if sheets is None:
        raise WbSourceBridgeError("WB_BRIDGE_SHEETS_MISSING")
    matches: list[str] = []
    for sheet in sheets.findall(f"{{{_SPREADSHEET_NS}}}sheet"):
        if (sheet.get("name") or "").strip() != sheet_name:
            continue
        relation_id = sheet.get(f"{{{_OFFICE_RELATIONSHIP_NS}}}id")
        target = relationship_map.get(relation_id or "")
        if target is None:
            raise WbSourceBridgeError("WB_BRIDGE_SHEET_RELATIONSHIP_MISSING")
        matches.append(target)
    if len(matches) != 1:
        raise WbSourceBridgeError("WB_BRIDGE_SHEET_NOT_UNIQUE")
    target = matches[0]
    if not (
        target.casefold().startswith("xl/worksheets/")
        and target.casefold().endswith(".xml")
    ):
        raise WbSourceBridgeError("WB_BRIDGE_WORKSHEET_TARGET_INVALID")
    return target


def _row_values(
    row: ElementTree.Element,
    *,
    shared: tuple[str, ...],
    max_columns: int,
) -> tuple[str, ...]:
    values: dict[int, str] = {}
    for cell in row.findall(f"{{{_SPREADSHEET_NS}}}c"):
        reference = cell.get("r") or ""
        column, _ = _cell_position(reference)
        if column > max_columns or column in values:
            raise WbSourceBridgeError("WB_BRIDGE_CELL_LAYOUT_INVALID")
        if cell.find(f"{{{_SPREADSHEET_NS}}}f") is not None:
            raise WbSourceBridgeError("WB_BRIDGE_FORMULA_FORBIDDEN")
        values[column] = _cell_text(cell, shared).strip()
    if not values:
        return ()
    return tuple(values.get(index, "") for index in range(1, max(values) + 1))


def _sheet_rows(
    payload: bytes,
    *,
    sheet_name: str,
    limits: XlsxInspectionLimits,
) -> list[tuple[int, tuple[str, ...]]]:
    _, workbook = _extract_workbook(payload, limits)
    try:
        with ZipFile(BytesIO(workbook)) as archive:
            sheet_path = _worksheet_path(
                archive,
                sheet_name=sheet_name,
                limits=limits,
            )
            shared = _shared_strings(archive, limits)
            root = _xml_root(
                _read_limited(archive, sheet_path, limits),
                "WB_BRIDGE_WORKSHEET_INVALID",
            )
            sheet_data = root.find(f"{{{_SPREADSHEET_NS}}}sheetData")
            if sheet_data is None:
                raise WbSourceBridgeError("WB_BRIDGE_SHEET_DATA_MISSING")
            result: list[tuple[int, tuple[str, ...]]] = []
            for row in sheet_data.findall(f"{{{_SPREADSHEET_NS}}}row"):
                raw_index = row.get("r") or ""
                try:
                    row_index = int(raw_index)
                except ValueError as exc:
                    raise WbSourceBridgeError(
                        "WB_BRIDGE_ROW_INDEX_INVALID"
                    ) from exc
                if row_index < 1 or row_index > limits.max_rows:
                    raise WbSourceBridgeError("WB_BRIDGE_ROW_INDEX_INVALID")
                values = _row_values(
                    row,
                    shared=shared,
                    max_columns=limits.max_columns,
                )
                result.append((row_index, values))
            return result
    except WbSourceBridgeError:
        raise
    except BadZipFile as exc:
        raise WbSourceBridgeError("WB_BRIDGE_ARCHIVE_INVALID") from exc


def _decimal(value: str, code: str) -> Decimal:
    normalized = value.replace("\u00a0", "").replace(" ", "").strip()
    if not _DECIMAL.fullmatch(normalized):
        raise WbSourceBridgeError(code)
    try:
        parsed = Decimal(normalized.replace(",", "."))
    except InvalidOperation as exc:
        raise WbSourceBridgeError(code) from exc
    if not parsed.is_finite() or parsed < 0:
        raise WbSourceBridgeError(code)
    return parsed


def _integer(value: str, code: str) -> int:
    parsed = _decimal(value, code)
    integral = parsed.to_integral_value()
    if parsed != integral:
        raise WbSourceBridgeError(code)
    return int(integral)


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def _metric(
    value: int | str,
    *,
    value_type: str,
    unit: str,
    authority: str,
) -> dict[str, str]:
    return {
        "state": "VALID",
        "value": str(value),
        "value_type": value_type,
        "unit": unit,
        "authority": authority,
    }


def _supplier_goods_summary(
    rows: list[tuple[int, tuple[str, ...]]],
    *,
    header_row_index: int,
    expected_row_count: int | None,
    source_sha256: str,
    sheet_name: str,
) -> dict[str, Any]:
    header_matches = [values for index, values in rows if index == header_row_index]
    if len(header_matches) != 1:
        raise WbSourceBridgeError("WB_BRIDGE_HEADER_ROW_NOT_UNIQUE")
    headers = header_matches[0]
    if headers != _EXPECTED_SUPPLIER_GOODS_HEADERS:
        raise WbSourceBridgeError("WB_SUPPLIER_GOODS_HEADERS_UNSUPPORTED")
    if normalized_header_sha256(headers) != _EXPECTED_SUPPLIER_GOODS_HEADER_HASH:
        raise WbSourceBridgeError("WB_SUPPLIER_GOODS_HEADER_HASH_MISMATCH")

    data_rows = [
        (index, values)
        for index, values in rows
        if index > header_row_index and any(value.strip() for value in values)
    ]
    if expected_row_count is not None and len(data_rows) != expected_row_count:
        raise WbSourceBridgeError("WB_BRIDGE_ROW_COUNT_MISMATCH")

    keys: set[tuple[str, str, str, str]] = set()
    articles: set[str] = set()
    warehouses: set[str] = set()
    brands: set[str] = set()
    subjects: set[str] = set()
    row_hashes: list[str] = []
    ordered_units = 0
    bought_units = 0
    stock_units = 0
    ordered_amount = Decimal("0")
    payout_amount = Decimal("0")

    for row_index, values in data_rows:
        padded = values + ("",) * (len(headers) - len(values))
        if len(padded) != len(headers):
            raise WbSourceBridgeError("WB_SUPPLIER_GOODS_COLUMN_COUNT_INVALID")
        row = dict(zip(headers, padded, strict=True))
        article = _text(
            row["Артикул продавца"],
            "WB_SUPPLIER_GOODS_ARTICLE_REQUIRED",
        )
        barcode = _text(row["Баркод"], "WB_SUPPLIER_GOODS_BARCODE_REQUIRED")
        size = _text(row["Размер"], "WB_SUPPLIER_GOODS_SIZE_REQUIRED")
        warehouse = _text(row["Склад"], "WB_SUPPLIER_GOODS_WAREHOUSE_REQUIRED")
        key = (article, barcode, size, warehouse)
        if key in keys:
            raise WbSourceBridgeError("WB_SUPPLIER_GOODS_DUPLICATE_KEY")
        keys.add(key)
        articles.add(article)
        warehouses.add(warehouse)
        if row["Бренд"].strip():
            brands.add(_text(row["Бренд"], "WB_SUPPLIER_GOODS_BRAND_INVALID"))
        if row["Предмет"].strip():
            subjects.add(_text(row["Предмет"], "WB_SUPPLIER_GOODS_SUBJECT_INVALID"))

        row_ordered_units = _integer(
            row["шт."],
            "WB_SUPPLIER_GOODS_ORDERED_UNITS_INVALID",
        )
        row_ordered_amount = _decimal(
            row["Сумма заказов минус комиссия WB, руб."],
            "WB_SUPPLIER_GOODS_ORDERED_AMOUNT_INVALID",
        )
        row_bought_units = _integer(
            row["Выкупили, шт."],
            "WB_SUPPLIER_GOODS_BOUGHT_UNITS_INVALID",
        )
        row_payout_amount = _decimal(
            row["К перечислению за товар, руб."],
            "WB_SUPPLIER_GOODS_PAYOUT_INVALID",
        )
        row_stock_units = _integer(
            row["Текущий остаток, шт."],
            "WB_SUPPLIER_GOODS_STOCK_INVALID",
        )
        ordered_units += row_ordered_units
        ordered_amount += row_ordered_amount
        bought_units += row_bought_units
        payout_amount += row_payout_amount
        stock_units += row_stock_units

        canonical_row = {
            "row_index": row_index,
            "key": list(key),
            "brand": row["Бренд"],
            "subject": row["Предмет"],
            "name": row["Наименование"],
            "wb_article": row["Артикул WB"],
            "contract": row["Контракт"],
            "ordered_units": row_ordered_units,
            "ordered_amount_net_commission": str(row_ordered_amount),
            "bought_units": row_bought_units,
            "payout_amount": str(row_payout_amount),
            "current_stock_units": row_stock_units,
        }
        row_hashes.append(sha256(_canonical_json(canonical_row)).hexdigest())

    canonical_rows_sha256 = sha256(
        _canonical_json(sorted(row_hashes))
    ).hexdigest()
    authority = "PRIMARY_SKU_STOCK_AND_AGGREGATED_ORDER_BUY_SOURCE"
    return {
        "schema_version": BRIDGE_SCHEMA_VERSION,
        "status": "SOURCE_BRIDGE_COMPLETE",
        "source_type": SUPPLIER_GOODS_SOURCE_TYPE,
        "source_sha256": source_sha256,
        "sheet_name": sheet_name,
        "header_row_index": header_row_index,
        "header_sha256": _EXPECTED_SUPPLIER_GOODS_HEADER_HASH,
        "row_count": len(data_rows),
        "canonical_key_count": len(keys),
        "canonical_rows_sha256": canonical_rows_sha256,
        "dimensions": {
            "seller_article_count": len(articles),
            "warehouse_count": len(warehouses),
            "brand_count": len(brands),
            "subject_count": len(subjects),
        },
        "observed_metrics": {
            "ordered_units": _metric(
                ordered_units,
                value_type="INTEGER",
                unit="ITEM",
                authority=authority,
            ),
            "ordered_amount_net_commission": _metric(
                _money(ordered_amount),
                value_type="MONEY",
                unit="MONEY",
                authority=authority,
            ),
            "bought_units": _metric(
                bought_units,
                value_type="INTEGER",
                unit="ITEM",
                authority=authority,
            ),
            "payout_amount": _metric(
                _money(payout_amount),
                value_type="MONEY",
                unit="MONEY",
                authority=authority,
            ),
            "current_stock_units": _metric(
                stock_units,
                value_type="INTEGER",
                unit="ITEM",
                authority=authority,
            ),
        },
        "finance_request": None,
        "finance_request_state": "BLOCKED",
        "finance_request_reason_code": (
            "EVENT_LEVEL_FINANCIAL_SOURCE_REQUIRED_FOR_KERNEL"
        ),
        "diagnostics": [],
        "limitations": [
            "AGGREGATED_SOURCE_NOT_EVENT_LEDGER",
            "RETURNS_AND_DIRECT_WB_EXPENSES_NOT_AVAILABLE",
            "PAYOUT_IS_NOT_GROSS_SALES",
            "NO_FINANCIAL_DEFAULTS_OR_ZERO_COERCION_APPLIED",
        ],
        "raw_rows_in_report": False,
    }


def bridge_admitted_xlsx(
    *,
    payload: bytes,
    schema_discovery: Mapping[str, Any],
    limits: XlsxInspectionLimits,
) -> dict[str, Any]:
    """Extract a governed aggregate from an already admitted WB workbook.

    The bridge does not bypass admission and never copies raw rows into the
    result. Supplier-goods can establish SKU, stock, order and buy aggregates,
    but cannot manufacture an event-level finance request.
    """
    if not isinstance(payload, bytes) or not payload:
        raise WbSourceBridgeError("WB_BRIDGE_PAYLOAD_REQUIRED")
    if not isinstance(schema_discovery, Mapping):
        raise WbSourceBridgeError("WB_BRIDGE_SCHEMA_DISCOVERY_REQUIRED")
    if not isinstance(limits, XlsxInspectionLimits):
        raise WbSourceBridgeError("WB_BRIDGE_LIMITS_INVALID")

    sheet_name = _text(
        schema_discovery.get("sheet_name"),
        "WB_BRIDGE_SHEET_NAME_INVALID",
    )
    header_row_index = _positive_int(
        schema_discovery.get("header_row_index"),
        "WB_BRIDGE_HEADER_ROW_INDEX_INVALID",
    )
    raw_headers = schema_discovery.get("headers")
    if (
        not isinstance(raw_headers, list)
        or not raw_headers
        or any(not isinstance(item, str) for item in raw_headers)
    ):
        raise WbSourceBridgeError("WB_BRIDGE_HEADERS_INVALID")
    headers = tuple(raw_headers)
    claimed_hash = _text(
        schema_discovery.get("header_sha256"),
        "WB_BRIDGE_HEADER_HASH_INVALID",
    )
    if normalized_header_sha256(headers) != claimed_hash:
        raise WbSourceBridgeError("WB_BRIDGE_DISCOVERY_HASH_MISMATCH")

    raw_count = schema_discovery.get("data_row_count")
    expected_row_count = None
    if raw_count is not None:
        if (
            not isinstance(raw_count, int)
            or isinstance(raw_count, bool)
            or raw_count < 0
        ):
            raise WbSourceBridgeError("WB_BRIDGE_EXPECTED_ROW_COUNT_INVALID")
        expected_row_count = raw_count

    if (
        headers != _EXPECTED_SUPPLIER_GOODS_HEADERS
        or claimed_hash != _EXPECTED_SUPPLIER_GOODS_HEADER_HASH
    ):
        raise WbSourceBridgeError("WB_SOURCE_SCHEMA_UNSUPPORTED")

    rows = _sheet_rows(
        payload,
        sheet_name=sheet_name,
        limits=limits,
    )
    return _supplier_goods_summary(
        rows,
        header_row_index=header_row_index,
        expected_row_count=expected_row_count,
        source_sha256=sha256(payload).hexdigest(),
        sheet_name=sheet_name,
    )
