from __future__ import annotations

from io import BytesIO
from pathlib import PurePosixPath
import re
import stat
import unicodedata
from xml.etree import ElementTree
from zlib import error as ZlibError
from zipfile import BadZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

from ._xlsx_contracts import XlsxInspectionError, XlsxInspectionLimits

_CELL_REFERENCE = re.compile(r"^([A-Z]+)([1-9][0-9]*)$")
_XLSX_REQUIRED_PARTS = {
    "[Content_Types].xml",
    "_rels/.rels",
    "xl/workbook.xml",
    "xl/_rels/workbook.xml.rels",
}
_BLOCKED_SUFFIXES = (
    ".exe", ".dll", ".com", ".scr", ".js", ".jse", ".vbs", ".vbe",
    ".ps1", ".bat", ".cmd", ".sh", ".py", ".jar", ".msi",
)
_BLOCKED_PATH_MARKERS = (
    "xl/activex/", "xl/embeddings/", "xl/externallinks/",
    "customui/", "vbaproject.bin",
)
_XML_DECLARATION_MARKERS = ("<!DOCTYPE", "<!ENTITY")
_SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_ALLOWED_COMPRESSION_METHODS = {ZIP_STORED, ZIP_DEFLATED}


def _reject_xml_declarations(payload: bytes) -> None:
    if payload.startswith((b"\xff\xfe", b"\xfe\xff", b"\x00\x00\xfe\xff", b"\xff\xfe\x00\x00")):
        raise XlsxInspectionError("XLSX_XML_ENCODING_UNSUPPORTED")
    try:
        decoded = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise XlsxInspectionError("XLSX_XML_ENCODING_UNSUPPORTED") from exc
    upper = decoded.replace("\x00", "").upper()
    if any(marker in upper for marker in _XML_DECLARATION_MARKERS):
        raise XlsxInspectionError("XLSX_XML_ENTITY_DECLARATION_FORBIDDEN")
    if "\x00" in decoded:
        raise XlsxInspectionError("XLSX_XML_ENCODING_UNSUPPORTED")


def _safe_member_name(name: str) -> str:
    if not isinstance(name, str) or not name or "\x00" in name:
        raise XlsxInspectionError("XLSX_ARCHIVE_PATH_INVALID")
    normalized = name.replace("\\", "/")
    if normalized.startswith("//") or re.match(r"^[A-Za-z]:", normalized):
        raise XlsxInspectionError("XLSX_ARCHIVE_PATH_INVALID")
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise XlsxInspectionError("XLSX_ARCHIVE_PATH_INVALID")
    canonical = unicodedata.normalize("NFC", str(path))
    if any(":" in part for part in PurePosixPath(canonical).parts):
        raise XlsxInspectionError("XLSX_ARCHIVE_PATH_INVALID")
    return canonical


def _is_symlink(info: ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(mode)


def _validate_archive(zf: ZipFile, limits: XlsxInspectionLimits) -> dict[str, ZipInfo]:
    infos = zf.infolist()
    if len(infos) > limits.max_archive_entries:
        raise XlsxInspectionError("XLSX_ARCHIVE_ENTRY_LIMIT_EXCEEDED")
    normalized: dict[str, ZipInfo] = {}
    total_uncompressed = 0
    for info in infos:
        name = _safe_member_name(info.filename)
        key = unicodedata.normalize("NFC", name).casefold()
        if key in normalized:
            raise XlsxInspectionError("XLSX_ARCHIVE_DUPLICATE_PATH")
        normalized[key] = info
        if info.flag_bits & 0x1:
            raise XlsxInspectionError("XLSX_ARCHIVE_ENCRYPTED_ENTRY")
        if info.compress_type not in _ALLOWED_COMPRESSION_METHODS:
            raise XlsxInspectionError("XLSX_ARCHIVE_COMPRESSION_UNSUPPORTED")
        if _is_symlink(info):
            raise XlsxInspectionError("XLSX_ARCHIVE_SYMLINK_FORBIDDEN")
        if info.file_size > limits.max_entry_uncompressed_bytes:
            raise XlsxInspectionError("XLSX_ARCHIVE_ENTRY_SIZE_EXCEEDED")
        total_uncompressed += info.file_size
        if total_uncompressed > limits.max_total_uncompressed_bytes:
            raise XlsxInspectionError("XLSX_ARCHIVE_TOTAL_SIZE_EXCEEDED")
        if info.file_size > 0:
            if info.compress_size == 0:
                raise XlsxInspectionError("XLSX_ARCHIVE_COMPRESSION_RATIO_EXCEEDED")
            if info.file_size > info.compress_size * limits.max_compression_ratio:
                raise XlsxInspectionError("XLSX_ARCHIVE_COMPRESSION_RATIO_EXCEEDED")
        lower = name.casefold()
        if lower.endswith(_BLOCKED_SUFFIXES) or any(marker in lower for marker in _BLOCKED_PATH_MARKERS):
            raise XlsxInspectionError("XLSX_ACTIVE_CONTENT_FORBIDDEN")
    return normalized


def _read_limited(zf: ZipFile, name: str, limits: XlsxInspectionLimits) -> bytes:
    try:
        info = zf.getinfo(name)
    except KeyError as exc:
        raise XlsxInspectionError("XLSX_REQUIRED_PART_MISSING") from exc
    if info.file_size > limits.max_xml_bytes:
        raise XlsxInspectionError("XLSX_XML_SIZE_EXCEEDED")
    try:
        payload = zf.read(info)
    except (
        BadZipFile,
        RuntimeError,
        NotImplementedError,
        OSError,
        EOFError,
        ZlibError,
    ) as exc:
        raise XlsxInspectionError("XLSX_ARCHIVE_READ_FAILED") from exc
    if len(payload) != info.file_size:
        raise XlsxInspectionError("XLSX_ARCHIVE_READ_MISMATCH")
    _reject_xml_declarations(payload)
    return payload


def _xml_root(payload: bytes, code: str) -> ElementTree.Element:
    try:
        return ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise XlsxInspectionError(code) from exc


def _cell_position(reference: str) -> tuple[int, int]:
    match = _CELL_REFERENCE.fullmatch(reference)
    if match is None:
        raise XlsxInspectionError("XLSX_CELL_REFERENCE_INVALID")
    column = 0
    for char in match.group(1):
        column = column * 26 + ord(char) - 64
    return column, int(match.group(2))


def _relationship_target(target: str) -> str:
    normalized = target.replace("\\", "/")
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", normalized):
        raise XlsxInspectionError("XLSX_RELATIONSHIP_TARGET_INVALID")
    if normalized.startswith("/"):
        normalized = normalized.removeprefix("/")
    elif not normalized.startswith("xl/"):
        normalized = f"xl/{normalized}"
    path = PurePosixPath(normalized)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise XlsxInspectionError("XLSX_RELATIONSHIP_TARGET_INVALID")
    return str(path)


def _shared_strings(zf: ZipFile, limits: XlsxInspectionLimits) -> tuple[str, ...]:
    try:
        payload = _read_limited(zf, "xl/sharedStrings.xml", limits)
    except XlsxInspectionError as exc:
        if exc.code == "XLSX_REQUIRED_PART_MISSING":
            return ()
        raise
    root = _xml_root(payload, "XLSX_SHARED_STRINGS_INVALID")
    values: list[str] = []
    for item in root.findall(f"{{{_SPREADSHEET_NS}}}si"):
        text = "".join(node.text or "" for node in item.iter(f"{{{_SPREADSHEET_NS}}}t"))
        values.append(text)
    return tuple(values)


def _cell_text(cell: ElementTree.Element, shared: tuple[str, ...]) -> str:
    cell_type = cell.get("t")
    if cell_type == "inlineStr":
        inline = cell.find(f"{{{_SPREADSHEET_NS}}}is")
        if inline is None:
            return ""
        return "".join(node.text or "" for node in inline.iter(f"{{{_SPREADSHEET_NS}}}t"))
    value = cell.find(f"{{{_SPREADSHEET_NS}}}v")
    raw = value.text if value is not None and value.text is not None else ""
    if cell_type == "s":
        try:
            index = int(raw)
            return shared[index]
        except (ValueError, IndexError) as exc:
            raise XlsxInspectionError("XLSX_SHARED_STRING_REFERENCE_INVALID") from exc
    return raw


def _extract_workbook(
    payload: bytes,
    limits: XlsxInspectionLimits,
) -> tuple[str, bytes]:
    if len(payload) > limits.max_file_bytes:
        raise XlsxInspectionError("XLSX_FILE_SIZE_EXCEEDED")
    try:
        with ZipFile(BytesIO(payload)) as zf:
            names = _validate_archive(zf, limits)
            if {item.casefold() for item in _XLSX_REQUIRED_PARTS}.issubset(names):
                return "XLSX", payload
            files = [info for info in zf.infolist() if not info.is_dir()]
            workbook_entries = [info for info in files if info.filename.casefold().endswith(".xlsx")]
            if len(files) != 1 or len(workbook_entries) != 1:
                raise XlsxInspectionError("XLSX_OUTER_ARCHIVE_CONTENT_INVALID")
            workbook_info = workbook_entries[0]
            try:
                workbook = zf.read(workbook_info)
            except (
                BadZipFile,
                RuntimeError,
                NotImplementedError,
                OSError,
                EOFError,
                ZlibError,
            ) as exc:
                raise XlsxInspectionError("XLSX_ARCHIVE_READ_FAILED") from exc
            if len(workbook) != workbook_info.file_size:
                raise XlsxInspectionError("XLSX_ARCHIVE_READ_MISMATCH")
            return "ZIP_XLSX", workbook
    except XlsxInspectionError:
        raise
    except (
        BadZipFile,
        NotImplementedError,
        ValueError,
        OSError,
        EOFError,
        ZlibError,
    ) as exc:
        raise XlsxInspectionError("XLSX_ARCHIVE_INVALID") from exc
