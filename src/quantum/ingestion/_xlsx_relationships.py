from __future__ import annotations

from io import BytesIO
import re
from zipfile import BadZipFile, ZipFile
from zlib import error as ZlibError

from ._xlsx_archive import _read_limited, _xml_root
from ._xlsx_contracts import XlsxInspectionError, XlsxInspectionLimits

_RELATIONSHIP_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_OFFICE_RELATIONSHIP_NS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)
_SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_OFFICE_DOCUMENT_RELATIONSHIP_TYPES = {
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument",
    "http://purl.oclc.org/ooxml/officeDocument/relationships/officeDocument",
}
_WORKSHEET_RELATIONSHIP_TYPES = {
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet",
    "http://purl.oclc.org/ooxml/officeDocument/relationships/worksheet",
}
_URI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def _reject_external_target(target: str, target_mode: str | None) -> None:
    normalized = target.replace("\\", "/")
    if (
        isinstance(target_mode, str)
        and target_mode.casefold() == "external"
    ) or normalized.startswith("//") or _URI_SCHEME.match(normalized):
        raise XlsxInspectionError("XLSX_EXTERNAL_RELATIONSHIP_FORBIDDEN")


def _validate_root_binding(zf: ZipFile, limits: XlsxInspectionLimits) -> None:
    root = _xml_root(
        _read_limited(zf, "_rels/.rels", limits),
        "XLSX_ROOT_RELATIONSHIPS_INVALID",
    )
    relationships = root.findall(f"{{{_RELATIONSHIP_NS}}}Relationship")
    if len(relationships) != 1:
        raise XlsxInspectionError("XLSX_ROOT_RELATIONSHIP_INVALID")
    relationship = relationships[0]
    _reject_external_target(
        relationship.get("Target") or "",
        relationship.get("TargetMode"),
    )
    if relationship.get("Type") not in _OFFICE_DOCUMENT_RELATIONSHIP_TYPES:
        raise XlsxInspectionError("XLSX_ROOT_RELATIONSHIP_INVALID")
    target = (relationship.get("Target") or "").replace("\\", "/")
    if target.startswith("/"):
        target = target[1:]
    if target.casefold() != "xl/workbook.xml":
        raise XlsxInspectionError("XLSX_ROOT_RELATIONSHIP_INVALID")


def validate_relationships(
    workbook: bytes,
    limits: XlsxInspectionLimits,
) -> None:
    try:
        with ZipFile(BytesIO(workbook)) as zf:
            for info in zf.infolist():
                if not info.filename.casefold().endswith(".rels"):
                    continue
                root = _xml_root(
                    _read_limited(zf, info.filename, limits),
                    "XLSX_RELATIONSHIPS_INVALID",
                )
                for relation in root.findall(
                    f"{{{_RELATIONSHIP_NS}}}Relationship"
                ):
                    _reject_external_target(
                        relation.get("Target") or "",
                        relation.get("TargetMode"),
                    )

            _validate_root_binding(zf, limits)

            workbook_root = _xml_root(
                _read_limited(zf, "xl/workbook.xml", limits),
                "XLSX_WORKBOOK_INVALID",
            )
            relation_root = _xml_root(
                _read_limited(zf, "xl/_rels/workbook.xml.rels", limits),
                "XLSX_WORKBOOK_RELATIONSHIPS_INVALID",
            )
            relationship_types: dict[str, str] = {}
            for relation in relation_root.findall(
                f"{{{_RELATIONSHIP_NS}}}Relationship"
            ):
                relation_id = relation.get("Id")
                if relation_id:
                    relationship_types[relation_id] = relation.get("Type") or ""
            sheets = workbook_root.find(f"{{{_SPREADSHEET_NS}}}sheets")
            if sheets is None:
                raise XlsxInspectionError("XLSX_SHEETS_MISSING")
            for sheet in sheets.findall(f"{{{_SPREADSHEET_NS}}}sheet"):
                relation_id = sheet.get(f"{{{_OFFICE_RELATIONSHIP_NS}}}id")
                if not relation_id or relation_id not in relationship_types:
                    raise XlsxInspectionError("XLSX_SHEET_RELATIONSHIP_MISSING")
                relationship_type = relationship_types[relation_id]
                if relationship_type not in _WORKSHEET_RELATIONSHIP_TYPES:
                    raise XlsxInspectionError(
                        "XLSX_WORKSHEET_RELATIONSHIP_TYPE_INVALID"
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
