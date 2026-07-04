from __future__ import annotations

from io import BytesIO
import re
from zipfile import BadZipFile, ZipFile
from zlib import error as ZlibError

from ._xlsx_archive import _read_limited, _xml_root
from ._xlsx_contracts import XlsxInspectionError, XlsxInspectionLimits

_LOCAL_HEADER = b"PK\x03\x04"
_LOCAL_FIXED_SIZE = 30
_XML_DECLARATION = re.compile(r"^\s*<\?xml(?:\s+[^?]*)?\?>", re.IGNORECASE)
_NAMESPACE_DECLARATION = re.compile(
    r"\sxmlns(?::(?P<prefix>[A-Za-z_][A-Za-z0-9_.-]*))?\s*=\s*"
    r"(?P<quote>[\"'])(?P<uri>[^\"']*)(?P=quote)",
)
_WORKSHEET_ROOT_START = re.compile(r"^\s*<worksheet\b[^>]*>", re.DOTALL)
_PREFIX = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
_GUID = re.compile(
    r"^\{[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-"
    r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}$"
)

_SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
_X14AC_NS = "http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac"
_XR_NS = "http://schemas.microsoft.com/office/spreadsheetml/2014/revision"

_WORKSHEET = f"{{{_SPREADSHEET_NS}}}worksheet"
_MC_IGNORABLE = f"{{{_MC_NS}}}Ignorable"
_XR_UID = f"{{{_XR_NS}}}uid"
_RICH_PROPERTIES = f"{{{_SPREADSHEET_NS}}}rPr"
_RICH_BOLD = f"{{{_SPREADSHEET_NS}}}b"
_RICH_ITALIC = f"{{{_SPREADSHEET_NS}}}i"


def _u16(payload: bytes, offset: int) -> int:
    return int.from_bytes(payload[offset : offset + 2], "little")


def validate_archive_extra_fields(payload: bytes) -> None:
    try:
        with ZipFile(BytesIO(payload)) as zf:
            for info in zf.infolist():
                if info.extra:
                    raise XlsxInspectionError(
                        "XLSX_ARCHIVE_POLYGLOT_FORBIDDEN"
                    )
                offset = info.header_offset
                if (
                    offset < 0
                    or offset + _LOCAL_FIXED_SIZE > len(payload)
                    or payload[offset : offset + 4] != _LOCAL_HEADER
                    or _u16(payload, offset + 28) != 0
                ):
                    raise XlsxInspectionError(
                        "XLSX_ARCHIVE_POLYGLOT_FORBIDDEN"
                    )
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


def _worksheet_namespace_bindings(payload: bytes) -> tuple[tuple[str | None, str], ...]:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise XlsxInspectionError("XLSX_XML_ENCODING_UNSUPPORTED") from exc
    without_declaration = _XML_DECLARATION.sub("", text, count=1)
    root_match = _WORKSHEET_ROOT_START.match(without_declaration)
    if root_match is None:
        raise XlsxInspectionError("XLSX_XML_NAMESPACE_UNMODELED")
    root_start = root_match.group(0)
    all_declarations = tuple(_NAMESPACE_DECLARATION.finditer(without_declaration))
    root_declarations = tuple(_NAMESPACE_DECLARATION.finditer(root_start))
    if len(all_declarations) != len(root_declarations):
        raise XlsxInspectionError("XLSX_XML_NAMESPACE_UNMODELED")
    bindings = tuple(
        (declaration.group("prefix"), declaration.group("uri"))
        for declaration in root_declarations
    )
    if len({prefix for prefix, _ in bindings}) != len(bindings):
        raise XlsxInspectionError("XLSX_XML_NAMESPACE_UNMODELED")
    return bindings


def _validate_ignorable(
    value: str | None,
    bindings: dict[str | None, str],
) -> None:
    if value is None:
        return
    if not value or value != value.strip():
        raise XlsxInspectionError("XLSX_WORKSHEET_ATTRIBUTE_VALUE_INVALID")
    tokens = value.split()
    if (
        not tokens
        or any(_PREFIX.fullmatch(token) is None for token in tokens)
        or any(token not in bindings for token in tokens)
    ):
        raise XlsxInspectionError("XLSX_XML_NAMESPACE_UNMODELED")


def _validate_worksheet_namespace_contract(
    payload: bytes,
) -> dict[str | None, str]:
    bindings = dict(_worksheet_namespace_bindings(payload))
    if bindings.get(None) != _SPREADSHEET_NS:
        raise XlsxInspectionError("XLSX_XML_NAMESPACE_UNMODELED")
    expected = {
        "mc": _MC_NS,
        "x14ac": _X14AC_NS,
        "xr": _XR_NS,
    }
    if any(
        prefix in bindings and bindings[prefix] != uri
        for prefix, uri in expected.items()
    ):
        raise XlsxInspectionError("XLSX_XML_NAMESPACE_UNMODELED")
    return bindings


def _validate_rich_property_cardinality(root) -> None:
    allowed_sequences = {
        (),
        (_RICH_BOLD,),
        (_RICH_ITALIC,),
        (_RICH_BOLD, _RICH_ITALIC),
    }
    for properties in root.iter(_RICH_PROPERTIES):
        sequence = tuple(child.tag for child in properties)
        if sequence not in allowed_sequences:
            raise XlsxInspectionError(
                "XLSX_RICH_TEXT_PROPERTIES_UNMODELED"
            )


def _validate_worksheet_semantics(
    root,
    bindings: dict[str | None, str],
) -> None:
    if root.tag != _WORKSHEET:
        raise XlsxInspectionError("XLSX_WORKSHEET_INVALID")
    if set(root.attrib) - {_MC_IGNORABLE, _XR_UID}:
        raise XlsxInspectionError("XLSX_WORKSHEET_ATTRIBUTE_UNMODELED")
    _validate_ignorable(root.get(_MC_IGNORABLE), bindings)
    uid = root.get(_XR_UID)
    if uid is not None and _GUID.fullmatch(uid) is None:
        raise XlsxInspectionError("XLSX_WORKSHEET_ATTRIBUTE_VALUE_INVALID")
    _validate_rich_property_cardinality(root)


def validate_workbook_r19_hardening(
    workbook: bytes,
    limits: XlsxInspectionLimits,
) -> None:
    try:
        with ZipFile(BytesIO(workbook)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                normalized = info.filename.replace("\\", "/").casefold()
                if normalized.startswith("xl/worksheets/") and normalized.endswith(
                    ".xml"
                ):
                    payload = _read_limited(zf, info.filename, limits)
                    bindings = _validate_worksheet_namespace_contract(payload)
                    root = _xml_root(payload, "XLSX_WORKSHEET_INVALID")
                    _validate_worksheet_semantics(root, bindings)
                elif normalized == "xl/sharedstrings.xml":
                    root = _xml_root(
                        _read_limited(zf, info.filename, limits),
                        "XLSX_SHARED_STRING_STRUCTURE_UNMODELED",
                    )
                    _validate_rich_property_cardinality(root)
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


__all__ = [
    "validate_archive_extra_fields",
    "validate_workbook_r19_hardening",
]
