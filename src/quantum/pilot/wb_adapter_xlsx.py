from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path, PurePosixPath
import re
from typing import Any, Sequence
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from .wb_adapter_common import AdapterError, WorkbookData

_NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_NS_REL_PACKAGE = "http://schemas.openxmlformats.org/package/2006/relationships"
_NS_REL_OFFICE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_MAX_FILE_BYTES = 256 * 1024 * 1024
_MAX_ENTRIES = 20_000
_MAX_ENTRY_BYTES = 256 * 1024 * 1024
_MAX_TOTAL_BYTES = 1024 * 1024 * 1024
_MAX_RATIO = 200


def _safe_zip_name(name: str) -> str:
    if not name or "\x00" in name:
        raise AdapterError("WB_ADAPTER_ARCHIVE_PATH_INVALID")
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        raise AdapterError("WB_ADAPTER_ARCHIVE_PATH_INVALID")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise AdapterError("WB_ADAPTER_ARCHIVE_PATH_INVALID")
    return str(path)


def _read_bytes(path: Path) -> bytes:
    if not path.is_file():
        raise AdapterError("WB_ADAPTER_SOURCE_NOT_FOUND", str(path))
    size = path.stat().st_size
    if size < 1:
        raise AdapterError("WB_ADAPTER_SOURCE_EMPTY", str(path))
    if size > _MAX_FILE_BYTES:
        raise AdapterError("WB_ADAPTER_SOURCE_TOO_LARGE", str(path))
    return path.read_bytes()


def _xml(data: bytes, code: str) -> ET.Element:
    upper = data[:8192].upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise AdapterError("WB_ADAPTER_XML_ENTITY_FORBIDDEN")
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise AdapterError(code) from exc


def _zip_read(archive: ZipFile, name: str) -> bytes:
    try:
        info = archive.getinfo(name)
    except KeyError as exc:
        raise AdapterError("WB_ADAPTER_XLSX_PART_MISSING", name) from exc
    if info.file_size > _MAX_ENTRY_BYTES:
        raise AdapterError("WB_ADAPTER_ARCHIVE_ENTRY_TOO_LARGE", name)
    if info.file_size and (
        info.compress_size == 0 or info.file_size > info.compress_size * _MAX_RATIO
    ):
        raise AdapterError("WB_ADAPTER_ARCHIVE_RATIO_EXCEEDED", name)
    return archive.read(info)


def _column_index(reference: str) -> int:
    letters = "".join(ch for ch in reference if ch.isalpha())
    if not letters:
        raise AdapterError("WB_ADAPTER_CELL_REFERENCE_INVALID", reference)
    value = 0
    for ch in letters.upper():
        value = value * 26 + (ord(ch) - 64)
    return value


def _cell_value(cell: ET.Element, shared: Sequence[str]) -> Any:
    cell_type = cell.get("t")
    if cell_type == "inlineStr":
        return "".join(
            node.text or "" for node in cell.findall(f".//{{{_NS_MAIN}}}t")
        )
    value_node = cell.find(f"{{{_NS_MAIN}}}v")
    raw = "" if value_node is None or value_node.text is None else value_node.text
    if cell_type == "s":
        try:
            return shared[int(raw)]
        except (ValueError, IndexError) as exc:
            raise AdapterError("WB_ADAPTER_SHARED_STRING_INVALID") from exc
    if cell_type in {"str", "e"}:
        return raw
    if cell_type == "b":
        return raw == "1"
    if raw == "":
        return ""
    try:
        if re.fullmatch(r"[-+]?\d+", raw):
            return int(raw)
        return float(raw)
    except ValueError:
        return raw


def load_xlsx(path: Path) -> WorkbookData:
    payload = _read_bytes(path)
    digest = sha256(payload).hexdigest()
    try:
        archive = ZipFile(BytesIO(payload))
    except BadZipFile as exc:
        raise AdapterError("WB_ADAPTER_XLSX_INVALID", path.name) from exc

    with archive:
        infos = archive.infolist()
        if not infos or len(infos) > _MAX_ENTRIES:
            raise AdapterError("WB_ADAPTER_ARCHIVE_ENTRY_LIMIT")
        total = 0
        seen: set[str] = set()
        for info in infos:
            name = _safe_zip_name(info.filename)
            key = name.casefold()
            if key in seen:
                raise AdapterError("WB_ADAPTER_ARCHIVE_DUPLICATE_PATH", name)
            seen.add(key)
            if info.flag_bits & 1:
                raise AdapterError("WB_ADAPTER_ARCHIVE_ENCRYPTED")
            total += info.file_size
            if total > _MAX_TOTAL_BYTES:
                raise AdapterError("WB_ADAPTER_ARCHIVE_TOTAL_TOO_LARGE")

        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = _xml(
                _zip_read(archive, "xl/sharedStrings.xml"),
                "WB_ADAPTER_SHARED_STRINGS_INVALID",
            )
            for item in root.findall(f"{{{_NS_MAIN}}}si"):
                shared.append(
                    "".join(
                        node.text or ""
                        for node in item.findall(f".//{{{_NS_MAIN}}}t")
                    )
                )

        workbook = _xml(
            _zip_read(archive, "xl/workbook.xml"),
            "WB_ADAPTER_WORKBOOK_INVALID",
        )
        relationships = _xml(
            _zip_read(archive, "xl/_rels/workbook.xml.rels"),
            "WB_ADAPTER_WORKBOOK_RELS_INVALID",
        )
        relationship_map: dict[str, str] = {}
        for relation in relationships.findall(
            f"{{{_NS_REL_PACKAGE}}}Relationship"
        ):
            relationship_id = relation.get("Id") or ""
            target = (relation.get("Target") or "").replace("\\", "/")
            if target.startswith("/"):
                target = target[1:]
            elif not target.startswith("xl/"):
                target = "xl/" + target
            relationship_map[relationship_id] = _safe_zip_name(target)

        sheets_node = workbook.find(f"{{{_NS_MAIN}}}sheets")
        if sheets_node is None:
            raise AdapterError("WB_ADAPTER_SHEETS_MISSING")

        sheets: dict[str, tuple[tuple[Any, ...], ...]] = {}
        for node in sheets_node.findall(f"{{{_NS_MAIN}}}sheet"):
            name = (node.get("name") or "").strip()
            relationship_id = node.get(f"{{{_NS_REL_OFFICE}}}id") or ""
            target = relationship_map.get(relationship_id)
            if (
                not name
                or not target
                or not target.startswith("xl/worksheets/")
            ):
                continue
            root = _xml(
                _zip_read(archive, target),
                "WB_ADAPTER_WORKSHEET_INVALID",
            )
            sheet_data = root.find(f"{{{_NS_MAIN}}}sheetData")
            rows_out: list[tuple[Any, ...]] = []
            if sheet_data is not None:
                for row in sheet_data.findall(f"{{{_NS_MAIN}}}row"):
                    values: dict[int, Any] = {}
                    for cell in row.findall(f"{{{_NS_MAIN}}}c"):
                        reference = cell.get("r") or ""
                        column = _column_index(reference)
                        if column in values:
                            raise AdapterError(
                                "WB_ADAPTER_CELL_DUPLICATE",
                                reference,
                            )
                        values[column] = _cell_value(cell, shared)
                    if not values:
                        rows_out.append(())
                        continue
                    last = max(values)
                    raw_row = [values.get(i, "") for i in range(1, last + 1)]
                    while raw_row and raw_row[-1] in {"", None}:
                        raw_row.pop()
                    rows_out.append(tuple(raw_row))
            sheets[name] = tuple(rows_out)

    return WorkbookData(path=path, file_sha256=digest, sheets=sheets)
