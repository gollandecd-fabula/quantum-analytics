from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from zipfile import BadZipFile, ZipFile
from zlib import error as ZlibError

from ._xlsx_archive import _read_limited, _xml_root
from ._xlsx_contracts import XlsxInspectionError, XlsxInspectionLimits

_SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_XML_NS = "http://www.w3.org/XML/1998/namespace"
_MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
_WORKSHEET = f"{{{_SPREADSHEET_NS}}}worksheet"
_SHEET_DATA = f"{{{_SPREADSHEET_NS}}}sheetData"
_ROW = f"{{{_SPREADSHEET_NS}}}row"
_CELL = f"{{{_SPREADSHEET_NS}}}c"
_FORMULA = f"{{{_SPREADSHEET_NS}}}f"
_VALUE = f"{{{_SPREADSHEET_NS}}}v"
_INLINE = f"{{{_SPREADSHEET_NS}}}is"
_SHARED_ROOT = f"{{{_SPREADSHEET_NS}}}sst"
_SHARED_ITEM = f"{{{_SPREADSHEET_NS}}}si"
_TEXT = f"{{{_SPREADSHEET_NS}}}t"
_RICH_RUN = f"{{{_SPREADSHEET_NS}}}r"
_RICH_PROPERTIES = f"{{{_SPREADSHEET_NS}}}rPr"

_ALLOWED_WORKSHEET_STRUCTURE_TAGS = frozenset({
    f"{{{_SPREADSHEET_NS}}}sheetPr",
    f"{{{_SPREADSHEET_NS}}}outlinePr",
    f"{{{_SPREADSHEET_NS}}}pageSetUpPr",
    f"{{{_SPREADSHEET_NS}}}dimension",
    f"{{{_SPREADSHEET_NS}}}sheetViews",
    f"{{{_SPREADSHEET_NS}}}sheetView",
    f"{{{_SPREADSHEET_NS}}}pane",
    f"{{{_SPREADSHEET_NS}}}selection",
    f"{{{_SPREADSHEET_NS}}}sheetFormatPr",
    f"{{{_SPREADSHEET_NS}}}cols",
    f"{{{_SPREADSHEET_NS}}}col",
    f"{{{_SPREADSHEET_NS}}}mergeCells",
    f"{{{_SPREADSHEET_NS}}}mergeCell",
    f"{{{_SPREADSHEET_NS}}}printOptions",
    f"{{{_SPREADSHEET_NS}}}pageMargins",
    f"{{{_SPREADSHEET_NS}}}pageSetup",
    f"{{{_SPREADSHEET_NS}}}sheetProtection",
    f"{{{_SPREADSHEET_NS}}}phoneticPr",
})
_ALLOWED_RICH_PROPERTY_TAGS = frozenset({
    f"{{{_SPREADSHEET_NS}}}rFont",
    f"{{{_SPREADSHEET_NS}}}charset",
    f"{{{_SPREADSHEET_NS}}}family",
    f"{{{_SPREADSHEET_NS}}}b",
    f"{{{_SPREADSHEET_NS}}}i",
    f"{{{_SPREADSHEET_NS}}}strike",
    f"{{{_SPREADSHEET_NS}}}outline",
    f"{{{_SPREADSHEET_NS}}}shadow",
    f"{{{_SPREADSHEET_NS}}}condense",
    f"{{{_SPREADSHEET_NS}}}extend",
    f"{{{_SPREADSHEET_NS}}}color",
    f"{{{_SPREADSHEET_NS}}}sz",
    f"{{{_SPREADSHEET_NS}}}u",
    f"{{{_SPREADSHEET_NS}}}vertAlign",
    f"{{{_SPREADSHEET_NS}}}scheme",
})
_ALLOWED_WORKSHEET_ATTRIBUTES = frozenset({f"{{{_MC_NS}}}Ignorable"})
_ALLOWED_ROW_ATTRIBUTES = frozenset({
    "r",
    "spans",
    "s",
    "customFormat",
    "ht",
    "hidden",
    "customHeight",
    "outlineLevel",
    "collapsed",
    "thickTop",
    "thickBot",
    "ph",
})
_ALLOWED_CELL_ATTRIBUTES = frozenset({"r", "s", "t"})
_ALLOWED_FORMULA_ATTRIBUTES = frozenset({
    "t",
    "ref",
    "si",
    "ca",
    "dt2D",
    "dtr",
    "del1",
    "del2",
    "r1",
    "r2",
    "bx",
})
_ALLOWED_TEXT_ATTRIBUTES = frozenset({f"{{{_XML_NS}}}space"})
_ALLOWED_RICH_PROPERTY_ATTRIBUTES = frozenset({
    "val",
    "rgb",
    "theme",
    "tint",
    "indexed",
    "auto",
})
_AUXILIARY_PARTS = frozenset({
    "docprops/app.xml",
    "docprops/core.xml",
    "xl/styles.xml",
    "xl/theme/theme1.xml",
})


def _has_text(value: str | None) -> bool:
    return value is not None and bool(value.strip())


def _require_attributes(element, allowed: frozenset[str], code: str) -> None:
    if any(name not in allowed for name in element.attrib):
        raise XlsxInspectionError(code)


def _require_whitespace_only(element, code: str) -> None:
    if _has_text(element.text) or _has_text(element.tail):
        raise XlsxInspectionError(code)


def _validate_text_node(element, code: str) -> None:
    if element.tag != _TEXT or list(element) or _has_text(element.tail):
        raise XlsxInspectionError(code)
    _require_attributes(element, _ALLOWED_TEXT_ATTRIBUTES, code)


def _validate_rich_properties(element, code: str) -> None:
    if element.tag != _RICH_PROPERTIES or element.attrib:
        raise XlsxInspectionError(code)
    _require_whitespace_only(element, code)
    for child in element:
        if child.tag not in _ALLOWED_RICH_PROPERTY_TAGS:
            raise XlsxInspectionError(code)
        _require_attributes(child, _ALLOWED_RICH_PROPERTY_ATTRIBUTES, code)
        if list(child) or _has_text(child.text) or _has_text(child.tail):
            raise XlsxInspectionError(code)


def _validate_rich_run(element, code: str) -> None:
    if element.tag != _RICH_RUN or element.attrib:
        raise XlsxInspectionError(code)
    _require_whitespace_only(element, code)
    children = list(element)
    if not children:
        raise XlsxInspectionError(code)
    if children[0].tag == _RICH_PROPERTIES:
        _validate_rich_properties(children[0], code)
        children = children[1:]
    if len(children) != 1:
        raise XlsxInspectionError(code)
    _validate_text_node(children[0], code)


def _validate_string_container(element, code: str) -> None:
    if element.attrib:
        raise XlsxInspectionError(code)
    _require_whitespace_only(element, code)
    children = list(element)
    if not children:
        raise XlsxInspectionError(code)
    if len(children) == 1 and children[0].tag == _TEXT:
        _validate_text_node(children[0], code)
        return
    if any(child.tag != _RICH_RUN for child in children):
        raise XlsxInspectionError(code)
    for child in children:
        _validate_rich_run(child, code)


def _validate_cell_content(cell) -> None:
    _require_attributes(cell, _ALLOWED_CELL_ATTRIBUTES, "XLSX_CELL_ATTRIBUTE_UNMODELED")
    if _has_text(cell.text) or _has_text(cell.tail):
        raise XlsxInspectionError("XLSX_SHEET_DATA_CONTENT_UNMODELED")
    for child in cell:
        if child.tag == _FORMULA:
            _require_attributes(
                child,
                _ALLOWED_FORMULA_ATTRIBUTES,
                "XLSX_SHEET_DATA_CONTENT_UNMODELED",
            )
            if list(child) or _has_text(child.tail):
                raise XlsxInspectionError("XLSX_SHEET_DATA_CONTENT_UNMODELED")
        elif child.tag == _VALUE:
            if child.attrib or list(child) or _has_text(child.tail):
                raise XlsxInspectionError("XLSX_SHEET_DATA_CONTENT_UNMODELED")
        elif child.tag == _INLINE:
            _validate_string_container(
                child,
                "XLSX_INLINE_STRING_STRUCTURE_UNMODELED",
            )
        else:
            raise XlsxInspectionError("XLSX_CELL_CHILD_UNMODELED")


def _validate_non_sheet_data_child(child) -> None:
    elements = tuple(child.iter())
    if any(_has_text(element.text) or _has_text(element.tail) for element in elements):
        raise XlsxInspectionError("XLSX_UNMODELED_WORKSHEET_TEXT")
    if any(element.tag not in _ALLOWED_WORKSHEET_STRUCTURE_TAGS for element in elements):
        raise XlsxInspectionError("XLSX_WORKSHEET_ELEMENT_UNMODELED")


def _validate_worksheet_root(root) -> None:
    if root.tag != _WORKSHEET or _has_text(root.text) or _has_text(root.tail):
        raise XlsxInspectionError("XLSX_UNMODELED_WORKSHEET_TEXT")
    _require_attributes(
        root,
        _ALLOWED_WORKSHEET_ATTRIBUTES,
        "XLSX_WORKSHEET_ATTRIBUTE_UNMODELED",
    )
    sheet_data_nodes = [child for child in root if child.tag == _SHEET_DATA]
    if len(sheet_data_nodes) != 1:
        raise XlsxInspectionError("XLSX_SHEET_DATA_STRUCTURE_INVALID")
    sheet_data = sheet_data_nodes[0]

    for child in root:
        if child is sheet_data:
            continue
        if child.tag in {_ROW, _CELL}:
            continue
        _validate_non_sheet_data_child(child)

    if sheet_data.attrib or _has_text(sheet_data.text) or _has_text(sheet_data.tail):
        raise XlsxInspectionError("XLSX_SHEET_DATA_CONTENT_UNMODELED")
    for row in sheet_data:
        if row.tag == _CELL:
            continue
        if row.tag != _ROW:
            raise XlsxInspectionError("XLSX_SHEET_DATA_CHILD_UNMODELED")
        _require_attributes(row, _ALLOWED_ROW_ATTRIBUTES, "XLSX_ROW_ATTRIBUTE_UNMODELED")
        if _has_text(row.text) or _has_text(row.tail):
            raise XlsxInspectionError("XLSX_SHEET_DATA_CONTENT_UNMODELED")
        for cell in row:
            if cell.tag != _CELL:
                if any(
                    _has_text(element.text) or _has_text(element.tail)
                    for element in cell.iter()
                ):
                    raise XlsxInspectionError("XLSX_SHEET_DATA_CONTENT_UNMODELED")
                raise XlsxInspectionError("XLSX_ROW_CHILD_UNMODELED")
            _validate_cell_content(cell)


def _validate_shared_strings(root) -> None:
    if root.tag != _SHARED_ROOT or _has_text(root.text) or _has_text(root.tail):
        raise XlsxInspectionError("XLSX_SHARED_STRING_STRUCTURE_UNMODELED")
    _require_attributes(
        root,
        frozenset({"count", "uniqueCount"}),
        "XLSX_SHARED_STRING_STRUCTURE_UNMODELED",
    )
    for item in root:
        if item.tag != _SHARED_ITEM:
            raise XlsxInspectionError("XLSX_SHARED_STRING_STRUCTURE_UNMODELED")
        _validate_string_container(
            item,
            "XLSX_SHARED_STRING_STRUCTURE_UNMODELED",
        )


def validate_modeled_xml_content(
    workbook: bytes,
    limits: XlsxInspectionLimits,
) -> tuple[tuple[str, str, int], ...]:
    auxiliary: list[tuple[str, str, int]] = []
    try:
        with ZipFile(BytesIO(workbook)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                normalized = info.filename.replace("\\", "/").casefold()
                if normalized.startswith("xl/worksheets/") and normalized.endswith(
                    ".xml"
                ):
                    root = _xml_root(
                        _read_limited(zf, info.filename, limits),
                        "XLSX_WORKSHEET_INVALID",
                    )
                    _validate_worksheet_root(root)
                elif normalized == "xl/sharedstrings.xml":
                    root = _xml_root(
                        _read_limited(zf, info.filename, limits),
                        "XLSX_SHARED_STRINGS_INVALID",
                    )
                    _validate_shared_strings(root)
                elif normalized in _AUXILIARY_PARTS:
                    payload = _read_limited(zf, info.filename, limits)
                    _xml_root(payload, "XLSX_AUXILIARY_PART_INVALID")
                    auxiliary.append(
                        (normalized, sha256(payload).hexdigest(), len(payload))
                    )
        return tuple(sorted(auxiliary))
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


__all__ = ["validate_modeled_xml_content"]
