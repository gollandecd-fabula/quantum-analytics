from __future__ import annotations

from ._xlsx_contracts import XlsxInspectionError

_SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_CORE_PROPERTIES_NS = (
    "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
)
_EXTENDED_PROPERTIES_NS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
)
_DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"

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


def _has_text(value: str | None) -> bool:
    return value is not None and bool(value.strip())


def validate_auxiliary_content(path: str, root) -> None:
    expected_roots = _EXPECTED_ROOTS.get(path)
    if expected_roots is None:
        raise XlsxInspectionError("XLSX_AUXILIARY_PART_UNMODELED")
    if (
        root.tag not in expected_roots
        or root.attrib
        or list(root)
        or _has_text(root.text)
        or _has_text(root.tail)
    ):
        raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")


__all__ = ["validate_auxiliary_content"]
