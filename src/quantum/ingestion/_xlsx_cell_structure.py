from __future__ import annotations

from io import BytesIO
from zipfile import BadZipFile, ZipFile
from zlib import error as ZlibError

from ._xlsx_archive import (
    _SPREADSHEET_NS,
    _read_limited,
    _xml_root,
)
from ._xlsx_contracts import XlsxInspectionError, XlsxInspectionLimits

_ALLOWED_CELL_CHILDREN = frozenset({
    f"{{{_SPREADSHEET_NS}}}f",
    f"{{{_SPREADSHEET_NS}}}v",
    f"{{{_SPREADSHEET_NS}}}is",
})


def _shared_string_count(
    zf: ZipFile,
    limits: XlsxInspectionLimits,
) -> int | None:
    try:
        payload = _read_limited(zf, "xl/sharedStrings.xml", limits)
    except XlsxInspectionError as exc:
        if exc.code == "XLSX_REQUIRED_PART_MISSING":
            return None
        raise
    root = _xml_root(payload, "XLSX_SHARED_STRINGS_INVALID")
    entries = root.findall(f"{{{_SPREADSHEET_NS}}}si")
    if len(root.findall(f".//{{{_SPREADSHEET_NS}}}si")) != len(entries):
        raise XlsxInspectionError("XLSX_SHARED_STRINGS_INVALID")
    return len(entries)


def validate_cell_structures(
    workbook: bytes,
    limits: XlsxInspectionLimits,
) -> None:
    try:
        with ZipFile(BytesIO(workbook)) as zf:
            shared_count = _shared_string_count(zf, limits)
            used_shared_indexes: set[int] = set()
            for info in zf.infolist():
                path = info.filename.replace("\\", "/").casefold()
                if (
                    info.is_dir()
                    or not path.startswith("xl/worksheets/")
                    or not path.endswith(".xml")
                ):
                    continue
                root = _xml_root(
                    _read_limited(zf, info.filename, limits),
                    "XLSX_WORKSHEET_INVALID",
                )
                for cell in root.iter(f"{{{_SPREADSHEET_NS}}}c"):
                    if any(child.tag not in _ALLOWED_CELL_CHILDREN for child in cell):
                        raise XlsxInspectionError("XLSX_CELL_CHILD_UNMODELED")
                    formula_nodes = cell.findall(f"{{{_SPREADSHEET_NS}}}f")
                    value_nodes = cell.findall(f"{{{_SPREADSHEET_NS}}}v")
                    inline_nodes = cell.findall(f"{{{_SPREADSHEET_NS}}}is")
                    if (
                        len(formula_nodes) > 1
                        or len(value_nodes) > 1
                        or len(inline_nodes) > 1
                    ):
                        raise XlsxInspectionError(
                            "XLSX_CELL_STRUCTURE_INVALID"
                        )
                    cell_type = cell.get("t")
                    if cell_type == "inlineStr":
                        if len(inline_nodes) != 1 or value_nodes:
                            raise XlsxInspectionError(
                                "XLSX_CELL_STRUCTURE_INVALID"
                            )
                    elif inline_nodes:
                        raise XlsxInspectionError(
                            "XLSX_CELL_STRUCTURE_INVALID"
                        )
                    if cell_type == "s":
                        if len(value_nodes) != 1:
                            raise XlsxInspectionError(
                                "XLSX_CELL_STRUCTURE_INVALID"
                            )
                        raw_index = value_nodes[0].text or ""
                        try:
                            index = int(raw_index)
                        except ValueError as exc:
                            raise XlsxInspectionError(
                                "XLSX_SHARED_STRING_REFERENCE_INVALID"
                            ) from exc
                        if (
                            shared_count is None
                            or index < 0
                            or index >= shared_count
                        ):
                            raise XlsxInspectionError(
                                "XLSX_SHARED_STRING_REFERENCE_INVALID"
                            )
                        used_shared_indexes.add(index)
            if shared_count is not None and used_shared_indexes != set(range(shared_count)):
                raise XlsxInspectionError("XLSX_SHARED_STRING_UNUSED")
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
