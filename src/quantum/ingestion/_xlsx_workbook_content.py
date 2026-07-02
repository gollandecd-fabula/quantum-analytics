from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from zipfile import BadZipFile, ZipFile
from zlib import error as ZlibError

from ._xlsx_archive import _read_limited, _xml_root
from ._xlsx_contracts import XlsxInspectionError, XlsxInspectionLimits

_SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_OFFICE_RELATIONSHIP_NS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)
_WORKBOOK = f"{{{_SPREADSHEET_NS}}}workbook"
_SHEETS = f"{{{_SPREADSHEET_NS}}}sheets"
_SHEET = f"{{{_SPREADSHEET_NS}}}sheet"
_WORKBOOK_VIEW = f"{{{_SPREADSHEET_NS}}}workbookView"
_RELATIONSHIP_ID = f"{{{_OFFICE_RELATIONSHIP_NS}}}id"
_ALLOWED_TAGS = frozenset({
    _WORKBOOK,
    f"{{{_SPREADSHEET_NS}}}fileVersion",
    f"{{{_SPREADSHEET_NS}}}fileSharing",
    f"{{{_SPREADSHEET_NS}}}workbookPr",
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
    f"{{{_SPREADSHEET_NS}}}calcPr",
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
_ALLOWED_ATTRIBUTES = {
    tag: frozenset() for tag in _ALLOWED_TAGS
}
_ALLOWED_ATTRIBUTES[_SHEET] = frozenset({"name", "sheetId", "state", _RELATIONSHIP_ID})
_ALLOWED_ATTRIBUTES[_WORKBOOK_VIEW] = frozenset({"activeTab"})
_REQUIRED_SHEET_ATTRIBUTES = frozenset({"name", "sheetId", _RELATIONSHIP_ID})
_ALLOWED_SHEET_STATES = frozenset({"visible", "hidden", "veryHidden"})


def _has_text(value: str | None) -> bool:
    return value is not None and bool(value.strip())


def _validate_attributes(element) -> None:
    allowed = _ALLOWED_ATTRIBUTES[element.tag]
    if not set(element.attrib).issubset(allowed):
        raise XlsxInspectionError("XLSX_WORKBOOK_ATTRIBUTE_UNMODELED")
    if element.tag == _SHEET:
        if not _REQUIRED_SHEET_ATTRIBUTES.issubset(element.attrib):
            raise XlsxInspectionError("XLSX_WORKBOOK_ATTRIBUTE_UNMODELED")
        if not element.get("name", "").strip():
            raise XlsxInspectionError("XLSX_WORKBOOK_ATTRIBUTE_UNMODELED")
        sheet_id = element.get("sheetId", "")
        if not sheet_id.isdecimal() or int(sheet_id) < 1:
            raise XlsxInspectionError("XLSX_WORKBOOK_ATTRIBUTE_UNMODELED")
        state = element.get("state")
        if state is not None and state not in _ALLOWED_SHEET_STATES:
            raise XlsxInspectionError("XLSX_WORKBOOK_ATTRIBUTE_UNMODELED")
    elif element.tag == _WORKBOOK_VIEW:
        active_tab = element.get("activeTab")
        if active_tab is not None and (
            not active_tab.isdecimal() or int(active_tab) < 0
        ):
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
