from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile
from zlib import error as ZlibError

from ._xlsx_archive import _SPREADSHEET_NS, _read_limited, _xml_root
from ._xlsx_contracts import XlsxInspectionError, XlsxInspectionLimits

_XML_NS = "http://www.w3.org/XML/1998/namespace"
_MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
_WORKSHEET = f"{{{_SPREADSHEET_NS}}}worksheet"
_SHEET_DATA = f"{{{_SPREADSHEET_NS}}}sheetData"
_ROW = f"{{{_SPREADSHEET_NS}}}row"
_CELL = f"{{{_SPREADSHEET_NS}}}c"
_FORMULA = f"{{{_SPREADSHEET_NS}}}f"
_VALUE = f"{{{_SPREADSHEET_NS}}}v"
_INLINE = f"{{{_SPREADSHEET_NS}}}is"
_TEXT = f"{{{_SPREADSHEET_NS}}}t"
_SHARED_ROOT = f"{{{_SPREADSHEET_NS}}}sst"
_SHARED_ITEM = f"{{{_SPREADSHEET_NS}}}si"

_ALLOWED_WORKSHEET_STRUCTURE_TAGS = frozenset({
    "sheetPr",
    "outlinePr",
    "pageSetUpPr",
    "dimension",
    "sheetViews",
    "sheetView",
    "pane",
    "selection",
    "sheetFormatPr",
    "cols",
    "col",
    "mergeCells",
    "mergeCell",
    "printOptions",
    "pageMargins",
    "pageSetup",
    "sheetProtection",
    "phoneticPr",
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
_ALLOWED_TEXT_ATTRIBUTES = frozenset({f"{{{_XML_NS}}}space"})
_ALLOWED_SHARED_ROOT_ATTRIBUTES = frozenset({"count", "uniqueCount"})
_AUXILIARY_PARTS = frozenset({
    "docprops/app.xml",
    "docprops/core.xml",
    "xl/styles.xml",
    "xl/theme/theme1.xml",
})


def _has_text(value: str | None) -> bool:
    return value is not None and bool(value.strip())


def _local_name(tag: object) -> str:
    prefix = f"{{{_SPREADSHEET_NS}}}"
    if not isinstance(tag, str) or not tag.startswith(prefix):
        raise XlsxInspectionError("XLSX_WORKSHEET_ELEMENT_UNMODELED")
    return tag[len(prefix):]


def _require_attributes(
    element: ElementTree.Element,
    allowed: frozenset[str],
    code: str,
) -> None:
    if any(name not in allowed for name in element.attrib):
        raise XlsxInspectionError(code)


def _require_text_free_subtree(
    element: ElementTree.Element,
    *,
    allowed_tags: frozenset[str],
) -> None:
    for candidate in element.iter():
        if _has_text(candidate.text) or _has_text(candidate.tail):
            raise XlsxInspectionError("XLSX_UNMODELED_WORKSHEET_TEXT")
        if _local_name(candidate.tag) not in allowed_tags:
            raise XlsxInspectionError("XLSX_WORKSHEET_ELEMENT_UNMODELED")


def _validate_simple_text_container(
    container: ElementTree.Element,
    *,
    code: str,
) -> None:
    if container.attrib or _has_text(container.text):
        raise XlsxInspectionError(code)
    children = list(container)
    if not children:
        raise XlsxInspectionError(code)
    for child in children:
        if child.tag != _TEXT or list(child):
            raise XlsxInspectionError(code)
        _require_attributes(child, _ALLOWED_TEXT_ATTRIBUTES, code)
        if _has_text(child.tail):
            raise XlsxInspectionError(code)


def _validate_cell_content(cell: ElementTree.Element) -> None:
    _require_attributes(cell, _ALLOWED_CELL_ATTRIBUTES, "XLSX_CELL_ATTRIBUTE_UNMODELED")
    if _has_text(cell.text) or _has_text(cell.tail):
        raise XlsxInspectionError("XLSX_CELL_TEXT_UNMODELED")
    for child in cell:
        if _has_text(child.tail):
            raise XlsxInspectionError("XLSX_CELL_TEXT_UNMODELED")
        if child.tag in {_FORMULA, _VALUE}:
            if child.attrib or list(child):
                raise XlsxInspectionError("XLSX_CELL_CHILD_UNMODELED")
            continue
        if child.tag == _INLINE:
            _validate_simple_text_container(
                child,
                code="XLSX_INLINE_STRING_UNMODELED",
            )
            continue
        raise XlsxInspectionError("XLSX_CELL_CHILD_UNMODELED")


def _validate_worksheet(root: ElementTree.Element) -> None:
    if root.tag != _WORKSHEET:
        raise XlsxInspectionError("XLSX_WORKSHEET_INVALID")
    _require_attributes(
        root,
        _ALLOWED_WORKSHEET_ATTRIBUTES,
        "XLSX_WORKSHEET_ATTRIBUTE_UNMODELED",
    )
    if _has_text(root.text):
        raise XlsxInspectionError("XLSX_UNMODELED_WORKSHEET_TEXT")
    sheet_data_nodes = root.findall(_SHEET_DATA)
    if len(sheet_data_nodes) != 1:
        raise XlsxInspectionError("XLSX_SHEET_DATA_STRUCTURE_INVALID")
    sheet_data = sheet_data_nodes[0]

    for child in root:
        if _has_text(child.tail):
            raise XlsxInspectionError("XLSX_UNMODELED_WORKSHEET_TEXT")
        if child is sheet_data:
            continue
        if child.tag in {_ROW, _CELL}:
            continue
        _require_text_free_subtree(
            child,
            allowed_tags=_ALLOWED_WORKSHEET_STRUCTURE_TAGS,
        )

    if sheet_data.attrib or _has_text(sheet_data.text) or _has_text(sheet_data.tail):
        raise XlsxInspectionError("XLSX_UNMODELED_WORKSHEET_TEXT")
    for sheet_child in sheet_data:
        if _has_text(sheet_child.tail):
            raise XlsxInspectionError("XLSX_UNMODELED_WORKSHEET_TEXT")
        if sheet_child.tag == _CELL:
            continue
        if sheet_child.tag != _ROW:
            raise XlsxInspectionError("XLSX_WORKSHEET_ELEMENT_UNMODELED")
        _require_attributes(
            sheet_child,
            _ALLOWED_ROW_ATTRIBUTES,
            "XLSX_ROW_ATTRIBUTE_UNMODELED",
        )
        if _has_text(sheet_child.text):
            raise XlsxInspectionError("XLSX_UNMODELED_WORKSHEET_TEXT")
        for row_child in sheet_child:
            if _has_text(row_child.tail):
                raise XlsxInspectionError("XLSX_UNMODELED_WORKSHEET_TEXT")
            if row_child.tag != _CELL:
                raise XlsxInspectionError("XLSX_WORKSHEET_ELEMENT_UNMODELED")
            _validate_cell_content(row_child)


def _validate_shared_strings(root: ElementTree.Element) -> None:
    if root.tag != _SHARED_ROOT:
        raise XlsxInspectionError("XLSX_SHARED_STRINGS_INVALID")
    _require_attributes(
        root,
        _ALLOWED_SHARED_ROOT_ATTRIBUTES,
        "XLSX_SHARED_STRINGS_INVALID",
    )
    if _has_text(root.text):
        raise XlsxInspectionError("XLSX_SHARED_STRINGS_INVALID")
    for item in root:
        if item.tag != _SHARED_ITEM or _has_text(item.tail):
            raise XlsxInspectionError("XLSX_SHARED_STRINGS_INVALID")
        _validate_simple_text_container(
            item,
            code="XLSX_SHARED_STRINGS_INVALID",
        )


def _semantic_node(element: ElementTree.Element) -> dict[str, object]:
    return {
        "tag": element.tag,
        "attributes": sorted(element.attrib.items()),
        "text": element.text or "",
        "tail": element.tail or "",
        "children": [_semantic_node(child) for child in element],
    }


def _semantic_sha256(root: ElementTree.Element) -> str:
    payload = json.dumps(
        _semantic_node(root),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def validate_hidden_xml_content(
    workbook: bytes,
    limits: XlsxInspectionLimits,
) -> tuple[dict[str, object], ...]:
    auxiliary: list[dict[str, object]] = []
    try:
        with ZipFile(BytesIO(workbook)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                path = info.filename.replace("\\", "/").casefold()
                if path.startswith("xl/worksheets/") and path.endswith(".xml"):
                    payload = _read_limited(zf, info.filename, limits)
                    root = _xml_root(payload, "XLSX_WORKSHEET_INVALID")
                    _validate_worksheet(root)
                    continue
                if path == "xl/sharedstrings.xml":
                    payload = _read_limited(zf, info.filename, limits)
                    root = _xml_root(payload, "XLSX_SHARED_STRINGS_INVALID")
                    _validate_shared_strings(root)
                    continue
                if path in _AUXILIARY_PARTS:
                    payload = _read_limited(zf, info.filename, limits)
                    root = _xml_root(payload, "XLSX_AUXILIARY_PART_INVALID")
                    auxiliary.append({
                        "path": path,
                        "raw_sha256": sha256(payload).hexdigest(),
                        "semantic_sha256": _semantic_sha256(root),
                        "size_bytes": len(payload),
                    })
        return tuple(sorted(auxiliary, key=lambda item: str(item["path"])))
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


__all__ = ["validate_hidden_xml_content"]
