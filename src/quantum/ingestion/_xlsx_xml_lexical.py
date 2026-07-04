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

_ALLOWED_NAMESPACE_BINDINGS: dict[str | None, frozenset[str]] = {
    None: frozenset({
        'http://purl.oclc.org/ooxml/package/content-types',
        'http://purl.oclc.org/ooxml/package/relationships',
        'http://purl.oclc.org/ooxml/spreadsheetml/main',
        'http://schemas.openxmlformats.org/drawingml/2006/main',
        'http://schemas.openxmlformats.org/officeDocument/2006/extended-properties',
        'http://schemas.openxmlformats.org/package/2006/content-types',
        'http://schemas.openxmlformats.org/package/2006/metadata/core-properties',
        'http://schemas.openxmlformats.org/package/2006/relationships',
        'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
    }),
    'a': frozenset({
        'http://schemas.openxmlformats.org/drawingml/2006/main',
    }),
    'a14': frozenset({
        'http://schemas.microsoft.com/office/drawing/2010/main',
    }),
    'ap': frozenset({
        'http://schemas.openxmlformats.org/officeDocument/2006/extended-properties',
    }),
    'ax': frozenset({
        'http://schemas.microsoft.com/office/2006/activeX',
    }),
    'c': frozenset({
        'http://schemas.openxmlformats.org/drawingml/2006/chart',
    }),
    'c14': frozenset({
        'http://schemas.microsoft.com/office/drawing/2007/8/2/chart',
    }),
    'cdip': frozenset({
        'http://schemas.microsoft.com/office/2006/customDocumentInformationPanel',
    }),
    'cdr': frozenset({
        'http://schemas.openxmlformats.org/drawingml/2006/chartDrawing',
    }),
    'cdr14': frozenset({
        'http://schemas.microsoft.com/office/drawing/2010/chartDrawing',
    }),
    'comp': frozenset({
        'http://schemas.openxmlformats.org/drawingml/2006/compatibility',
    }),
    'cp': frozenset({
        'http://schemas.openxmlformats.org/package/2006/metadata/core-properties',
    }),
    'cppr': frozenset({
        'http://schemas.microsoft.com/office/2006/coverPageProps',
    }),
    'ct': frozenset({
        'http://schemas.microsoft.com/office/2006/metadata/contentType',
    }),
    'dc': frozenset({
        'http://purl.org/dc/elements/1.1/',
    }),
    'dcmitype': frozenset({
        'http://purl.org/dc/dcmitype/',
    }),
    'dcterms': frozenset({
        'http://purl.org/dc/terms/',
    }),
    'dgm': frozenset({
        'http://schemas.openxmlformats.org/drawingml/2006/diagram',
    }),
    'dgm14': frozenset({
        'http://schemas.microsoft.com/office/drawing/2010/diagram',
    }),
    'ds': frozenset({
        'http://schemas.openxmlformats.org/officeDocument/2006/customXml',
    }),
    'dsp': frozenset({
        'http://schemas.microsoft.com/office/drawing/2008/diagram',
    }),
    'lc': frozenset({
        'http://schemas.openxmlformats.org/drawingml/2006/lockedCanvas',
    }),
    'lp': frozenset({
        'http://schemas.microsoft.com/office/2006/metadata/longProperties',
    }),
    'm': frozenset({
        'http://schemas.openxmlformats.org/officeDocument/2006/math',
    }),
    'ma': frozenset({
        'http://schemas.microsoft.com/office/2006/metadata/properties/metaAttributes',
    }),
    'mc': frozenset({
        'http://schemas.openxmlformats.org/markup-compatibility/2006',
    }),
    'mo': frozenset({
        'http://schemas.microsoft.com/office/mac/office/2008/main',
    }),
    'msink': frozenset({
        'http://schemas.microsoft.com/ink/2010/main',
    }),
    'mso': frozenset({
        'http://schemas.microsoft.com/office/2006/01/customui',
    }),
    'mso14': frozenset({
        'http://schemas.microsoft.com/office/2009/07/customui',
    }),
    'mv': frozenset({
        'urn:schemas-microsoft-com:mac:vml',
    }),
    'mx': frozenset({
        'http://schemas.microsoft.com/office/mac/excel/2008/main',
    }),
    'ntns': frozenset({
        'http://schemas.microsoft.com/office/2006/metadata/customXsn',
    }),
    'o': frozenset({
        'urn:schemas-microsoft-com:office:office',
    }),
    'op': frozenset({
        'http://schemas.openxmlformats.org/officeDocument/2006/custom-properties',
    }),
    'pic': frozenset({
        'http://schemas.openxmlformats.org/drawingml/2006/picture',
    }),
    'pic14': frozenset({
        'http://schemas.microsoft.com/office/drawing/2010/picture',
    }),
    'r': frozenset({
        'http://purl.oclc.org/ooxml/officeDocument/relationships',
        'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    }),
    'sl': frozenset({
        'http://schemas.openxmlformats.org/schemaLibrary/2006/main',
    }),
    'v': frozenset({
        'urn:schemas-microsoft-com:vml',
    }),
    'vt': frozenset({
        'http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes',
    }),
    'x': frozenset({
        'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
    }),
    'x12ac': frozenset({
        'http://schemas.microsoft.com/office/spreadsheetml/2011/1/ac',
    }),
    'x14': frozenset({
        'http://schemas.microsoft.com/office/spreadsheetml/2009/9/main',
    }),
    'x14ac': frozenset({
        'http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac',
    }),
    'x15': frozenset({
        'http://schemas.microsoft.com/office/spreadsheetml/2010/11/main',
    }),
    'x15ac': frozenset({
        'http://schemas.microsoft.com/office/spreadsheetml/2010/11/ac',
    }),
    'x16': frozenset({
        'http://schemas.microsoft.com/office/spreadsheetml/2014/11/main',
    }),
    'x16r2': frozenset({
        'http://schemas.microsoft.com/office/spreadsheetml/2015/02/main',
    }),
    'xda': frozenset({
        'http://schemas.microsoft.com/office/spreadsheetml/2017/dynamicarray',
    }),
    'xdr': frozenset({
        'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing',
    }),
    'xdr14': frozenset({
        'http://schemas.microsoft.com/office/excel/2010/spreadsheetDrawing',
    }),
    'xne': frozenset({
        'http://schemas.microsoft.com/office/excel/2006/main',
    }),
    'xr': frozenset({
        'http://schemas.microsoft.com/office/spreadsheetml/2014/revision',
    }),
    'xr10': frozenset({
        'http://schemas.microsoft.com/office/spreadsheetml/2016/revision10',
    }),
    'xr11': frozenset({
        'http://schemas.microsoft.com/office/spreadsheetml/2016/revision11',
    }),
    'xr12': frozenset({
        'http://schemas.microsoft.com/office/spreadsheetml/2016/revision12',
    }),
    'xr13': frozenset({
        'http://schemas.microsoft.com/office/spreadsheetml/2016/revision13',
    }),
    'xr14': frozenset({
        'http://schemas.microsoft.com/office/spreadsheetml/2016/revision14',
    }),
    'xr15': frozenset({
        'http://schemas.microsoft.com/office/spreadsheetml/2016/revision15',
    }),
    'xr16': frozenset({
        'http://schemas.microsoft.com/office/spreadsheetml/2016/revision16',
    }),
    'xr2': frozenset({
        'http://schemas.microsoft.com/office/spreadsheetml/2015/revision2',
    }),
    'xr3': frozenset({
        'http://schemas.microsoft.com/office/spreadsheetml/2016/revision3',
    }),
    'xr4': frozenset({
        'http://schemas.microsoft.com/office/spreadsheetml/2016/revision4',
    }),
    'xr5': frozenset({
        'http://schemas.microsoft.com/office/spreadsheetml/2016/revision5',
    }),
    'xr6': frozenset({
        'http://schemas.microsoft.com/office/spreadsheetml/2016/revision6',
    }),
    'xr7': frozenset({
        'http://schemas.microsoft.com/office/spreadsheetml/2016/revision7',
    }),
    'xr8': frozenset({
        'http://schemas.microsoft.com/office/spreadsheetml/2016/revision8',
    }),
    'xr9': frozenset({
        'http://schemas.microsoft.com/office/spreadsheetml/2016/revision9',
    }),
    'xsi': frozenset({
        'http://www.w3.org/2001/XMLSchema-instance',
    }),
}


def _validate_namespaces(text: str) -> None:
    assignments = tuple(_NAMESPACE_ASSIGNMENT.finditer(text))
    declarations = tuple(_NAMESPACE_DECLARATION.finditer(text))
    if len(assignments) != len(declarations):
        raise XlsxInspectionError("XLSX_XML_NAMESPACE_UNMODELED")
    prefixes = tuple(declaration.group("prefix") for declaration in declarations)
    if len(set(prefixes)) != len(prefixes):
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
