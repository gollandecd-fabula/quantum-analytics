from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import re
from zipfile import BadZipFile, ZipFile
from zlib import error as ZlibError

from ._xlsx_archive import _read_limited, _xml_root
from ._xlsx_content_model import _SHEET_DATA
from ._xlsx_contracts import XlsxInspectionError, XlsxInspectionLimits

_SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_X14AC_NS = "http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac"

_CELL = re.compile(r"\$?[A-Z]{1,3}\$?[1-9][0-9]{0,6}")
_RANGE = re.compile(
    r"\$?[A-Z]{1,3}\$?[1-9][0-9]{0,6}"
    r"(?::\$?[A-Z]{1,3}\$?[1-9][0-9]{0,6})?"
)
_UINT = re.compile(r"(?:0|[1-9][0-9]{0,9})")
_POSITIVE_UINT = re.compile(r"[1-9][0-9]{0,9}")
_DECIMAL = re.compile(r"-?(?:0|[1-9][0-9]{0,9})(?:\.[0-9]{1,8})?")
_SPANS = re.compile(r"[1-9][0-9]{0,5}:[1-9][0-9]{0,5}")
_RELATIONSHIP_ID = re.compile(r"rId[1-9][0-9]{0,5}")
_BOOLEAN = frozenset({"0", "1", "true", "false"})


def _tag(name: str) -> str:
    return f"{{{_SPREADSHEET_NS}}}{name}"


_RULES: dict[str, dict[str, object]] = {
    _tag("sheetPr"): {
        "syncHorizontal": _BOOLEAN,
        "syncVertical": _BOOLEAN,
        "syncRef": _RANGE,
        "transitionEvaluation": _BOOLEAN,
        "transitionEntry": _BOOLEAN,
        "published": _BOOLEAN,
        "filterMode": _BOOLEAN,
        "enableFormatConditionsCalculation": _BOOLEAN,
    },
    _tag("outlinePr"): {
        "applyStyles": _BOOLEAN,
        "summaryBelow": _BOOLEAN,
        "summaryRight": _BOOLEAN,
        "showOutlineSymbols": _BOOLEAN,
    },
    _tag("pageSetUpPr"): {
        "autoPageBreaks": _BOOLEAN,
        "fitToPage": _BOOLEAN,
    },
    _tag("dimension"): {"ref": _RANGE},
    _tag("sheetViews"): {},
    _tag("sheetView"): {
        "windowProtection": _BOOLEAN,
        "showFormulas": _BOOLEAN,
        "showGridLines": _BOOLEAN,
        "showRowColHeaders": _BOOLEAN,
        "showZeros": _BOOLEAN,
        "rightToLeft": _BOOLEAN,
        "tabSelected": _BOOLEAN,
        "showRuler": _BOOLEAN,
        "defaultGridColor": _BOOLEAN,
        "showWhiteSpace": _BOOLEAN,
        "view": frozenset({"normal", "pageBreakPreview", "pageLayout"}),
        "topLeftCell": _CELL,
        "colorId": _UINT,
        "zoomScale": _UINT,
        "zoomScaleNormal": _UINT,
        "zoomScaleSheetLayoutView": _UINT,
        "zoomScalePageLayoutView": _UINT,
        "workbookViewId": _UINT,
    },
    _tag("pane"): {
        "xSplit": _DECIMAL,
        "ySplit": _DECIMAL,
        "topLeftCell": _CELL,
        "activePane": frozenset(
            {"bottomRight", "topRight", "bottomLeft", "topLeft"}
        ),
        "state": frozenset({"split", "frozen", "frozenSplit"}),
    },
    _tag("selection"): {
        "pane": frozenset(
            {"bottomRight", "topRight", "bottomLeft", "topLeft"}
        ),
        "activeCell": _CELL,
        "activeCellId": _UINT,
        "sqref": "SQREF",
    },
    _tag("sheetFormatPr"): {
        "baseColWidth": _UINT,
        "defaultColWidth": _DECIMAL,
        "defaultRowHeight": _DECIMAL,
        "customHeight": _BOOLEAN,
        "zeroHeight": _BOOLEAN,
        "thickTop": _BOOLEAN,
        "thickBottom": _BOOLEAN,
        "outlineLevelRow": _UINT,
        "outlineLevelCol": _UINT,
        f"{{{_X14AC_NS}}}dyDescent": _DECIMAL,
    },
    _tag("cols"): {},
    _tag("col"): {
        "min": _POSITIVE_UINT,
        "max": _POSITIVE_UINT,
        "width": _DECIMAL,
        "style": _UINT,
        "hidden": _BOOLEAN,
        "bestFit": _BOOLEAN,
        "customWidth": _BOOLEAN,
        "phonetic": _BOOLEAN,
        "outlineLevel": _UINT,
        "collapsed": _BOOLEAN,
    },
    _tag("mergeCells"): {"count": _UINT},
    _tag("mergeCell"): {"ref": _RANGE},
    _tag("printOptions"): {
        "horizontalCentered": _BOOLEAN,
        "verticalCentered": _BOOLEAN,
        "headings": _BOOLEAN,
        "gridLines": _BOOLEAN,
        "gridLinesSet": _BOOLEAN,
    },
    _tag("pageMargins"): {
        "left": _DECIMAL,
        "right": _DECIMAL,
        "top": _DECIMAL,
        "bottom": _DECIMAL,
        "header": _DECIMAL,
        "footer": _DECIMAL,
    },
    _tag("pageSetup"): {
        "paperSize": _UINT,
        "scale": _UINT,
        "firstPageNumber": _UINT,
        "fitToWidth": _UINT,
        "fitToHeight": _UINT,
        "pageOrder": frozenset({"downThenOver", "overThenDown"}),
        "orientation": frozenset({"default", "portrait", "landscape"}),
        "usePrinterDefaults": _BOOLEAN,
        "blackAndWhite": _BOOLEAN,
        "draft": _BOOLEAN,
        "cellComments": frozenset({"none", "asDisplayed", "atEnd"}),
        "useFirstPageNumber": _BOOLEAN,
        "errors": frozenset({"displayed", "blank", "dash", "NA"}),
        "horizontalDpi": _UINT,
        "verticalDpi": _UINT,
        "copies": _UINT,
        f"{{{_REL_NS}}}id": _RELATIONSHIP_ID,
    },
    _tag("sheetProtection"): {
        "sheet": _BOOLEAN,
        "objects": _BOOLEAN,
        "scenarios": _BOOLEAN,
        "formatCells": _BOOLEAN,
        "formatColumns": _BOOLEAN,
        "formatRows": _BOOLEAN,
        "insertColumns": _BOOLEAN,
        "insertRows": _BOOLEAN,
        "insertHyperlinks": _BOOLEAN,
        "deleteColumns": _BOOLEAN,
        "deleteRows": _BOOLEAN,
        "selectLockedCells": _BOOLEAN,
        "sort": _BOOLEAN,
        "autoFilter": _BOOLEAN,
        "pivotTables": _BOOLEAN,
        "selectUnlockedCells": _BOOLEAN,
    },
    _tag("phoneticPr"): {
        "fontId": _UINT,
        "type": frozenset(
            {
                "fullwidthKatakana",
                "halfwidthKatakana",
                "Hiragana",
                "noConversion",
            }
        ),
        "alignment": frozenset(
            {"noControl", "left", "center", "distributed"}
        ),
    },
}


def _value_matches(rule: object, value: str) -> bool:
    if not value or value != value.strip() or len(value) > 128 or not value.isascii():
        return False
    if rule == "SQREF":
        references = value.split()
        return bool(references) and all(_RANGE.fullmatch(item) for item in references)
    if isinstance(rule, frozenset):
        return value in rule
    if hasattr(rule, "fullmatch"):
        return rule.fullmatch(value) is not None
    return False


def _validate_element_attributes(element) -> None:
    rules = _RULES.get(element.tag)
    if rules is None or set(element.attrib) - set(rules):
        raise XlsxInspectionError("XLSX_WORKSHEET_ATTRIBUTE_UNMODELED")
    if any(
        not _value_matches(rules[name], value)
        for name, value in element.attrib.items()
    ):
        raise XlsxInspectionError("XLSX_WORKSHEET_ATTRIBUTE_VALUE_INVALID")


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
                        _validate_element_attributes(element)
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
