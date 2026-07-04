from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import re
from zipfile import BadZipFile, ZipFile
from zlib import error as ZlibError

from ._xlsx_archive import _read_limited, _xml_root
from ._xlsx_contracts import XlsxInspectionError, XlsxInspectionLimits

_SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_OFFICE_RELATIONSHIP_NS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)
_MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
_WORKBOOK = f"{{{_SPREADSHEET_NS}}}workbook"
_SHEETS = f"{{{_SPREADSHEET_NS}}}sheets"
_SHEET = f"{{{_SPREADSHEET_NS}}}sheet"
_WORKBOOK_VIEW = f"{{{_SPREADSHEET_NS}}}workbookView"
_FILE_VERSION = f"{{{_SPREADSHEET_NS}}}fileVersion"
_WORKBOOK_PR = f"{{{_SPREADSHEET_NS}}}workbookPr"
_CALC_PR = f"{{{_SPREADSHEET_NS}}}calcPr"
_RELATIONSHIP_ID = f"{{{_OFFICE_RELATIONSHIP_NS}}}id"
_MC_IGNORABLE = f"{{{_MC_NS}}}Ignorable"
_ALLOWED_TAGS = frozenset({
    _WORKBOOK,
    _FILE_VERSION,
    f"{{{_SPREADSHEET_NS}}}fileSharing",
    _WORKBOOK_PR,
    f"{{{_SPREADSHEET_NS}}}workbookProtection",
    f"{{{_SPREADSHEET_NS}}}bookViews",
    _WORKBOOK_VIEW,
    _SHEETS,
    _SHEET,
    f"{{{_SPREADSHEET_NS}}}functionGroups",
    f"{{{_SPREADSHEET_NS}}}functionGroup",
    f"{{{_SPREADSHEET_NS}}}externalReferences",
    f"{{{_SPREADSHEET_NS}}}externalReference",
    f"{{{_SPREADSHEET_NS}}}definedNames",
    f"{{{_SPREADSHEET_NS}}}definedName",
    _CALC_PR,
    f"{{{_SPREADSHEET_NS}}}oleSize",
    f"{{{_SPREADSHEET_NS}}}customWorkbookViews",
    f"{{{_SPREADSHEET_NS}}}customWorkbookView",
    f"{{{_SPREADSHEET_NS}}}pivotCaches",
    f"{{{_SPREADSHEET_NS}}}pivotCache",
    f"{{{_SPREADSHEET_NS}}}smartTagPr",
    f"{{{_SPREADSHEET_NS}}}smartTagTypes",
    f"{{{_SPREADSHEET_NS}}}smartTagType",
    f"{{{_SPREADSHEET_NS}}}webPublishing",
    f"{{{_SPREADSHEET_NS}}}fileRecoveryPr",
    f"{{{_SPREADSHEET_NS}}}webPublishObjects",
    f"{{{_SPREADSHEET_NS}}}webPublishObject",
})
_REQUIRED_SHEET_ATTRIBUTES = frozenset({"name", "sheetId", _RELATIONSHIP_ID})
_ALLOWED_SHEET_STATES = frozenset({"visible", "hidden", "veryHidden"})
_BOOLEAN = frozenset({"0", "1", "true", "false"})
_UINT = re.compile(r"(?:0|[1-9][0-9]{0,9})")
_INT = re.compile(r"-?(?:0|[1-9][0-9]{0,9})")
_APP_NAME = re.compile(r"[A-Za-z0-9_.-]{1,32}")
_RELATIONSHIP = re.compile(r"rId[1-9][0-9]{0,5}")
_PREFIX = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*")


def _has_text(value: str | None) -> bool:
    return value is not None and bool(value.strip())


def _matches(pattern: re.Pattern[str], value: str) -> bool:
    return bool(value) and value == value.strip() and pattern.fullmatch(value) is not None


def _validate_ignorable(value: str | None) -> None:
    if value is None:
        return
    tokens = value.split()
    if (
        value != value.strip()
        or not tokens
        or any(_PREFIX.fullmatch(token) is None for token in tokens)
    ):
        raise XlsxInspectionError("XLSX_WORKBOOK_ATTRIBUTE_UNMODELED")


def _validate_attributes(element) -> None:
    attributes = element.attrib
    if element.tag == _WORKBOOK:
        if set(attributes) - {_MC_IGNORABLE}:
            raise XlsxInspectionError("XLSX_WORKBOOK_ATTRIBUTE_UNMODELED")
        _validate_ignorable(attributes.get(_MC_IGNORABLE))
        return
    if element.tag == _FILE_VERSION:
        if set(attributes) - {"appName", "lastEdited", "lowestEdited", "rupBuild"}:
            raise XlsxInspectionError("XLSX_WORKBOOK_ATTRIBUTE_UNMODELED")
        if "appName" in attributes and not _matches(_APP_NAME, attributes["appName"]):
            raise XlsxInspectionError("XLSX_WORKBOOK_ATTRIBUTE_UNMODELED")
        if any(
            not _matches(_UINT, value)
            for name, value in attributes.items()
            if name != "appName"
        ):
            raise XlsxInspectionError("XLSX_WORKBOOK_ATTRIBUTE_UNMODELED")
        return
    if element.tag == _WORKBOOK_PR:
        if set(attributes) - {"filterPrivacy", "defaultThemeVersion"}:
            raise XlsxInspectionError("XLSX_WORKBOOK_ATTRIBUTE_UNMODELED")
        if (
            "filterPrivacy" in attributes
            and attributes["filterPrivacy"] not in _BOOLEAN
        ):
            raise XlsxInspectionError("XLSX_WORKBOOK_ATTRIBUTE_UNMODELED")
        if (
            "defaultThemeVersion" in attributes
            and not _matches(_UINT, attributes["defaultThemeVersion"])
        ):
            raise XlsxInspectionError("XLSX_WORKBOOK_ATTRIBUTE_UNMODELED")
        return
    if element.tag == _WORKBOOK_VIEW:
        if set(attributes) - {
            "activeTab",
            "xWindow",
            "yWindow",
            "windowWidth",
            "windowHeight",
        }:
            raise XlsxInspectionError("XLSX_WORKBOOK_ATTRIBUTE_UNMODELED")
        if any(
            not _matches(_UINT, attributes[name])
            for name in ("activeTab", "windowWidth", "windowHeight")
            if name in attributes
        ):
            raise XlsxInspectionError("XLSX_WORKBOOK_ATTRIBUTE_UNMODELED")
        if any(
            not _matches(_INT, attributes[name])
            for name in ("xWindow", "yWindow")
            if name in attributes
        ):
            raise XlsxInspectionError("XLSX_WORKBOOK_ATTRIBUTE_UNMODELED")
        return
    if element.tag == _SHEET:
        if set(attributes) - {"name", "sheetId", "state", _RELATIONSHIP_ID}:
            raise XlsxInspectionError("XLSX_WORKBOOK_ATTRIBUTE_UNMODELED")
        if not _REQUIRED_SHEET_ATTRIBUTES.issubset(attributes):
            raise XlsxInspectionError("XLSX_WORKBOOK_ATTRIBUTE_UNMODELED")
        if not element.get("name", "").strip():
            raise XlsxInspectionError("XLSX_WORKBOOK_ATTRIBUTE_UNMODELED")
        if not _matches(_UINT, element.get("sheetId", "")) or int(
            element.get("sheetId", "0")
        ) < 1:
            raise XlsxInspectionError("XLSX_WORKBOOK_ATTRIBUTE_UNMODELED")
        if not _matches(_RELATIONSHIP, element.get(_RELATIONSHIP_ID, "")):
            raise XlsxInspectionError("XLSX_WORKBOOK_ATTRIBUTE_UNMODELED")
        state = element.get("state")
        if state is not None and state not in _ALLOWED_SHEET_STATES:
            raise XlsxInspectionError("XLSX_WORKBOOK_ATTRIBUTE_UNMODELED")
        return
    if element.tag == _CALC_PR:
        if set(attributes) - {"calcId"}:
            raise XlsxInspectionError("XLSX_WORKBOOK_ATTRIBUTE_UNMODELED")
        if "calcId" in attributes and not _matches(_UINT, attributes["calcId"]):
            raise XlsxInspectionError("XLSX_WORKBOOK_ATTRIBUTE_UNMODELED")
        return
    if attributes:
        raise XlsxInspectionError("XLSX_WORKBOOK_ATTRIBUTE_UNMODELED")


def _validate_workbook_root(root) -> None:
    if root.tag != _WORKBOOK:
        raise XlsxInspectionError("XLSX_WORKBOOK_INVALID")
    for element in root.iter():
        if element.tag not in _ALLOWED_TAGS:
            raise XlsxInspectionError("XLSX_WORKBOOK_ELEMENT_UNMODELED")
        if _has_text(element.text) or _has_text(element.tail):
            raise XlsxInspectionError("XLSX_WORKBOOK_TEXT_UNMODELED")
        _validate_attributes(element)
    sheets = [child for child in root if child.tag == _SHEETS]
    if len(sheets) != 1:
        raise XlsxInspectionError("XLSX_SHEETS_MISSING")
    if not list(sheets[0]) or any(child.tag != _SHEET for child in sheets[0]):
        raise XlsxInspectionError("XLSX_WORKBOOK_ELEMENT_UNMODELED")


def validate_workbook_xml_content(
    workbook: bytes,
    limits: XlsxInspectionLimits,
) -> tuple[str, str, int]:
    try:
        with ZipFile(BytesIO(workbook)) as zf:
            payload = _read_limited(zf, "xl/workbook.xml", limits)
            root = _xml_root(payload, "XLSX_WORKBOOK_INVALID")
            _validate_workbook_root(root)
            return (
                "xl/workbook.xml",
                sha256(payload).hexdigest(),
                len(payload),
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


__all__ = ["validate_workbook_xml_content"]
