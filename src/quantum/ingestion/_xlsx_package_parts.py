from __future__ import annotations

from io import BytesIO
import re
from zipfile import BadZipFile, ZipFile

from ._xlsx_archive import (
    _read_limited,
    _safe_member_name,
    _validate_archive,
    _xml_root,
)
from ._xlsx_contracts import XlsxInspectionError, XlsxInspectionLimits

_ALLOWED_EXACT_PARTS = {
    "[content_types].xml",
    "_rels/.rels",
    "docprops/app.xml",
    "docprops/core.xml",
    "xl/workbook.xml",
    "xl/_rels/workbook.xml.rels",
    "xl/sharedstrings.xml",
    "xl/styles.xml",
    "xl/theme/theme1.xml",
}
_MODELED_AUXILIARY_XML_PARTS = {
    "docprops/app.xml",
    "docprops/core.xml",
    "xl/styles.xml",
    "xl/theme/theme1.xml",
}
_WORKSHEET_PART = re.compile(r"^xl/worksheets/[^/]+[.]xml$")


def validate_modeled_package_parts(
    workbook: bytes,
    limits: XlsxInspectionLimits,
) -> None:
    try:
        with ZipFile(BytesIO(workbook)) as zf:
            _validate_archive(zf, limits)
            for info in zf.infolist():
                if info.is_dir():
                    continue
                part = _safe_member_name(info.filename).casefold()
                if (
                    part not in _ALLOWED_EXACT_PARTS
                    and _WORKSHEET_PART.fullmatch(part) is None
                ):
                    raise XlsxInspectionError("XLSX_PACKAGE_PART_UNMODELED")
                if part in _MODELED_AUXILIARY_XML_PARTS:
                    payload = _read_limited(zf, info.filename, limits)
                    _xml_root(payload, "XLSX_AUXILIARY_PART_INVALID")
    except XlsxInspectionError:
        raise
    except (
        BadZipFile,
        NotImplementedError,
        ValueError,
        OSError,
        EOFError,
    ) as exc:
        raise XlsxInspectionError("XLSX_ARCHIVE_INVALID") from exc
