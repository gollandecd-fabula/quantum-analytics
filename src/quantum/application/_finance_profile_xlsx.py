from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any
from xml.etree import ElementTree
from zipfile import ZIP_DEFLATED, ZipFile

from quantum.adapters.wildberries.detailed_financial import (
    WbDetailedFinancialError,
    _ALIASES as _WB_DETAILED_ALIASES,
    normalize_detailed_financial_rows,
)
from quantum.adapters.wildberries.source_bridge import _sheet_rows
from quantum.finance import FinanceError, calculate, canonical_hash
from quantum.ingestion import XlsxInspectionLimits
from quantum.ingestion._xlsx_archive import _extract_workbook

from quantum.application._finance_profile_model import *

def _first_sheet_name(payload: bytes) -> str:
    _, workbook = _extract_workbook(payload, _SAFE_LIMITS)
    namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    try:
        with ZipFile(BytesIO(workbook)) as archive:
            root = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    except Exception as exc:
        raise FinanceProfileError("XLSX_WORKBOOK_INVALID") from exc
    sheets = root.find(f"{{{namespace}}}sheets")
    if sheets is None:
        raise FinanceProfileError("XLSX_SHEETS_MISSING")
    names = [
        (sheet.get("name") or "").strip()
        for sheet in sheets.findall(f"{{{namespace}}}sheet")
    ]
    names = [name for name in names if name]
    if not names:
        raise FinanceProfileError("XLSX_SHEETS_MISSING")
    return names[0]


def read_first_sheet(path: Path) -> list[tuple[int, tuple[str, ...]]]:
    if not isinstance(path, Path) or not path.is_file():
        raise FinanceProfileError("XLSX_FILE_NOT_FOUND")
    payload = path.read_bytes()
    if not payload:
        raise FinanceProfileError("XLSX_FILE_EMPTY")
    sheet_name = _first_sheet_name(payload)
    try:
        return _sheet_rows(payload, sheet_name=sheet_name, limits=_SAFE_LIMITS)
    except Exception as exc:
        raise FinanceProfileError("XLSX_PARSE_FAILED", (type(exc).__name__,)) from exc


def _find_header(
    rows: Sequence[tuple[int, tuple[str, ...]]],
    required_fields: Sequence[str],
    *,
    max_scan_rows: int = 40,
) -> tuple[int, tuple[str, ...], dict[str, int]]:
    candidates: list[tuple[int, tuple[str, ...], dict[str, int]]] = []
    for row_index, values in rows:
        if row_index > max_scan_rows:
            continue
        tokens = [_header_token(value) for value in values]
        positions: dict[str, int] = {}
        for field_name in required_fields:
            aliases = _HEADER_ALIASES.get(field_name) or _DETAILED_REQUIRED_HEADERS.get(field_name)
            if aliases is None:
                raise FinanceProfileError("XLSX_HEADER_RULE_INVALID")
            matches = [index for index, token in enumerate(tokens) if token in aliases]
            if len(matches) == 1:
                positions[field_name] = matches[0]
        if all(field_name in positions for field_name in required_fields):
            candidates.append((row_index, values, positions))
    if len(candidates) != 1:
        raise FinanceProfileError("XLSX_HEADER_NOT_UNIQUE")
    return candidates[0]


def detect_products_from_xlsx(path: Path) -> tuple[ProductRecord, ...]:
    rows = read_first_sheet(path)
    candidates: list[tuple[int, tuple[str, ...], int]] = []
    for row_index, values in rows:
        if row_index > 40:
            continue
        tokens = [_header_token(value) for value in values]
        product_position = None
        for preferred in _PRODUCT_ID_PRIORITY:
            matches = [index for index, token in enumerate(tokens) if token == preferred]
            if len(matches) > 1:
                raise FinanceProfileError("XLSX_HEADER_DUPLICATE:product_id")
            if matches:
                product_position = matches[0]
                break
        if product_position is not None:
            candidates.append((row_index, values, product_position))
    if len(candidates) != 1:
        raise FinanceProfileError("XLSX_HEADER_NOT_UNIQUE")
    header_index, headers, product_position = candidates[0]
    header_tokens = [_header_token(value) for value in headers]

    def optional_position(field_name: str) -> int | None:
        aliases = _HEADER_ALIASES[field_name]
        matches = [index for index, token in enumerate(header_tokens) if token in aliases]
        if len(matches) > 1:
            raise FinanceProfileError("XLSX_HEADER_DUPLICATE:" + field_name)
        return matches[0] if matches else None

    group_position = optional_position("group")
    name_position = optional_position("product_name")
    discovered: dict[str, ProductRecord] = {}
    for row_index, values in rows:
        if row_index <= header_index or not any(value.strip() for value in values):
            continue
        product_id = values[product_position].strip() if product_position < len(values) else ""
        if not product_id:
            continue
        name = (
            values[name_position].strip()
            if name_position is not None and name_position < len(values)
            else product_id
        ) or product_id
        group_name = (
            values[group_position].strip()
            if group_position is not None and group_position < len(values)
            else UNASSIGNED_GROUP
        ) or UNASSIGNED_GROUP
        record = ProductRecord(product_id, name, group_name, path.name)
        previous = discovered.get(product_id)
        if previous is not None and previous.detected_group != group_name:
            raise FinanceProfileError(
                "PRODUCT_GROUP_CONFLICT",
                (product_id, previous.detected_group, group_name),
            )
        discovered[product_id] = record
    if not discovered:
        raise FinanceProfileError("PRODUCTS_NOT_FOUND")
    return tuple(discovered[key] for key in sorted(discovered))

__all__ = [name for name in globals() if not name.startswith("__")]
