from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from zipfile import BadZipFile, ZipFile
from zlib import error as ZlibError

from ._xlsx_archive import _read_limited, _xml_root
from ._xlsx_contracts import XlsxInspectionError, XlsxInspectionLimits

_SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_WORKBOOK = f"{{{_SPREADSHEET_NS}}}workbook"
_SHEETS = f"{{{_SPREADSHEET_NS}}}sheets"
_SHEET = f"{{{_SPREADSHEET_NS}}}sheet"
_ALLOWED_TAGS = frozenset({
    _WORKBOOK,
    f"{{{_SPREADSHEET_NS}}}fileVersion",
    f"{{{_SPREADSHEET_NS}}}fileSharing",
    f"{{{_SPREADSHEET_NS}}}workbookPr",
    f"{{{_SPREADSHEET_NS}}}workbookProtection",
    f"{{{_SPREADSHEET_NS}}}bookViews",
    f"{{{_SPREADSHEET_NS}}}workbookView",
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


def _has_text(value: str | None) -> bool:
    return value is not None and bool(value.strip())


def _validate_workbook_root(root) -> None:
    if root.tag != _WORKBOOK:
        raise XlsxInspectionError("XLSX_WORKBOOK_INVALID")
    for element in root.iter():
        if element.tag not in _ALLOWED_TAGS:
            raise XlsxInspectionError("XLSX_WORKBOOK_ELEMENT_UNMODELED")
        if _has_text(element.text) or _has_text(element.tail):
            raise XlsxInspectionError("XLSX_WORKBOOK_TEXT_UNMODELED")
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
