from __future__ import annotations

from io import BytesIO
import re
from zipfile import BadZipFile, ZipFile
from zlib import error as ZlibError

from ._xlsx_archive import _read_limited
from ._xlsx_contracts import XlsxInspectionError, XlsxInspectionLimits

_XML_DECLARATION = re.compile(r"^\s*<\?xml(?:\s+[^?]*)?\?>", re.IGNORECASE)
_NAMESPACE_ASSIGNMENT = re.compile(
    r"\sxmlns(?::[A-Za-z_][A-Za-z0-9_.-]*)?\s*=",
)
_NAMESPACE_DECLARATION = re.compile(
    r"\sxmlns(?::(?P<prefix>[A-Za-z_][A-Za-z0-9_.-]*))?\s*=\s*"
    r"(?P<quote>[\"'])(?P<uri>[^\"']*)(?P=quote)",
)

_PACKAGE_CONTENT_TYPES = "http://schemas.openxmlformats.org/package/2006/content-types"
_PACKAGE_RELATIONSHIPS = "http://schemas.openxmlformats.org/package/2006/relationships"
_OFFICE_RELATIONSHIPS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)
_SPREADSHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_DRAWING = "http://schemas.openxmlformats.org/drawingml/2006/main"
_MARKUP_COMPATIBILITY = (
    "http://schemas.openxmlformats.org/markup-compatibility/2006"
)
_CORE_PROPERTIES = (
    "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
)
_EXTENDED_PROPERTIES = (
    "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
)
_DOC_PROPERTIES_TYPES = (
    "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"
)

_ALLOWED_NAMESPACE_BINDINGS: dict[str | None, frozenset[str]] = {
    None: frozenset({
        _PACKAGE_CONTENT_TYPES,
        _PACKAGE_RELATIONSHIPS,
        _SPREADSHEET,
        _DRAWING,
        _CORE_PROPERTIES,
        _EXTENDED_PROPERTIES,
        "http://purl.oclc.org/ooxml/package/content-types",
        "http://purl.oclc.org/ooxml/package/relationships",
        "http://purl.oclc.org/ooxml/spreadsheetml/main",
    }),
    "r": frozenset({
        _OFFICE_RELATIONSHIPS,
        "http://purl.oclc.org/ooxml/officeDocument/relationships",
    }),
    "mc": frozenset({_MARKUP_COMPATIBILITY}),
    "x14ac": frozenset({
        "http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac"
    }),
    "x15": frozenset({
        "http://schemas.microsoft.com/office/spreadsheetml/2010/11/main"
    }),
    "x16r2": frozenset({
        "http://schemas.microsoft.com/office/spreadsheetml/2015/02/main"
    }),
    "xda": frozenset({
        "http://schemas.microsoft.com/office/spreadsheetml/2017/dynamicarray"
    }),
    "xr": frozenset({
        "http://schemas.microsoft.com/office/spreadsheetml/2014/revision"
    }),
    "xr2": frozenset({
        "http://schemas.microsoft.com/office/spreadsheetml/2015/revision2"
    }),
    "xr3": frozenset({
        "http://schemas.microsoft.com/office/spreadsheetml/2016/revision3"
    }),
    "xr6": frozenset({
        "http://schemas.microsoft.com/office/spreadsheetml/2016/revision6"
    }),
    "xr10": frozenset({
        "http://schemas.microsoft.com/office/spreadsheetml/2016/revision10"
    }),
    "xr11": frozenset({
        "http://schemas.microsoft.com/office/spreadsheetml/2016/revision11"
    }),
    "xr12": frozenset({
        "http://schemas.microsoft.com/office/spreadsheetml/2016/revision12"
    }),
    "xr16": frozenset({
        "http://schemas.microsoft.com/office/spreadsheetml/2016/revision16"
    }),
    "a": frozenset({_DRAWING}),
    "cp": frozenset({_CORE_PROPERTIES}),
    "dc": frozenset({"http://purl.org/dc/elements/1.1/"}),
    "dcterms": frozenset({"http://purl.org/dc/terms/"}),
    "dcmitype": frozenset({"http://purl.org/dc/dcmitype/"}),
    "xsi": frozenset({"http://www.w3.org/2001/XMLSchema-instance"}),
    "vt": frozenset({_DOC_PROPERTIES_TYPES}),
}


def _validate_namespaces(text: str) -> None:
    assignments = tuple(_NAMESPACE_ASSIGNMENT.finditer(text))
    declarations = tuple(_NAMESPACE_DECLARATION.finditer(text))
    if len(assignments) != len(declarations):
        raise XlsxInspectionError("XLSX_XML_NAMESPACE_UNMODELED")
    for declaration in declarations:
        prefix = declaration.group("prefix")
        uri = declaration.group("uri")
        if uri not in _ALLOWED_NAMESPACE_BINDINGS.get(prefix, frozenset()):
            raise XlsxInspectionError("XLSX_XML_NAMESPACE_UNMODELED")


def _validate_xml_lexical_content(payload: bytes) -> None:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise XlsxInspectionError("XLSX_XML_ENCODING_UNSUPPORTED") from exc
    if "<!--" in text:
        raise XlsxInspectionError("XLSX_XML_COMMENT_FORBIDDEN")
    without_declaration = _XML_DECLARATION.sub("", text, count=1)
    if "<?" in without_declaration:
        raise XlsxInspectionError(
            "XLSX_XML_PROCESSING_INSTRUCTION_FORBIDDEN"
        )
    _validate_namespaces(without_declaration)


def validate_xml_lexical_content(
    workbook: bytes,
    limits: XlsxInspectionLimits,
) -> None:
    try:
        with ZipFile(BytesIO(workbook)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                path = info.filename.replace("\\", "/").casefold()
                if not path.endswith((".xml", ".rels")):
                    continue
                _validate_xml_lexical_content(
                    _read_limited(zf, info.filename, limits)
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


__all__ = ["validate_xml_lexical_content"]
