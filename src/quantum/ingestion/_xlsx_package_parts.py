from __future__ import annotations

from io import BytesIO
import re
from zipfile import BadZipFile, ZipFile

from ._xlsx_archive import _safe_member_name
from ._xlsx_contracts import XlsxInspectionError

_ALLOWED_EXACT_PARTS = {
    "[content_types].xml",
    "_rels/.rels",
    "xl/workbook.xml",
    "xl/_rels/workbook.xml.rels",
    "xl/sharedstrings.xml",
}
_WORKSHEET_PART = re.compile(r"^xl/worksheets/[^/]+[.]xml$")


def validate_modeled_package_parts(workbook: bytes) -> None:
    try:
        with ZipFile(BytesIO(workbook)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                part = _safe_member_name(info.filename).casefold()
                if (
                    part in _ALLOWED_EXACT_PARTS
                    or _WORKSHEET_PART.fullmatch(part) is not None
                ):
                    continue
                raise XlsxInspectionError("XLSX_PACKAGE_PART_UNMODELED")
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
