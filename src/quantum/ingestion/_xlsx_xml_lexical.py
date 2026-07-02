from __future__ import annotations

from io import BytesIO
import re
from zipfile import BadZipFile, ZipFile
from zlib import error as ZlibError

from ._xlsx_archive import _read_limited
from ._xlsx_contracts import XlsxInspectionError, XlsxInspectionLimits

_XML_DECLARATION = re.compile(r"^\s*<\?xml(?:\s+[^?]*)?\?>", re.IGNORECASE)


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
