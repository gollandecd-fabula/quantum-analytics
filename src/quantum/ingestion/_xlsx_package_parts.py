from __future__ import annotations

from hashlib import sha256
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
_CONTENT_TYPES_NS = (
    "http://schemas.openxmlformats.org/package/2006/content-types"
)
_TYPES = f"{{{_CONTENT_TYPES_NS}}}Types"
_DEFAULT = f"{{{_CONTENT_TYPES_NS}}}Default"
_OVERRIDE = f"{{{_CONTENT_TYPES_NS}}}Override"


def _has_text(value: str | None) -> bool:
    return value is not None and bool(value.strip())


def _safe_content_type(value: str | None) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or len(value) > 255
        or "/" not in value
        or any(character.isspace() or ord(character) < 32 for character in value)
    ):
        raise XlsxInspectionError("XLSX_CONTENT_TYPES_INVALID")
    return value


def _safe_extension(value: str | None) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > 64
        or any(not (character.isalnum() or character in "._-") for character in value)
    ):
        raise XlsxInspectionError("XLSX_CONTENT_TYPES_INVALID")
    return value.casefold()


def _safe_part_name(value: str | None) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value.startswith("/")
        or "\\" in value
        or "//" in value
    ):
        raise XlsxInspectionError("XLSX_CONTENT_TYPES_INVALID")
    pieces = value[1:].split("/")
    if not pieces or any(not piece or piece in {".", ".."} for piece in pieces):
        raise XlsxInspectionError("XLSX_CONTENT_TYPES_INVALID")
    return "/" + "/".join(pieces).casefold()


def _validate_content_types(
    zf: ZipFile,
    limits: XlsxInspectionLimits,
) -> tuple[str, str, int]:
    payload = _read_limited(zf, "[Content_Types].xml", limits)
    root = _xml_root(payload, "XLSX_CONTENT_TYPES_INVALID")
    if (
        root.tag != _TYPES
        or root.attrib
        or _has_text(root.text)
        or _has_text(root.tail)
    ):
        raise XlsxInspectionError("XLSX_CONTENT_TYPES_INVALID")
    names = {
        "/" + _safe_member_name(info.filename).casefold()
        for info in zf.infolist()
        if not info.is_dir()
    }
    defaults: set[str] = set()
    overrides: set[str] = set()
    for child in root:
        if list(child) or _has_text(child.text) or _has_text(child.tail):
            raise XlsxInspectionError("XLSX_CONTENT_TYPES_INVALID")
        if child.tag == _DEFAULT:
            if set(child.attrib) != {"Extension", "ContentType"}:
                raise XlsxInspectionError("XLSX_CONTENT_TYPES_INVALID")
            extension = _safe_extension(child.get("Extension"))
            _safe_content_type(child.get("ContentType"))
            if extension in defaults:
                raise XlsxInspectionError("XLSX_CONTENT_TYPES_INVALID")
            defaults.add(extension)
        elif child.tag == _OVERRIDE:
            if set(child.attrib) != {"PartName", "ContentType"}:
                raise XlsxInspectionError("XLSX_CONTENT_TYPES_INVALID")
            part_name = _safe_part_name(child.get("PartName"))
            _safe_content_type(child.get("ContentType"))
            if part_name not in names or part_name in overrides:
                raise XlsxInspectionError("XLSX_CONTENT_TYPES_INVALID")
            overrides.add(part_name)
        else:
            raise XlsxInspectionError("XLSX_CONTENT_TYPES_INVALID")
    if not defaults or not overrides:
        raise XlsxInspectionError("XLSX_CONTENT_TYPES_INVALID")
    return (
        "[content_types].xml",
        sha256(payload).hexdigest(),
        len(payload),
    )


def validate_modeled_package_parts(
    workbook: bytes,
    limits: XlsxInspectionLimits,
) -> tuple[str, str, int]:
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
            return _validate_content_types(zf, limits)
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
