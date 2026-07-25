from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from zipfile import BadZipFile, ZipFile
from zlib import error as ZlibError

from ._xlsx_archive import _read_limited, _xml_root
from ._xlsx_contracts import XlsxInspectionError, XlsxInspectionLimits


_MAX_PASSIVE_PART_BYTES = 8 * 1024 * 1024
_SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_CORE_PROPERTIES_NS = (
    "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
)
_EXTENDED_PROPERTIES_NS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
)
_DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"

_PASSIVE_ROOTS = {
    "docprops/app.xml": frozenset(
        {"Properties", f"{{{_EXTENDED_PROPERTIES_NS}}}Properties"}
    ),
    "docprops/core.xml": frozenset(
        {"coreProperties", f"{{{_CORE_PROPERTIES_NS}}}coreProperties"}
    ),
    "xl/styles.xml": frozenset(
        {"styleSheet", f"{{{_SPREADSHEET_NS}}}styleSheet"}
    ),
    "xl/theme/theme1.xml": frozenset(
        {"theme", f"{{{_DRAWING_NS}}}theme"}
    ),
}
_BLOCKED_NAMESPACE_MARKERS = (
    "activex",
    "customui",
    "office/2006/relationships",
    "ole",
)
_BLOCKED_LOCAL_TAGS = frozenset(
    {
        "script",
        "object",
        "oleobject",
        "externalLink",
        "externalBook",
        "connection",
        "webPublishObject",
    }
)


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[-1] if tag.startswith("{") else tag


def _namespace(tag: str) -> str:
    return tag[1:].split("}", 1)[0] if tag.startswith("{") and "}" in tag else ""


def _validate_passive_tree(path: str, root) -> None:
    if root.tag not in _PASSIVE_ROOTS[path]:
        raise XlsxInspectionError("XLSX_AUXILIARY_COMPAT_ROOT_INVALID")
    for element in root.iter():
        namespace = _namespace(element.tag).casefold()
        local = _local_name(element.tag)
        if any(marker in namespace for marker in _BLOCKED_NAMESPACE_MARKERS):
            raise XlsxInspectionError("XLSX_AUXILIARY_COMPAT_ACTIVE_CONTENT")
        if local.casefold() in {item.casefold() for item in _BLOCKED_LOCAL_TAGS}:
            raise XlsxInspectionError("XLSX_AUXILIARY_COMPAT_ACTIVE_CONTENT")
        for attribute_name, attribute_value in element.attrib.items():
            attribute_namespace = _namespace(attribute_name).casefold()
            if any(marker in attribute_namespace for marker in _BLOCKED_NAMESPACE_MARKERS):
                raise XlsxInspectionError("XLSX_AUXILIARY_COMPAT_ACTIVE_CONTENT")
            if len(attribute_value) > 32767:
                raise XlsxInspectionError("XLSX_AUXILIARY_COMPAT_VALUE_LIMIT_EXCEEDED")
        if element.text is not None and len(element.text) > 32767:
            raise XlsxInspectionError("XLSX_AUXILIARY_COMPAT_VALUE_LIMIT_EXCEEDED")


def hash_passive_auxiliary_parts(
    workbook: bytes,
    limits: XlsxInspectionLimits,
) -> tuple[tuple[str, str, int], ...]:
    """Hash-bind bounded, non-semantic Office metadata in HOME_LOCAL mode."""
    auxiliary: list[tuple[str, str, int]] = []
    try:
        with ZipFile(BytesIO(workbook)) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                normalized = info.filename.replace("\\", "/").casefold()
                if normalized not in _PASSIVE_ROOTS:
                    continue
                if info.file_size > min(
                    _MAX_PASSIVE_PART_BYTES,
                    limits.max_xml_bytes,
                ):
                    raise XlsxInspectionError(
                        "XLSX_AUXILIARY_COMPAT_SIZE_EXCEEDED"
                    )
                payload = _read_limited(archive, info.filename, limits)
                root = _xml_root(
                    payload,
                    "XLSX_AUXILIARY_COMPAT_XML_INVALID",
                )
                _validate_passive_tree(normalized, root)
                auxiliary.append(
                    (
                        "compat-passive:" + normalized,
                        sha256(payload).hexdigest(),
                        len(payload),
                    )
                )
        return tuple(sorted(auxiliary))
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


__all__ = ["hash_passive_auxiliary_parts"]
