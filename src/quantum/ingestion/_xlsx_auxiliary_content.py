from __future__ import annotations

from collections import Counter
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
_DC_NS = "http://purl.org/dc/elements/1.1/"
_DCTERMS_NS = "http://purl.org/dc/terms/"
_XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
_MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
_XR_NS = "http://schemas.microsoft.com/office/spreadsheetml/2014/revision"
_X15_NS = "http://schemas.microsoft.com/office/spreadsheetml/2010/11/main"

_MC_IGNORABLE = f"{{{_MC_NS}}}Ignorable"
_XR_UID = f"{{{_XR_NS}}}uid"
_XSI_TYPE = f"{{{_XSI_NS}}}type"
_PREFIX = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*")
_GUID = re.compile(
    r"\{[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-"
    r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}"
)
_UINT = re.compile(r"(?:0|[1-9][0-9]{0,9})")
_DECIMAL = re.compile(r"(?:0|[1-9][0-9]{0,9})(?:\.[0-9]{1,8})?")
_HEX6 = re.compile(r"[0-9A-Fa-f]{6}")
_HEX20 = re.compile(r"[0-9A-Fa-f]{20}")
_SCRIPT = re.compile(r"[A-Za-z]{4}")
_SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._+\-()]{0,254}")
_SAFE_NAME_OR_EMPTY = re.compile(r"(?:[A-Za-z0-9][A-Za-z0-9 ._+\-()]{0,254})?")
_ISO_UTC = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,9})?Z"
)
_BOOLEAN = frozenset({"0", "1", "true", "false"})
_MAX_TEXT_LENGTH = 32767
_KNOWN_TYPEFACES = frozenset(
    {
        "",
        "Arial",
        "Calibri",
        "Calibri Light",
        "DaunPenh",
        "DokChampa",
        "Estrangelo Edessa",
        "Euphemia",
        "Gautami",
        "Iskoola Pota",
        "Kalinga",
        "Kartika",
        "Latha",
        "MV Boli",
        "Mangal",
        "Microsoft Himalaya",
        "Microsoft Uighur",
        "Microsoft Yi Baiti",
        "Mongolian Baiti",
        "MoolBoran",
        "Nyala",
        "Plantagenet Cherokee",
        "Raavi",
        "Shruti",
        "Sylfaen",
        "Tahoma",
        "Times New Roman",
        "Tunga",
        "Vrinda",
        "新細明體",
        "游ゴシック",
        "游ゴシック Light",
        "等线",
        "等线 Light",
        "맑은 고딕",
    }
)

_EXPECTED_ROOTS = {
    "docprops/core.xml": frozenset(
        {"coreProperties", f"{{{_CORE_PROPERTIES_NS}}}coreProperties"}
    ),
    "docprops/app.xml": frozenset(
        {"Properties", f"{{{_EXTENDED_PROPERTIES_NS}}}Properties"}
    ),
    "xl/styles.xml": frozenset(
        {"styleSheet", f"{{{_SPREADSHEET_NS}}}styleSheet"}
    ),
    "xl/theme/theme1.xml": frozenset(
        {"theme", f"{{{_DRAWING_NS}}}theme"}
    ),
}

_STYLE_ALLOWED_TAGS = frozenset(
    {
        "styleSheet", "fonts", "font", "sz", "color", "name", "family",
        "fills", "fill", "patternFill", "borders", "border", "left",
        "right", "top", "bottom", "diagonal", "cellStyleXfs", "cellXfs",
        "xf", "alignment", "cellStyles", "cellStyle", "dxfs", "tableStyles",
    }
)
_THEME_ALLOWED_TAGS = frozenset(
    {
        "theme", "themeElements", "clrScheme", "dk1", "lt1", "dk2", "lt2",
        "accent1", "accent2", "accent3", "accent4", "accent5", "accent6",
        "hlink", "folHlink", "sysClr", "srgbClr", "fontScheme", "majorFont",
        "minorFont", "latin", "ea", "cs", "font", "fmtScheme", "fillStyleLst",
        "solidFill", "schemeClr", "gradFill", "gsLst", "gs", "lumMod",
        "satMod", "tint", "lin", "shade", "lnStyleLst", "ln", "prstDash",
        "miter", "effectStyleLst", "effectStyle", "effectLst", "outerShdw",
        "alpha", "bgFillStyleLst", "objectDefaults", "extraClrSchemeLst",
    }
)


def _local(name: str) -> str:
    return name.split("}", 1)[-1] if name.startswith("{") else name


def _namespace(name: str) -> str | None:
    if name.startswith("{") and "}" in name:
        return name[1:].split("}", 1)[0]
    return None


def _has_text(value: str | None) -> bool:
    return value is not None and bool(value.strip())


def _matches(pattern: re.Pattern[str], value: str) -> bool:
    return value == value.strip() and pattern.fullmatch(value) is not None


def _require_attrs(element, allowed: set[str]) -> None:
    if set(element.attrib) - allowed:
        raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")


def _uint(value: str) -> bool:
    return _matches(_UINT, value)


def _boolean(value: str) -> bool:
    return value in _BOOLEAN


def _safe_name(value: str, *, empty: bool = False) -> bool:
    pattern = _SAFE_NAME_OR_EMPTY if empty else _SAFE_NAME
    return _matches(pattern, value)


def _validate_ignorable(value: str | None) -> None:
    if value is None:
        return
    if not value or value != value.strip():
        raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
    tokens = value.split()
    if not tokens or any(_PREFIX.fullmatch(token) is None for token in tokens):
        raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
    counts = Counter(tokens)
    for token, count in counts.items():
        if count == 1:
            continue
        if not (token == "x15" and count == 2):
            raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")


def _validate_legacy_empty_root(root) -> bool:
    if _namespace(root.tag) is not None:
        return False
    if root.attrib or list(root) or _has_text(root.text) or _has_text(root.tail):
        raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
    return True


def _validate_core(root) -> None:
    if _validate_legacy_empty_root(root):
        return
    if root.tag != f"{{{_CORE_PROPERTIES_NS}}}coreProperties":
        raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
    if root.attrib or _has_text(root.text) or _has_text(root.tail):
        raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
    allowed = {
        f"{{{_DC_NS}}}creator": "safe_text",
        f"{{{_DC_NS}}}title": "safe_text",
        f"{{{_DC_NS}}}subject": "safe_text",
        f"{{{_DC_NS}}}description": "safe_text",
        f"{{{_DCTERMS_NS}}}created": "date",
        f"{{{_DCTERMS_NS}}}modified": "date",
    }
    seen: set[str] = set()
    for child in root:
        kind = allowed.get(child.tag)
        if kind is None or child.tag in seen or list(child) or _has_text(child.tail):
            raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
        seen.add(child.tag)
        value = child.text or ""
        if kind == "safe_text":
            if child.attrib or not _safe_name(value):
                raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
        else:
            if child.attrib != {_XSI_TYPE: "dcterms:W3CDTF"} or not _matches(
                _ISO_UTC, value
            ):
                raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")


def _validate_app(root) -> None:
    if _validate_legacy_empty_root(root):
        return
    if root.tag != f"{{{_EXTENDED_PROPERTIES_NS}}}Properties":
        raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
    if root.attrib or _has_text(root.text) or _has_text(root.tail):
        raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
    allowed = {
        f"{{{_EXTENDED_PROPERTIES_NS}}}TotalTime": "uint",
        f"{{{_EXTENDED_PROPERTIES_NS}}}Application": "name",
    }
    seen: set[str] = set()
    for child in root:
        kind = allowed.get(child.tag)
        if (
            kind is None
            or child.tag in seen
            or child.attrib
            or list(child)
            or _has_text(child.tail)
        ):
            raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
        seen.add(child.tag)
        value = child.text or ""
        if kind == "uint" and not _uint(value):
            raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
        if kind == "name" and not _safe_name(value):
            raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")


def _validate_styles(root) -> None:
    if _validate_legacy_empty_root(root):
        return
    if root.tag != f"{{{_SPREADSHEET_NS}}}styleSheet":
        raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
    _require_attrs(root, {_MC_IGNORABLE, _XR_UID})
    _validate_ignorable(root.get(_MC_IGNORABLE))
    uid = root.get(_XR_UID)
    if uid is not None and _GUID.fullmatch(uid) is None:
        raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
    for element in root.iter():
        if _namespace(element.tag) != _SPREADSHEET_NS:
            raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
        local = _local(element.tag)
        if local not in _STYLE_ALLOWED_TAGS or _has_text(element.text) or _has_text(
            element.tail
        ):
            raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
        attrs = element.attrib
        if element is root:
            continue
        if local in {
            "font", "fill", "border", "left", "right", "top", "bottom",
            "diagonal", "alignment",
        }:
            _require_attrs(element, set())
        elif local in {
            "fonts", "fills", "borders", "cellStyleXfs", "cellXfs",
            "cellStyles", "dxfs",
        }:
            _require_attrs(element, {"count"})
            if not _uint(attrs.get("count", "")):
                raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
        elif local == "sz":
            _require_attrs(element, {"val"})
            if not _matches(_DECIMAL, attrs.get("val", "")):
                raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
        elif local == "color":
            _require_attrs(element, {"theme"})
            if attrs and not _uint(attrs.get("theme", "")):
                raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
        elif local == "name":
            _require_attrs(element, {"val"})
            if not _safe_name(attrs.get("val", "")):
                raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
        elif local == "family":
            _require_attrs(element, {"val"})
            if not _uint(attrs.get("val", "")):
                raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
        elif local == "patternFill":
            _require_attrs(element, {"patternType"})
            if attrs.get("patternType") not in {"none", "gray125", "solid"}:
                raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
        elif local == "xf":
            numeric = {"numFmtId", "fontId", "fillId", "borderId", "xfId"}
            booleans = {
                "applyFont", "applyFill", "applyBorder", "applyAlignment",
                "applyProtection", "applyNumberFormat", "quotePrefix", "pivotButton",
            }
            _require_attrs(element, numeric | booleans)
            if any(not _uint(attrs[name]) for name in numeric if name in attrs):
                raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
            if any(not _boolean(attrs[name]) for name in booleans if name in attrs):
                raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
        elif local == "cellStyle":
            _require_attrs(element, {"name", "xfId", "builtinId", "customBuiltin", "hidden"})
            if not _safe_name(attrs.get("name", "")):
                raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
            if any(not _uint(attrs[name]) for name in ("xfId", "builtinId") if name in attrs):
                raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
            if any(not _boolean(attrs[name]) for name in ("customBuiltin", "hidden") if name in attrs):
                raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
        elif local == "tableStyles":
            _require_attrs(element, {"count", "defaultPivotStyle", "defaultTableStyle"})
            if not _uint(attrs.get("count", "")):
                raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
            for name in ("defaultPivotStyle", "defaultTableStyle"):
                if name in attrs and not _safe_name(attrs[name]):
                    raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")


def _validate_theme(root) -> None:
    if _validate_legacy_empty_root(root):
        return
    if root.tag != f"{{{_DRAWING_NS}}}theme":
        raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
    for element in root.iter():
        if _namespace(element.tag) != _DRAWING_NS:
            raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
        local = _local(element.tag)
        if local not in _THEME_ALLOWED_TAGS or _has_text(element.text) or _has_text(
            element.tail
        ):
            raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
        attrs = element.attrib
        if local in {"theme", "clrScheme", "fontScheme", "fmtScheme"}:
            _require_attrs(element, {"name"})
            if not _safe_name(attrs.get("name", "")):
                raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
        elif local in {"themeElements", "dk1", "lt1", "dk2", "lt2", "accent1", "accent2", "accent3", "accent4", "accent5", "accent6", "hlink", "folHlink", "majorFont", "minorFont", "fillStyleLst", "solidFill", "gsLst", "lnStyleLst", "effectStyleLst", "effectStyle", "effectLst", "bgFillStyleLst", "objectDefaults", "extraClrSchemeLst"}:
            _require_attrs(element, set())
        elif local == "sysClr":
            _require_attrs(element, {"val", "lastClr"})
            if attrs.get("val") not in {"window", "windowText"} or _HEX6.fullmatch(attrs.get("lastClr", "")) is None:
                raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
        elif local == "srgbClr":
            _require_attrs(element, {"val"})
            if _HEX6.fullmatch(attrs.get("val", "")) is None:
                raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
        elif local == "schemeClr":
            _require_attrs(element, {"val"})
            if not _safe_name(attrs.get("val", "")):
                raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
        elif local == "latin":
            _require_attrs(element, {"typeface", "panose"})
            if attrs.get("typeface", "") not in _KNOWN_TYPEFACES:
                raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
            if "panose" in attrs and _HEX20.fullmatch(attrs["panose"]) is None:
                raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
        elif local in {"ea", "cs"}:
            _require_attrs(element, {"typeface"})
            if attrs.get("typeface", "") not in _KNOWN_TYPEFACES:
                raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
        elif local == "font":
            _require_attrs(element, {"script", "typeface"})
            if (
                _SCRIPT.fullmatch(attrs.get("script", "")) is None
                or attrs.get("typeface", "") not in _KNOWN_TYPEFACES
            ):
                raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
        elif local in {"lumMod", "satMod", "tint", "shade", "alpha"}:
            _require_attrs(element, {"val"})
            if not _uint(attrs.get("val", "")):
                raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
        elif local == "gradFill":
            _require_attrs(element, {"rotWithShape"})
            if not _boolean(attrs.get("rotWithShape", "")):
                raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
        elif local == "gs":
            _require_attrs(element, {"pos"})
            if not _uint(attrs.get("pos", "")):
                raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
        elif local == "lin":
            _require_attrs(element, {"ang", "scaled"})
            if not _uint(attrs.get("ang", "")) or not _boolean(attrs.get("scaled", "")):
                raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
        elif local == "ln":
            _require_attrs(element, {"w", "cap", "cmpd", "algn"})
            if not _uint(attrs.get("w", "")):
                raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
            if attrs.get("cap") not in {"flat", "rnd", "sq"} or attrs.get("cmpd") not in {"sng", "dbl", "thickThin", "thinThick", "tri"} or attrs.get("algn") not in {"ctr", "in"}:
                raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
        elif local == "prstDash":
            _require_attrs(element, {"val"})
            if attrs.get("val") not in {"solid", "dash", "dot", "dashDot", "lgDash"}:
                raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
        elif local == "miter":
            _require_attrs(element, {"lim"})
            if not _uint(attrs.get("lim", "")):
                raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
        elif local == "outerShdw":
            _require_attrs(element, {"blurRad", "dist", "dir", "algn", "rotWithShape"})
            if any(not _uint(attrs.get(name, "")) for name in ("blurRad", "dist", "dir")):
                raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
            if attrs.get("algn") not in {"ctr", "tl", "t", "tr", "l", "r", "bl", "b", "br"} or not _boolean(attrs.get("rotWithShape", "")):
                raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")


def validate_auxiliary_content(path: str, root) -> None:
    expected_roots = _EXPECTED_ROOTS.get(path)
    if expected_roots is None:
        raise XlsxInspectionError("XLSX_AUXILIARY_PART_UNMODELED")
    if root.tag not in expected_roots:
        raise XlsxInspectionError("XLSX_AUXILIARY_CONTENT_UNMODELED")
    if path == "docprops/core.xml":
        _validate_core(root)
    elif path == "docprops/app.xml":
        _validate_app(root)
    elif path == "xl/styles.xml":
        _validate_styles(root)
    elif path == "xl/theme/theme1.xml":
        _validate_theme(root)


__all__ = ["validate_auxiliary_content"]
