from __future__ import annotations

import re

from ._xlsx_contracts import XlsxInspectionError

_SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_CORE_PROPERTIES_NS = (
    "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
)
_EXTENDED_PROPERTIES_NS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
)
_DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_DOC_PROPERTIES_TYPES_NS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"
)
_DC_NS = "http://purl.org/dc/elements/1.1/"
_DCTERMS_NS = "http://purl.org/dc/terms/"
_DCMITYPE_NS = "http://purl.org/dc/dcmitype/"
_XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
_XML_NS = "http://www.w3.org/XML/1998/namespace"
_MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
_XR_NS = "http://schemas.microsoft.com/office/spreadsheetml/2014/revision"

_MC_IGNORABLE = f"{{{_MC_NS}}}Ignorable"
_XR_UID = f"{{{_XR_NS}}}uid"
_PREFIX = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*")
_GUID = re.compile(
    r"\{[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-"
    r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}"
)
_MAX_TEXT_LENGTH = 32767

_EXPECTED_ROOTS = {
    "docprops/core.xml": frozenset(
        {
            "coreProperties",
            f"{{{_CORE_PROPERTIES_NS}}}coreProperties",
        }
    ),
    "docprops/app.xml": frozenset(
        {
            "Properties",
            f"{{{_EXTENDED_PROPERTIES_NS}}}Properties",
        }
    ),
    "xl/styles.xml": frozenset(
        {
            "styleSheet",
            f"{{{_SPREADSHEET_NS}}}styleSheet",
        }
    ),
    "xl/theme/theme1.xml": frozenset(
        {
            "theme",
            f"{{{_DRAWING_NS}}}theme",
        }
    ),
}

_ALLOWED_ELEMENT_NAMESPACES = {
    "docprops/core.xml": frozenset(
        {
            _CORE_PROPERTIES_NS,
            _DC_NS,
            _DCTERMS_NS,
            _DCMITYPE_NS,
        }
    ),
    "docprops/app.xml": frozenset(
        {
            _EXTENDED_PROPERTIES_NS,
            _DOC_PROPERTIES_TYPES_NS,
        }
    ),
    "xl/styles.xml": frozenset({_SPREADSHEET_NS}),
    "xl/theme/theme1.xml": frozenset({_DRAWING_NS}),
}

_ALLOWED_ATTRIBUTE_NAMESPACES = {
    "docprops/core.xml": frozenset(
        {
            _CORE_PROPERTIES_NS,
            _DC_NS,
            _DCTERMS_NS,
            _DCMITYPE_NS,
            _XSI_NS,
            _XML_NS,
        }
    ),
    "docprops/app.xml": frozenset(
        {
            _EXTENDED_PROPERTIES_NS,
            _DOC_PROPERTIES_TYPES_NS,
            _XML_NS,
        }
    ),
    "xl/styles.xml": frozenset(
        {
            _SPREADSHEET_NS,
            _MC_NS,
            _XR_NS,
            _XML_NS,
        }
    ),
    "xl/theme/theme1.xml": frozenset({_DRAWING_NS, _XML_NS}),
}


def _namespace(name: str) -> str | None:
    if name.startswith("{") and "}" in name:
        return name[1:].split("}", 1)[0]
    return None


def _validate_ignorable(value: str | None) -> None:
    if value is None:
        return
    tokens = value.split()
    if (
        value != value.strip()
        or not tokens
        or any(_PREFIX.fullmatch(token) is None for token in tokens)
    ):
        raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")


def _validate_root_attributes(path: str, root) -> None:
    if path == "xl/styles.xml":
        if set(root.attrib) - {_MC_IGNORABLE, _XR_UID}:
            raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
        _validate_ignorable(root.get(_MC_IGNORABLE))
        uid = root.get(_XR_UID)
        if uid is not None and _GUID.fullmatch(uid) is None:
            raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
        return
    if path == "xl/theme/theme1.xml":
        if set(root.attrib) - {"name"}:
            raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
        name = root.get("name")
        if name is not None and (
            not name.strip() or name != name.strip() or len(name) > 255
        ):
            raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
        return
    if root.attrib:
        raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")


def _validate_text(value: str | None) -> None:
    if value is not None and len(value) > _MAX_TEXT_LENGTH:
        raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")


def validate_auxiliary_content(path: str, root) -> None:
    expected_roots = _EXPECTED_ROOTS.get(path)
    if expected_roots is None:
        raise XlsxInspectionError("XLSX_AUXILIARY_PART_UNMODELED")
    if root.tag not in expected_roots:
        raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
    _validate_root_attributes(path, root)
    element_namespaces = _ALLOWED_ELEMENT_NAMESPACES[path]
    attribute_namespaces = _ALLOWED_ATTRIBUTE_NAMESPACES[path]
    for element in root.iter():
        if _namespace(element.tag) not in element_namespaces:
            raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
        _validate_text(element.text)
        _validate_text(element.tail)
        for name, value in element.attrib.items():
            namespace = _namespace(name)
            if namespace is not None and namespace not in attribute_namespaces:
                raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
            if len(value) > _MAX_TEXT_LENGTH:
                raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")


__all__ = ["validate_auxiliary_content"]
