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
_RELATIONSHIPS = f"{{{_RELATIONSHIP_NS}}}Relationships"
_RELATIONSHIP = f"{{{_RELATIONSHIP_NS}}}Relationship"
_OFFICE_DOCUMENT_RELATIONSHIP_TYPES = {
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument",
    "http://purl.oclc.org/ooxml/officeDocument/relationships/officeDocument",
}
_CORE_PROPERTIES_RELATIONSHIP_TYPES = {
    "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties",
    "http://purl.oclc.org/ooxml/package/relationships/metadata/core-properties",
}
_EXTENDED_PROPERTIES_RELATIONSHIP_TYPES = {
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties",
    "http://purl.oclc.org/ooxml/officeDocument/relationships/extended-properties",
}
_WORKSHEET_RELATIONSHIP_TYPES = {
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet",
    "http://purl.oclc.org/ooxml/officeDocument/relationships/worksheet",
}
_URI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_WORKBOOK_RELATIONSHIP_ID = re.compile(
    r"^(?:rId[1-9][0-9]{0,5}|rStyles|rTheme|rSharedStrings)$"
)
_AUXILIARY_TARGETS = {
    "styles": "xl/styles.xml",
    "theme": "xl/theme/theme1.xml",
    "sharedStrings": "xl/sharedstrings.xml",
}
_ALLOWED_RELATIONSHIP_ATTRIBUTES = frozenset({"Id", "Type", "Target"})


def _has_text(value: str | None) -> bool:
    return value is not None and bool(value.strip())


def _valid_workbook_relationship_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and value == value.strip()
        and _WORKBOOK_RELATIONSHIP_ID.fullmatch(value) is not None
    )


def _reject_external_target(target: str, target_mode: str | None) -> None:
    normalized = target.replace("\\", "/")
    if (
        isinstance(target_mode, str)
        and target_mode.casefold() == "external"
    ) or normalized.startswith("//") or _URI_SCHEME.match(normalized):
        raise XlsxInspectionError("XLSX_EXTERNAL_RELATIONSHIP_FORBIDDEN")


def _root_target(target: str) -> str:
    normalized = target.replace("\\", "/")
    if normalized.startswith("/"):
        normalized = normalized[1:]
    return normalized.casefold()


def _workbook_target(target: str) -> str:
    normalized = target.replace("\\", "/")
    if normalized.startswith("/") or "//" in normalized:
        raise XlsxInspectionError("XLSX_WORKBOOK_RELATIONSHIPS_INVALID")
    pieces = normalized.split("/")
    if any(not piece or piece in {".", ".."} for piece in pieces):
        raise XlsxInspectionError("XLSX_WORKBOOK_RELATIONSHIPS_INVALID")
    return "xl/" + "/".join(pieces).casefold()


def _validate_root_binding(zf: ZipFile, limits: XlsxInspectionLimits) -> None:
    root = _xml_root(
        _read_limited(zf, "_rels/.rels", limits),
        "XLSX_ROOT_RELATIONSHIPS_INVALID",
    )
    names = {
        info.filename.replace("\\", "/").casefold()
        for info in zf.infolist()
        if not info.is_dir()
    }
    office_document_count = 0
    auxiliary_targets: set[str] = set()
    relationship_ids: set[str] = set()
    for relationship in root.findall(_RELATIONSHIP):
        raw_relationship_id = relationship.get("Id")
        if not isinstance(raw_relationship_id, str):
            raise XlsxInspectionError("XLSX_ROOT_RELATIONSHIP_INVALID")
        relationship_id = raw_relationship_id.strip()
        if (
            not relationship_id
            or relationship_id != raw_relationship_id
            or relationship_id in relationship_ids
        ):
            raise XlsxInspectionError("XLSX_ROOT_RELATIONSHIP_INVALID")
        relationship_ids.add(relationship_id)
        target_value = relationship.get("Target") or ""
        _reject_external_target(
            target_value,
            relationship.get("TargetMode"),
        )
        relationship_type = relationship.get("Type") or ""
        target = _root_target(target_value)
        if relationship_type in _OFFICE_DOCUMENT_RELATIONSHIP_TYPES:
            if target != "xl/workbook.xml":
                raise XlsxInspectionError("XLSX_ROOT_RELATIONSHIP_INVALID")
            office_document_count += 1
            continue
        if relationship_type in _CORE_PROPERTIES_RELATIONSHIP_TYPES:
            expected_target = "docprops/core.xml"
        elif relationship_type in _EXTENDED_PROPERTIES_RELATIONSHIP_TYPES:
            expected_target = "docprops/app.xml"
        else:
            raise XlsxInspectionError("XLSX_ROOT_RELATIONSHIP_INVALID")
        if (
            target != expected_target
            or target not in names
            or target in auxiliary_targets
        ):
            raise XlsxInspectionError("XLSX_ROOT_RELATIONSHIP_INVALID")
        auxiliary_targets.add(target)
    if office_document_count != 1:
        raise XlsxInspectionError("XLSX_ROOT_RELATIONSHIP_INVALID")


def validate_relationships(
    workbook: bytes,
    limits: XlsxInspectionLimits,
) -> tuple[tuple[str, str, str], ...]:
    try:
        with ZipFile(BytesIO(workbook)) as zf:
            for info in zf.infolist():
                if not info.filename.casefold().endswith(".rels"):
                    continue
                root = _xml_root(
                    _read_limited(zf, info.filename, limits),
                    "XLSX_RELATIONSHIPS_INVALID",
                )
                for relation in root.findall(_RELATIONSHIP):
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
            if (
                relation_root.tag != _RELATIONSHIPS
                or relation_root.attrib
                or _has_text(relation_root.text)
                or _has_text(relation_root.tail)
                or any(child.tag != _RELATIONSHIP for child in relation_root)
            ):
                raise XlsxInspectionError("XLSX_WORKBOOK_RELATIONSHIPS_INVALID")

            sheets = workbook_root.find(f"{{{_SPREADSHEET_NS}}}sheets")
            if sheets is None:
                raise XlsxInspectionError("XLSX_SHEETS_MISSING")
            referenced_ids: set[str] = set()
            for sheet in sheets.findall(f"{{{_SPREADSHEET_NS}}}sheet"):
                relation_id = sheet.get(f"{{{_OFFICE_RELATIONSHIP_NS}}}id")
                if (
                    not _valid_workbook_relationship_id(relation_id)
                    or relation_id in referenced_ids
                ):
                    raise XlsxInspectionError("XLSX_SHEET_RELATIONSHIP_MISSING")
                referenced_ids.add(relation_id)

            names = {
                info.filename.replace("\\", "/").casefold()
                for info in zf.infolist()
                if not info.is_dir()
            }
            seen_ids: set[str] = set()
            seen_targets: set[str] = set()
            worksheet_ids: set[str] = set()
            auxiliary_kinds: set[str] = set()
            evidence: list[tuple[str, str, str]] = []
            for relation in relation_root:
                if (
                    set(relation.attrib) != _ALLOWED_RELATIONSHIP_ATTRIBUTES
                    or list(relation)
                    or _has_text(relation.text)
                    or _has_text(relation.tail)
                ):
                    raise XlsxInspectionError("XLSX_WORKBOOK_RELATIONSHIPS_INVALID")
                relation_id = relation.get("Id")
                relation_type = relation.get("Type")
                raw_target = relation.get("Target")
                if (
                    not _valid_workbook_relationship_id(relation_id)
                    or relation_id in seen_ids
                    or not isinstance(relation_type, str)
                    or relation_type != relation_type.strip()
                    or not relation_type
                ):
                    raise XlsxInspectionError("XLSX_WORKBOOK_RELATIONSHIPS_INVALID")
                seen_ids.add(relation_id)
                target = _workbook_target(raw_target or "")
                if target not in names or target in seen_targets:
                    raise XlsxInspectionError("XLSX_WORKBOOK_RELATIONSHIPS_INVALID")
                seen_targets.add(target)

                if relation_type in _WORKSHEET_RELATIONSHIP_TYPES:
                    if relation_id not in referenced_ids:
                        raise XlsxInspectionError(
                            "XLSX_WORKBOOK_RELATIONSHIP_UNREFERENCED"
                        )
                    worksheet_ids.add(relation_id)
                else:
                    kind = relation_type.rsplit("/", 1)[-1]
                    expected_target = _AUXILIARY_TARGETS.get(kind)
                    if (
                        relation_id in referenced_ids
                        or expected_target != target
                        or kind in auxiliary_kinds
                    ):
                        if relation_id in referenced_ids:
                            raise XlsxInspectionError(
                                "XLSX_WORKSHEET_RELATIONSHIP_TYPE_INVALID"
                            )
                        raise XlsxInspectionError(
                            "XLSX_WORKBOOK_RELATIONSHIPS_INVALID"
                        )
                    auxiliary_kinds.add(kind)
                evidence.append((relation_id, relation_type, target))

            if worksheet_ids != referenced_ids:
                raise XlsxInspectionError("XLSX_SHEET_RELATIONSHIP_MISSING")
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
