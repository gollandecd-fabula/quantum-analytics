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


def validate_cell_structures(
    workbook: bytes,
    limits: XlsxInspectionLimits,
) -> None:
    try:
        with ZipFile(BytesIO(workbook)) as zf:
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
                    if cell_type == "s" and len(value_nodes) != 1:
                        raise XlsxInspectionError(
                            "XLSX_CELL_STRUCTURE_INVALID"
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
