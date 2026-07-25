from __future__ import annotations

import bz2
import csv
from dataclasses import dataclass, field
import gzip
from hashlib import sha256
from io import BytesIO, StringIO
import json
import lzma
from pathlib import PurePosixPath
import re
import stat
import tarfile
from typing import Any, Iterable, Mapping, Sequence
import unicodedata
from xml.etree import ElementTree
from zipfile import BadZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

from quantum.adapters.wildberries.source_bridge import _sheet_rows
from quantum.application._finance_profile_model import _SAFE_LIMITS
from quantum.ingestion._xlsx_archive import _extract_workbook, _read_limited, _xml_root


UNIVERSAL_TABLE_SCHEMA_VERSION = "quantum-universal-tables-v1"
_MAX_DEPTH = 3
_MAX_MEMBERS = 10_000
_MAX_MEMBER_BYTES = 128 * 1024 * 1024
_MAX_TOTAL_BYTES = 512 * 1024 * 1024
_MAX_RATIO = 100
_MAX_TEXT_BYTES = 16 * 1024 * 1024
_MAX_ROWS = 1_000_000
_MAX_COLUMNS = 512
_ALLOWED_ZIP_METHODS = frozenset({ZIP_STORED, ZIP_DEFLATED})
_BLOCKED_SUFFIXES = (
    ".exe", ".dll", ".com", ".scr", ".js", ".jse", ".vbs", ".vbe",
    ".ps1", ".bat", ".cmd", ".sh", ".py", ".jar", ".msi",
)
_EXECUTABLE_MAGIC = (
    b"MZ", b"\x7fELF", b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe",
)
_XLSX_REQUIRED = frozenset(
    {"[content_types].xml", "_rels/.rels", "xl/workbook.xml", "xl/_rels/workbook.xml.rels"}
)
_SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


class UniversalTableError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class ExtractedTable:
    source_name: str
    member_path: str
    detected_format: str
    headers: tuple[str, ...]
    rows: tuple[dict[str, str], ...]
    source_sha256: str
    reason_codes: tuple[str, ...] = ()

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def column_count(self) -> int:
        return len(self.headers)

    def summary(self) -> dict[str, Any]:
        return {
            "source_name": self.source_name,
            "member_path": self.member_path,
            "detected_format": self.detected_format,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "headers": list(self.headers),
            "source_sha256": self.source_sha256,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True, slots=True)
class MemberResult:
    member_path: str
    status: str
    detected_format: str | None
    table_count: int
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "member_path": self.member_path,
            "status": self.status,
            "detected_format": self.detected_format,
            "table_count": self.table_count,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(slots=True)
class ExtractionBudget:
    members: int = 0
    total_bytes: int = 0

    def charge(self, size: int) -> None:
        if size < 0 or size > _MAX_MEMBER_BYTES:
            raise UniversalTableError("ARCHIVE_MEMBER_SIZE_EXCEEDED")
        self.members += 1
        self.total_bytes += size
        if self.members > _MAX_MEMBERS:
            raise UniversalTableError("ARCHIVE_MEMBER_LIMIT_EXCEEDED")
        if self.total_bytes > _MAX_TOTAL_BYTES:
            raise UniversalTableError("ARCHIVE_TOTAL_SIZE_EXCEEDED")


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    status: str
    detected_format: str
    tables: tuple[ExtractedTable, ...]
    members: tuple[MemberResult, ...]
    reason_codes: tuple[str, ...]

    def public_summary(self) -> dict[str, Any]:
        return {
            "schema_version": UNIVERSAL_TABLE_SCHEMA_VERSION,
            "status": self.status,
            "detected_format": self.detected_format,
            "table_count": len(self.tables),
            "tables": [table.summary() for table in self.tables],
            "members": [member.to_dict() for member in self.members],
            "reason_codes": list(self.reason_codes),
            "raw_rows_in_report": False,
        }


def _safe_member_name(name: str) -> str:
    if not isinstance(name, str) or not name or "\x00" in name:
        raise UniversalTableError("ARCHIVE_PATH_INVALID")
    normalized = name.replace("\\", "/")
    if normalized.startswith("//") or re.match(r"^[A-Za-z]:", normalized):
        raise UniversalTableError("ARCHIVE_PATH_INVALID")
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise UniversalTableError("ARCHIVE_PATH_INVALID")
    canonical = unicodedata.normalize("NFC", str(path))
    if any(":" in part for part in PurePosixPath(canonical).parts):
        raise UniversalTableError("ARCHIVE_PATH_INVALID")
    return canonical


def _looks_executable(payload: bytes, name: str) -> bool:
    lower = PurePosixPath(name).suffix.casefold()
    return (
        lower in _BLOCKED_SUFFIXES
        or payload.startswith(b"#!")
        or any(payload.startswith(marker) for marker in _EXECUTABLE_MAGIC)
    )


def _decode_text(payload: bytes) -> tuple[str, str] | None:
    if len(payload) > _MAX_TEXT_BYTES:
        return None
    encodings = ["utf-8-sig"]
    if payload.startswith((b"\xff\xfe", b"\xfe\xff")):
        encodings.append("utf-16")
    encodings.append("cp1251")
    for encoding in encodings:
        try:
            text = payload.decode(encoding)
        except UnicodeError:
            continue
        sample = text[:100_000]
        controls = sum(ord(char) < 32 and char not in "\r\n\t" for char in sample)
        if controls / max(1, len(sample)) <= 0.01:
            return text, encoding
    return None


def _unique_headers(values: Sequence[object]) -> tuple[str, ...] | None:
    headers = tuple(" ".join(str(value).replace("\u00a0", " ").split()) for value in values)
    if len(headers) < 2 or len(headers) > _MAX_COLUMNS or any(not value for value in headers):
        return None
    keys = [value.casefold() for value in headers]
    if len(set(keys)) != len(keys):
        return None
    return headers


def _rows_to_table(
    *, source_name: str, member_path: str, detected_format: str,
    rows: Sequence[Sequence[object]], payload: bytes,
) -> ExtractedTable:
    header_index: int | None = None
    headers: tuple[str, ...] | None = None
    for index, row in enumerate(rows[:80]):
        candidate = _unique_headers(row)
        if candidate is not None:
            header_index = index
            headers = candidate
            break
    if header_index is None or headers is None:
        raise UniversalTableError("TABLE_HEADER_NOT_FOUND")
    records: list[dict[str, str]] = []
    for row in rows[header_index + 1 :]:
        values = tuple("" if value is None else str(value).strip() for value in row)
        if not any(values):
            continue
        if len(values) > len(headers) and any(values[len(headers) :]):
            raise UniversalTableError("TABLE_ROW_COLUMN_OVERFLOW")
        padded = values[: len(headers)] + ("",) * max(0, len(headers) - len(values))
        records.append(dict(zip(headers, padded, strict=True)))
        if len(records) > _MAX_ROWS:
            raise UniversalTableError("TABLE_ROW_LIMIT_EXCEEDED")
    if not records:
        raise UniversalTableError("TABLE_DATA_ROWS_NOT_FOUND")
    return ExtractedTable(
        source_name=source_name,
        member_path=member_path,
        detected_format=detected_format,
        headers=headers,
        rows=tuple(records),
        source_sha256=sha256(payload).hexdigest(),
    )


def _xlsx_sheet_names(payload: bytes) -> tuple[str, ...]:
    _, workbook_payload = _extract_workbook(payload, _SAFE_LIMITS)
    with ZipFile(BytesIO(workbook_payload)) as archive:
        root = _xml_root(
            _read_limited(archive, "xl/workbook.xml", _SAFE_LIMITS),
            "UNIVERSAL_XLSX_WORKBOOK_INVALID",
        )
        sheets = root.find(f"{{{_SPREADSHEET_NS}}}sheets")
        if sheets is None:
            raise UniversalTableError("UNIVERSAL_XLSX_SHEETS_MISSING")
        names = tuple(
            str(sheet.get("name") or "").strip()
            for sheet in sheets.findall(f"{{{_SPREADSHEET_NS}}}sheet")
        )
    if not names or any(not name for name in names) or len(set(names)) != len(names):
        raise UniversalTableError("UNIVERSAL_XLSX_SHEETS_INVALID")
    return names


def _extract_xlsx(payload: bytes, source_name: str, member_path: str) -> list[ExtractedTable]:
    result: list[ExtractedTable] = []
    errors: list[str] = []
    for sheet_name in _xlsx_sheet_names(payload):
        try:
            indexed = _sheet_rows(payload, sheet_name=sheet_name, limits=_SAFE_LIMITS)
            rows = [values for _index, values in indexed]
            table = _rows_to_table(
                source_name=source_name,
                member_path=f"{member_path}#{sheet_name}",
                detected_format="XLSX",
                rows=rows,
                payload=payload,
            )
            result.append(table)
        except Exception as exc:
            errors.append(getattr(exc, "code", type(exc).__name__) + ":" + sheet_name)
    if not result:
        raise UniversalTableError(errors[0] if errors else "UNIVERSAL_XLSX_TABLE_NOT_FOUND")
    return result


def _extract_json(payload: bytes, source_name: str, member_path: str) -> list[ExtractedTable]:
    decoded = _decode_text(payload)
    if decoded is None:
        raise UniversalTableError("JSON_TEXT_DECODING_FAILED")
    try:
        value = json.loads(decoded[0])
    except json.JSONDecodeError as exc:
        raise UniversalTableError("JSON_INVALID") from exc
    candidates: list[tuple[str, list[Mapping[str, Any]]]] = []
    if isinstance(value, list) and value and all(isinstance(item, Mapping) for item in value):
        candidates.append((member_path, value))
    elif isinstance(value, Mapping):
        for key in ("data", "rows", "items", "result", "records"):
            nested = value.get(key)
            if isinstance(nested, list) and nested and all(isinstance(item, Mapping) for item in nested):
                candidates.append((member_path + "#" + key, nested))
    if not candidates:
        raise UniversalTableError("JSON_TABLE_NOT_FOUND")
    tables: list[ExtractedTable] = []
    for path, records in candidates:
        headers = tuple(dict.fromkeys(str(key) for record in records for key in record))
        if len(headers) < 2 or len(headers) > _MAX_COLUMNS:
            continue
        rows = [[record.get(header, "") for header in headers] for record in records]
        tables.append(_rows_to_table(
            source_name=source_name,
            member_path=path,
            detected_format="JSON_TABLE",
            rows=[headers, *rows],
            payload=payload,
        ))
    if not tables:
        raise UniversalTableError("JSON_TABLE_NOT_FOUND")
    return tables


def _extract_delimited(payload: bytes, source_name: str, member_path: str) -> list[ExtractedTable]:
    decoded = _decode_text(payload)
    if decoded is None:
        raise UniversalTableError("TEXT_DECODING_FAILED")
    text = decoded[0]
    sample = text[:256_000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        rows = list(csv.reader(StringIO(text), dialect))
    except csv.Error as exc:
        raise UniversalTableError("DELIMITED_TEXT_INVALID") from exc
    return [_rows_to_table(
        source_name=source_name,
        member_path=member_path,
        detected_format="DELIMITED_TEXT",
        rows=rows,
        payload=payload,
    )]


def _local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _extract_xml(payload: bytes, source_name: str, member_path: str) -> list[ExtractedTable]:
    decoded = _decode_text(payload)
    if decoded is None:
        raise UniversalTableError("XML_TEXT_DECODING_FAILED")
    upper = decoded[0].upper()
    if "<!DOCTYPE" in upper or "<!ENTITY" in upper:
        raise UniversalTableError("XML_ENTITY_DECLARATION_FORBIDDEN")
    try:
        root = ElementTree.fromstring(decoded[0])
    except ElementTree.ParseError as exc:
        raise UniversalTableError("XML_INVALID") from exc
    groups: dict[str, list[dict[str, str]]] = {}
    for parent in root.iter():
        children = list(parent)
        if len(children) < 2:
            continue
        child_tags = [_local_tag(child.tag) for child in children]
        if len(set(child_tags)) != 1:
            continue
        records: list[dict[str, str]] = []
        for child in children:
            fields: dict[str, str] = {}
            for node in list(child):
                if list(node):
                    fields = {}
                    break
                name = _local_tag(node.tag)
                if name in fields:
                    fields = {}
                    break
                fields[name] = (node.text or "").strip()
            if len(fields) >= 2:
                records.append(fields)
        if records:
            groups[_local_tag(children[0].tag)] = records
    if not groups:
        raise UniversalTableError("XML_TABLE_NOT_FOUND")
    tables: list[ExtractedTable] = []
    for name, records in groups.items():
        headers = tuple(dict.fromkeys(key for record in records for key in record))
        rows = [[record.get(header, "") for header in headers] for record in records]
        tables.append(_rows_to_table(
            source_name=source_name,
            member_path=member_path + "#" + name,
            detected_format="XML_TABLE",
            rows=[headers, *rows],
            payload=payload,
        ))
    return tables


def _is_xlsx(payload: bytes) -> bool:
    if not payload.startswith(b"PK\x03\x04"):
        return False
    try:
        with ZipFile(BytesIO(payload)) as archive:
            names = {info.filename.replace("\\", "/").casefold() for info in archive.infolist()}
    except BadZipFile:
        return False
    return _XLSX_REQUIRED.issubset(names)


def _detect_archive(payload: bytes, name: str) -> str | None:
    lower = name.casefold()
    if payload.startswith(b"PK\x03\x04") and not _is_xlsx(payload):
        return "ZIP"
    if payload.startswith(b"\x1f\x8b") or lower.endswith((".gz", ".tgz")):
        return "GZIP"
    if payload.startswith(b"BZh") or lower.endswith((".bz2", ".tbz", ".tbz2")):
        return "BZIP2"
    if payload.startswith(b"\xfd7zXZ\x00") or lower.endswith((".xz", ".txz")):
        return "XZ"
    try:
        with tarfile.open(fileobj=BytesIO(payload), mode="r:*"):
            return "TAR"
    except (OSError, tarfile.TarError):
        pass
    if payload.startswith(b"7z\xbc\xaf\x27\x1c"):
        return "7Z_UNSUPPORTED"
    if payload.startswith(b"Rar!\x1a\x07"):
        return "RAR_UNSUPPORTED"
    return None


def _direct_tables(payload: bytes, source_name: str, member_path: str) -> tuple[str, list[ExtractedTable]]:
    if _is_xlsx(payload):
        return "XLSX", _extract_xlsx(payload, source_name, member_path)
    stripped = payload.lstrip()
    if stripped.startswith((b"{", b"[")):
        return "JSON", _extract_json(payload, source_name, member_path)
    if stripped.startswith(b"<"):
        return "XML", _extract_xml(payload, source_name, member_path)
    # Content wins over the filename. A CSV renamed to .json or .bin is still
    # a delimited table; malformed JSON/XML that actually starts with its
    # structural marker remains a format error and is never reinterpreted.
    if _decode_text(payload) is not None:
        return "DELIMITED_TEXT", _extract_delimited(
            payload, source_name, member_path
        )
    raise UniversalTableError("NO_USABLE_TABLE_DATA")


def _zip_members(payload: bytes, source_name: str, member_path: str, depth: int, budget: ExtractionBudget) -> tuple[list[ExtractedTable], list[MemberResult]]:
    tables: list[ExtractedTable] = []
    members: list[MemberResult] = []
    try:
        archive = ZipFile(BytesIO(payload))
    except BadZipFile as exc:
        raise UniversalTableError("ARCHIVE_CORRUPTED") from exc
    with archive:
        infos = archive.infolist()
        if not infos:
            raise UniversalTableError("ARCHIVE_EMPTY")
        seen: set[str] = set()
        for info in infos:
            name = _safe_member_name(info.filename)
            key = name.casefold()
            if key in seen:
                raise UniversalTableError("ARCHIVE_DUPLICATE_PATH")
            seen.add(key)
            if info.flag_bits & 0x1:
                raise UniversalTableError("ARCHIVE_ENCRYPTED_ENTRY")
            if info.compress_type not in _ALLOWED_ZIP_METHODS:
                raise UniversalTableError("ARCHIVE_COMPRESSION_UNSUPPORTED")
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise UniversalTableError("ARCHIVE_SYMLINK_FORBIDDEN")
            if info.is_dir():
                continue
            if info.file_size > _MAX_MEMBER_BYTES:
                raise UniversalTableError("ARCHIVE_MEMBER_SIZE_EXCEEDED")
            if info.file_size and (
                info.compress_size == 0 or info.file_size > info.compress_size * _MAX_RATIO
            ):
                raise UniversalTableError("ARCHIVE_COMPRESSION_RATIO_EXCEEDED")
            budget.charge(info.file_size)
            try:
                child = archive.read(info)
            except Exception as exc:
                members.append(MemberResult(name, "FAILED", None, 0, ("ARCHIVE_MEMBER_READ_FAILED",)))
                continue
            full_path = member_path.rstrip("/") + "/" + name
            if _looks_executable(child[:4096], name):
                members.append(MemberResult(full_path, "QUARANTINED_SECURITY", "EXECUTABLE", 0, ("ARCHIVE_ACTIVE_CONTENT_FORBIDDEN",)))
                continue
            child_result = _extract_payload(child, source_name, full_path, depth + 1, budget)
            tables.extend(child_result.tables)
            members.extend(child_result.members or (
                MemberResult(full_path, child_result.status, child_result.detected_format, len(child_result.tables), child_result.reason_codes),
            ))
    return tables, members


def _tar_members(payload: bytes, source_name: str, member_path: str, depth: int, budget: ExtractionBudget) -> tuple[list[ExtractedTable], list[MemberResult]]:
    tables: list[ExtractedTable] = []
    members: list[MemberResult] = []
    try:
        archive = tarfile.open(fileobj=BytesIO(payload), mode="r:*")
    except tarfile.TarError as exc:
        raise UniversalTableError("ARCHIVE_CORRUPTED") from exc
    with archive:
        seen: set[str] = set()
        for info in archive:
            name = _safe_member_name(info.name)
            key = name.casefold()
            if key in seen:
                raise UniversalTableError("ARCHIVE_DUPLICATE_PATH")
            seen.add(key)
            if info.issym() or info.islnk():
                raise UniversalTableError("ARCHIVE_SYMLINK_FORBIDDEN")
            if info.isdir():
                continue
            if not info.isfile():
                raise UniversalTableError("ARCHIVE_MEMBER_TYPE_FORBIDDEN")
            budget.charge(info.size)
            stream = archive.extractfile(info)
            if stream is None:
                members.append(MemberResult(name, "FAILED", None, 0, ("ARCHIVE_MEMBER_READ_FAILED",)))
                continue
            child = stream.read(_MAX_MEMBER_BYTES + 1)
            if len(child) != info.size or len(child) > _MAX_MEMBER_BYTES:
                members.append(MemberResult(name, "FAILED", None, 0, ("ARCHIVE_MEMBER_READ_MISMATCH",)))
                continue
            full_path = member_path.rstrip("/") + "/" + name
            if _looks_executable(child[:4096], name):
                members.append(MemberResult(full_path, "QUARANTINED_SECURITY", "EXECUTABLE", 0, ("ARCHIVE_ACTIVE_CONTENT_FORBIDDEN",)))
                continue
            child_result = _extract_payload(child, source_name, full_path, depth + 1, budget)
            tables.extend(child_result.tables)
            members.extend(child_result.members or (
                MemberResult(full_path, child_result.status, child_result.detected_format, len(child_result.tables), child_result.reason_codes),
            ))
    return tables, members


def _single_compressed(payload: bytes, kind: str) -> bytes:
    try:
        if kind == "GZIP":
            value = gzip.decompress(payload)
        elif kind == "BZIP2":
            value = bz2.decompress(payload)
        else:
            value = lzma.decompress(payload)
    except (OSError, EOFError, ValueError, lzma.LZMAError) as exc:
        raise UniversalTableError("ARCHIVE_CORRUPTED") from exc
    if len(value) > _MAX_MEMBER_BYTES:
        raise UniversalTableError("ARCHIVE_MEMBER_SIZE_EXCEEDED")
    if len(payload) and len(value) > len(payload) * _MAX_RATIO:
        raise UniversalTableError("ARCHIVE_COMPRESSION_RATIO_EXCEEDED")
    return value


def _extract_payload(payload: bytes, source_name: str, member_path: str, depth: int, budget: ExtractionBudget) -> ExtractionResult:
    if depth > _MAX_DEPTH:
        return ExtractionResult("UNSUPPORTED", "ARCHIVE_DEPTH_LIMIT", (), (), ("ARCHIVE_RECURSION_LIMIT_REACHED",))
    if not payload:
        return ExtractionResult("UNSUPPORTED", "EMPTY", (), (), ("FILE_EMPTY",))
    if _looks_executable(payload[:4096], member_path):
        return ExtractionResult("QUARANTINED_SECURITY", "EXECUTABLE", (), (), ("EXECUTABLE_OR_SCRIPT_CONTENT",))
    archive_kind = _detect_archive(payload, member_path)
    if archive_kind in {"7Z_UNSUPPORTED", "RAR_UNSUPPORTED"}:
        return ExtractionResult("UNSUPPORTED", archive_kind, (), (), ("ARCHIVE_FORMAT_REQUIRES_OPTIONAL_ADAPTER",))
    if archive_kind is not None:
        try:
            if archive_kind == "ZIP":
                tables, members = _zip_members(payload, source_name, member_path, depth, budget)
            elif archive_kind == "TAR":
                tables, members = _tar_members(payload, source_name, member_path, depth, budget)
            else:
                child = _single_compressed(payload, archive_kind)
                budget.charge(len(child))
                lower = member_path.casefold()
                suffixes = {"GZIP": (".gz",), "BZIP2": (".bz2",), "XZ": (".xz",)}[archive_kind]
                child_name = member_path
                for suffix in suffixes:
                    if lower.endswith(suffix):
                        child_name = member_path[: -len(suffix)] or "compressed-member"
                        break
                child_result = _extract_payload(child, source_name, child_name, depth + 1, budget)
                tables = list(child_result.tables)
                members = list(child_result.members or (
                    MemberResult(child_name, child_result.status, child_result.detected_format, len(child_result.tables), child_result.reason_codes),
                ))
        except UniversalTableError as exc:
            return ExtractionResult("QUARANTINED_SECURITY" if any(token in exc.code for token in ("PATH", "SYMLINK", "ENCRYPTED", "COMPRESSION_RATIO", "ACTIVE_CONTENT")) else "QUARANTINED_CORRUPTED", archive_kind, (), (), (exc.code,))
        status = "COMPLETE" if tables and all(member.status == "COMPLETE" for member in members) else ("PARTIAL" if tables else "UNSUPPORTED")
        reasons = tuple(dict.fromkeys(code for member in members for code in member.reason_codes))
        return ExtractionResult(status, archive_kind, tuple(tables), tuple(members), reasons)
    try:
        detected, tables = _direct_tables(payload, source_name, member_path)
    except UniversalTableError as exc:
        return ExtractionResult("UNSUPPORTED", "UNMAPPED", (), (), (exc.code,))
    public_detected = tables[0].detected_format if len(tables) == 1 else detected
    return ExtractionResult("COMPLETE", public_detected, tuple(tables), (), ())


def extract_tables(payload: bytes, *, source_name: str) -> ExtractionResult:
    if not isinstance(payload, bytes) or not payload:
        raise UniversalTableError("FILE_BYTES_REQUIRED")
    if len(payload) > _MAX_TOTAL_BYTES:
        raise UniversalTableError("FILE_SIZE_EXCEEDED")
    return _extract_payload(payload, source_name, source_name, 0, ExtractionBudget())


__all__ = [
    "ExtractedTable",
    "ExtractionResult",
    "MemberResult",
    "UNIVERSAL_TABLE_SCHEMA_VERSION",
    "UniversalTableError",
    "extract_tables",
]
