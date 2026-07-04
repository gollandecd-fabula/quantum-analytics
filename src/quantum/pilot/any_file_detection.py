from __future__ import annotations

import csv
from io import BytesIO, StringIO
import json
from pathlib import PurePosixPath
import re
import stat
from typing import Any
from xml.etree import ElementTree
from zipfile import BadZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile

from .any_file_common import AnyFileError, Detection

_ALLOWED_ZIP_METHODS = {ZIP_STORED, ZIP_DEFLATED}
_XLSX_REQUIRED = {
    "[content_types].xml",
    "_rels/.rels",
    "xl/workbook.xml",
    "xl/_rels/workbook.xml.rels",
}
_BLOCKED_SUFFIXES = tuple(
    "." + item
    for item in (
        "exe", "dll", "com", "scr", "js", "jse", "vbs", "vbe",
        "ps1", "bat", "cmd", "sh", "py", "jar", "msi",
    )
)
_BLOCKED_ARCHIVE_MARKERS = (
    "xl/activex/", "xl/embeddings/", "customui/", "vbaproject.bin",
)
_EXECUTABLE_MAGIC = tuple(
    bytes.fromhex(item)
    for item in (
        "4d5a", "7f454c46", "feedface", "feedfacf", "cefaedfe", "cffaedfe",
    )
)
_IMAGE_MAGIC = (
    (bytes.fromhex("89504e470d0a1a0a"), "PNG", "image/png"),
    (bytes.fromhex("ffd8ff"), "JPEG", "image/jpeg"),
    (b"GIF87a", "GIF", "image/gif"),
    (b"GIF89a", "GIF", "image/gif"),
    (bytes.fromhex("49492a00"), "TIFF", "image/tiff"),
    (bytes.fromhex("4d4d002a"), "TIFF", "image/tiff"),
)
_MAX_FILE_BYTES = 256 * 1024 * 1024
_MAX_ARCHIVE_ENTRIES = 20_000
_MAX_ARCHIVE_TOTAL = 1024 * 1024 * 1024
_MAX_ARCHIVE_ENTRY = 256 * 1024 * 1024
_MAX_COMPRESSION_RATIO = 200
_MAX_TEXT_BYTES = 32 * 1024 * 1024


def _safe_member_name(name: str) -> str:
    if not name or "\x00" in name:
        raise AnyFileError("ANY_FILE_ARCHIVE_PATH_INVALID")
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        raise AnyFileError("ANY_FILE_ARCHIVE_PATH_INVALID")
    path = PurePosixPath(normalized)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise AnyFileError("ANY_FILE_ARCHIVE_PATH_INVALID")
    return str(path)


def _is_symlink(info: Any) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(mode)


def _inspect_zip(payload: bytes) -> Detection:
    try:
        with ZipFile(BytesIO(payload)) as archive:
            infos = archive.infolist()
            if not infos or len(infos) > _MAX_ARCHIVE_ENTRIES:
                raise AnyFileError("ANY_FILE_ARCHIVE_ENTRY_LIMIT_EXCEEDED")
            normalized: dict[str, Any] = {}
            total = 0
            for info in infos:
                name = _safe_member_name(info.filename)
                key = name.casefold()
                if key in normalized:
                    raise AnyFileError("ANY_FILE_ARCHIVE_DUPLICATE_PATH")
                normalized[key] = info
                if info.flag_bits & 0x1:
                    raise AnyFileError("ANY_FILE_ARCHIVE_ENCRYPTED_ENTRY")
                if info.compress_type not in _ALLOWED_ZIP_METHODS:
                    raise AnyFileError("ANY_FILE_ARCHIVE_COMPRESSION_UNSUPPORTED")
                if _is_symlink(info):
                    raise AnyFileError("ANY_FILE_ARCHIVE_SYMLINK_FORBIDDEN")
                if info.file_size > _MAX_ARCHIVE_ENTRY:
                    raise AnyFileError("ANY_FILE_ARCHIVE_ENTRY_SIZE_EXCEEDED")
                total += info.file_size
                if total > _MAX_ARCHIVE_TOTAL:
                    raise AnyFileError("ANY_FILE_ARCHIVE_TOTAL_SIZE_EXCEEDED")
                if info.file_size and (
                    info.compress_size == 0
                    or info.file_size > info.compress_size * _MAX_COMPRESSION_RATIO
                ):
                    raise AnyFileError("ANY_FILE_ARCHIVE_COMPRESSION_RATIO_EXCEEDED")
                lower = name.casefold()
                if lower.endswith(_BLOCKED_SUFFIXES) or any(
                    marker in lower for marker in _BLOCKED_ARCHIVE_MARKERS
                ):
                    raise AnyFileError("ANY_FILE_ARCHIVE_ACTIVE_CONTENT_FORBIDDEN")

            names = set(normalized)
            if _XLSX_REQUIRED.issubset(names):
                return Detection(
                    kind="XLSX",
                    media_type=(
                        "application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet"
                    ),
                    workbook_payload=payload,
                    archive_entries=len(infos),
                )
            files = [info for info in infos if not info.is_dir()]
            nested = [
                info for info in files
                if info.filename.casefold().endswith(".xlsx")
            ]
            if len(files) == 1 and len(nested) == 1:
                workbook = archive.read(nested[0])
                try:
                    with ZipFile(BytesIO(workbook)) as nested_archive:
                        nested_names = {
                            _safe_member_name(item.filename).casefold()
                            for item in nested_archive.infolist()
                        }
                except (BadZipFile, OSError, EOFError, ValueError) as exc:
                    raise AnyFileError("ANY_FILE_NESTED_XLSX_CORRUPTED") from exc
                if not _XLSX_REQUIRED.issubset(nested_names):
                    raise AnyFileError("ANY_FILE_NESTED_XLSX_CORRUPTED")
                return Detection(
                    kind="ZIP_XLSX",
                    media_type="application/zip",
                    workbook_payload=workbook,
                    archive_entries=len(infos),
                )
            return Detection("ZIP", "application/zip", archive_entries=len(infos))
    except AnyFileError:
        raise
    except (BadZipFile, OSError, EOFError, ValueError) as exc:
        raise AnyFileError("ANY_FILE_ARCHIVE_CORRUPTED") from exc


def detect(payload: bytes, filename: str) -> Detection:
    if not payload:
        raise AnyFileError("ANY_FILE_EMPTY")
    if len(payload) > _MAX_FILE_BYTES:
        raise AnyFileError("ANY_FILE_SIZE_EXCEEDED")
    lower = filename.casefold()
    if payload.startswith(_EXECUTABLE_MAGIC) or lower.endswith(_BLOCKED_SUFFIXES):
        raise AnyFileError("ANY_FILE_EXECUTABLE_FORBIDDEN")
    if payload.startswith(bytes.fromhex("504b0304")) or lower.endswith((".zip", ".xlsx")):
        return _inspect_zip(payload)
    if payload.startswith(b"%PDF-"):
        return Detection("PDF", "application/pdf")
    for magic, kind, media_type in _IMAGE_MAGIC:
        if payload.startswith(magic):
            return Detection(kind, media_type)
    if payload.startswith(b"RIFF") and payload[8:12] == b"WEBP":
        return Detection("WEBP", "image/webp")
    if payload.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
        raise AnyFileError("ANY_FILE_LEGACY_ACTIVE_DOCUMENT_UNINSPECTED")
    if len(payload) <= _MAX_TEXT_BYTES:
        try:
            text = payload.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = ""
        if text and "\x00" not in text:
            printable = sum(
                char.isprintable() or char in "\r\n\t" for char in text
            )
            if printable / len(text) < 0.95:
                text = ""
        if text:
            stripped = text.lstrip()
            if stripped.startswith(("{", "[")):
                try:
                    json.loads(text)
                    return Detection("JSON", "application/json")
                except json.JSONDecodeError:
                    pass
            if stripped.startswith("<"):
                upper = stripped[:4096].upper()
                if "<!DOCTYPE" in upper or "<!ENTITY" in upper:
                    raise AnyFileError("ANY_FILE_XML_ENTITY_FORBIDDEN")
                try:
                    ElementTree.fromstring(text)
                    return Detection("XML", "application/xml")
                except ElementTree.ParseError:
                    pass
            if "\n" in text and any(item in text for item in (",", ";", "\t")):
                return Detection("DELIMITED_TEXT", "text/csv")
            return Detection("TEXT", "text/plain")
    return Detection("BINARY", "application/octet-stream")


def text_structure(payload: bytes, detection: Detection) -> dict[str, Any]:
    text = payload.decode("utf-8-sig")
    if detection.kind == "JSON":
        value = json.loads(text)
        if isinstance(value, dict):
            return {"top_level": "object", "key_count": len(value)}
        if isinstance(value, list):
            return {"top_level": "array", "item_count": len(value)}
        return {"top_level": type(value).__name__}
    if detection.kind == "XML":
        root = ElementTree.fromstring(text)
        return {"root_tag": root.tag, "direct_child_count": len(root)}
    if detection.kind == "DELIMITED_TEXT":
        sample = text[:65536]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        rows = list(csv.reader(StringIO(text), dialect))
        width = max((len(row) for row in rows), default=0)
        return {
            "row_count": max(0, len(rows) - 1),
            "column_count": width,
            "headers": rows[0][:100] if rows else [],
            "delimiter": dialect.delimiter,
        }
    return {"line_count": text.count("\n") + 1, "character_count": len(text)}
