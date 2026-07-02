from __future__ import annotations

from io import BytesIO
import re
from zipfile import BadZipFile, ZipFile
from zlib import error as ZlibError

from ._xlsx_archive import _read_limited, _xml_root
from ._xlsx_contracts import XlsxInspectionError, XlsxInspectionLimits
from ._xlsx_relationships_core import validate_relationships as _core_validate_relationships

_RELATIONSHIP_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_RELATIONSHIPS = f"{{{_RELATIONSHIP_NS}}}Relationships"
_RELATIONSHIP = f"{{{_RELATIONSHIP_NS}}}Relationship"
_REQUIRED_RELATIONSHIP_ATTRIBUTES = frozenset({"Id", "Type", "Target"})
_OPTIONAL_RELATIONSHIP_ATTRIBUTES = frozenset({"TargetMode"})
_ROOT_RELATIONSHIP_ID = re.compile(r"^(?:rId[1-9][0-9]{0,5}|rCore|rApp|rExt)$")
_ALLOWED_TARGET_MODES = frozenset({"internal", "external"})


def _has_text(value: str | None) -> bool:
    return value is not None and bool(value.strip())


def _validate_root_relationship_structure(
    workbook: bytes,
    limits: XlsxInspectionLimits,
) -> None:
    try:
        with ZipFile(BytesIO(workbook)) as zf:
            root = _xml_root(
                _read_limited(zf, "_rels/.rels", limits),
                "XLSX_ROOT_RELATIONSHIPS_INVALID",
            )
            if (
                root.tag != _RELATIONSHIPS
                or root.attrib
                or _has_text(root.text)
                or _has_text(root.tail)
                or any(child.tag != _RELATIONSHIP for child in root)
            ):
                raise XlsxInspectionError("XLSX_ROOT_RELATIONSHIP_INVALID")
            for relationship in root:
                attributes = set(relationship.attrib)
                relationship_id = relationship.get("Id")
                target_mode = relationship.get("TargetMode")
                if (
                    not _REQUIRED_RELATIONSHIP_ATTRIBUTES.issubset(attributes)
                    or attributes
                    - _REQUIRED_RELATIONSHIP_ATTRIBUTES
                    - _OPTIONAL_RELATIONSHIP_ATTRIBUTES
                    or not isinstance(relationship_id, str)
                    or _ROOT_RELATIONSHIP_ID.fullmatch(relationship_id) is None
                    or (
                        target_mode is not None
                        and (
                            not isinstance(target_mode, str)
                            or target_mode.casefold() not in _ALLOWED_TARGET_MODES
                        )
                    )
                    or list(relationship)
                    or _has_text(relationship.text)
                    or _has_text(relationship.tail)
                ):
                    raise XlsxInspectionError("XLSX_ROOT_RELATIONSHIP_INVALID")
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


def validate_relationships(
    workbook: bytes,
    limits: XlsxInspectionLimits,
) -> tuple[tuple[str, str, str], ...]:
    _validate_root_relationship_structure(workbook, limits)
    return _core_validate_relationships(workbook, limits)


__all__ = ["validate_relationships"]
