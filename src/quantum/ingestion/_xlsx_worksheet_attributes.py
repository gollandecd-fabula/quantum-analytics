from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from zipfile import BadZipFile, ZipFile
from zlib import error as ZlibError

from ._xlsx_archive import _read_limited, _xml_root
from ._xlsx_content_model import (
    _ALLOWED_WORKSHEET_STRUCTURE_TAGS,
    _SHEET_DATA,
)
from ._xlsx_contracts import XlsxInspectionError, XlsxInspectionLimits

_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_X14AC_NS = "http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac"
_ALLOWED_ATTRIBUTES = frozenset({
    "applyStyles", "summaryBelow", "summaryRight", "showOutlineSymbols",
    "autoPageBreaks", "fitToPage", "ref", "windowProtection",
    "showFormulas", "showGridLines", "showRowColHeaders", "showZeros",
    "rightToLeft", "tabSelected", "showRuler", "defaultGridColor",
    "showWhiteSpace", "view", "topLeftCell", "colorId", "zoomScale",
    "zoomScaleNormal", "zoomScaleSheetLayoutView", "zoomScalePageLayoutView",
    "workbookViewId", "xSplit", "ySplit", "activePane", "state", "pane",
    "activeCell", "activeCellId", "sqref", "baseColWidth", "defaultColWidth",
    "defaultRowHeight", "customHeight", "zeroHeight", "thickTop",
    "thickBottom", "outlineLevelRow", "outlineLevelCol", "min", "max",
    "width", "style", "hidden", "bestFit", "customWidth", "phonetic",
    "outlineLevel", "collapsed", "count", "horizontalCentered",
    "verticalCentered", "headings", "gridLines", "gridLinesSet", "left",
    "right", "top", "bottom", "header", "footer", "paperSize", "scale",
    "firstPageNumber", "fitToWidth", "fitToHeight", "pageOrder",
    "orientation", "usePrinterDefaults", "blackAndWhite", "draft",
    "cellComments", "useFirstPageNumber", "errors", "horizontalDpi",
    "verticalDpi", "copies", "password", "algorithmName", "hashValue",
    "saltValue", "spinCount", "sheet", "objects", "scenarios",
    "formatCells", "formatColumns", "formatRows", "insertColumns",
    "insertRows", "insertHyperlinks", "deleteColumns", "deleteRows",
    "selectLockedCells", "sort", "autoFilter", "pivotTables",
    "selectUnlockedCells", "fontId", "type", "alignment", "syncHorizontal",
    "syncVertical", "syncRef", "transitionEvaluation", "transitionEntry",
    "published", "codeName", "filterMode", "enableFormatConditionsCalculation",
    f"{{{_REL_NS}}}id", f"{{{_X14AC_NS}}}dyDescent",
})


def validate_worksheet_structural_attributes(
    workbook: bytes,
    limits: XlsxInspectionLimits,
) -> tuple[tuple[str, str, int], ...]:
    evidence: list[tuple[str, str, int]] = []
    try:
        with ZipFile(BytesIO(workbook)) as zf:
            for info in zf.infolist():
                normalized = info.filename.replace("\\", "/").casefold()
                if info.is_dir() or not (
                    normalized.startswith("xl/worksheets/")
                    and normalized.endswith(".xml")
                ):
                    continue
                payload = _read_limited(zf, info.filename, limits)
                root = _xml_root(payload, "XLSX_WORKSHEET_INVALID")
                for child in root:
                    if child.tag == _SHEET_DATA:
                        continue
                    for element in child.iter():
                        if element.tag not in _ALLOWED_WORKSHEET_STRUCTURE_TAGS:
                            continue
                        if any(name not in _ALLOWED_ATTRIBUTES for name in element.attrib):
                            raise XlsxInspectionError(
                                "XLSX_WORKSHEET_ATTRIBUTE_UNMODELED"
                            )
                evidence.append(
                    (normalized, sha256(payload).hexdigest(), len(payload))
                )
        return tuple(sorted(evidence))
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


__all__ = ["validate_worksheet_structural_attributes"]
