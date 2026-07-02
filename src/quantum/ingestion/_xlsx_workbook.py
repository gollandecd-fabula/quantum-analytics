from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from zipfile import BadZipFile, ZipFile
from zlib import error as ZlibError

from ._xlsx_archive import (
    _XLSX_REQUIRED_PARTS,
    _cell_position,
    _cell_text,
    _read_limited,
    _relationship_target,
    _shared_strings,
    _validate_archive,
    _xml_root,
)
from ._xlsx_contracts import (
    XlsxInspectionError,
    XlsxInspectionPolicy,
    _normalized_header,
    _normalized_sensitive_token,
    _safe_text,
    normalized_header_sha256,
)

_RELATIONSHIP_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_OFFICE_RELATIONSHIP_NS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)
_SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_ALLOWED_WORKSHEET_STRUCTURE_TAGS = frozenset({
    "sheetPr",
    "outlinePr",
    "pageSetUpPr",
    "dimension",
    "sheetViews",
    "sheetView",
    "pane",
    "selection",
    "sheetFormatPr",
    "cols",
    "col",
    "mergeCells",
    "mergeCell",
    "printOptions",
    "pageMargins",
    "pageSetup",
    "sheetProtection",
    "phoneticPr",
})


@dataclass(frozen=True, slots=True)
class _ParsedWorksheet:
    rows: dict[int, dict[int, str]]
    nonempty_rows: frozenset[int]
    formula_count: int
    max_used_column: int


@dataclass(frozen=True, slots=True)
class _WorkbookShape:
    sheet_name: str
    sheet_count: int
    header_row_index: int
    header_sha256: str
    column_count: int
    max_used_column: int
    unmodeled_worksheet_count: int
    data_row_count: int
    formula_count: int
    prohibited_header_count: int


def _worksheet_local_name(tag: object) -> str:
    prefix = f"{{{_SPREADSHEET_NS}}}"
    if not isinstance(tag, str) or not tag.startswith(prefix):
        raise XlsxInspectionError("XLSX_WORKSHEET_ELEMENT_UNMODELED")
    return tag[len(prefix):]


def _validate_unmodeled_worksheet_nodes(
    sheet_root,
    sheet_data,
) -> None:
    for child in list(sheet_root):
        if child is sheet_data:
            continue
        elements = tuple(child.iter())
        if any(
            (element.text is not None and element.text.strip())
            or (element.tail is not None and element.tail.strip())
            for element in elements
        ):
            raise XlsxInspectionError("XLSX_UNMODELED_WORKSHEET_TEXT")
        for element in elements:
            if _worksheet_local_name(element.tag) not in _ALLOWED_WORKSHEET_STRUCTURE_TAGS:
                raise XlsxInspectionError("XLSX_WORKSHEET_ELEMENT_UNMODELED")


def _parse_worksheet(
    zf: ZipFile,
    *,
    sheet_path: str,
    limits,
    shared: tuple[str, ...],
) -> _ParsedWorksheet:
    sheet_payload = _read_limited(zf, sheet_path, limits)
    sheet_root = _xml_root(sheet_payload, "XLSX_WORKSHEET_INVALID")
    sheet_data_nodes = sheet_root.findall(f"{{{_SPREADSHEET_NS}}}sheetData")
    if len(sheet_data_nodes) != 1:
        raise XlsxInspectionError("XLSX_SHEET_DATA_STRUCTURE_INVALID")
    sheet_data = sheet_data_nodes[0]
    _validate_unmodeled_worksheet_nodes(sheet_root, sheet_data)
    rows = sheet_data.findall(f"{{{_SPREADSHEET_NS}}}row")
    if len(sheet_data.findall(f".//{{{_SPREADSHEET_NS}}}row")) != len(rows):
        raise XlsxInspectionError("XLSX_ROW_STRUCTURE_INVALID")
    if len(sheet_root.findall(f".//{{{_SPREADSHEET_NS}}}row")) != len(rows):
        raise XlsxInspectionError("XLSX_ROW_OUTSIDE_SHEET_DATA")
    if len(rows) > limits.max_rows:
        raise XlsxInspectionError("XLSX_ROW_LIMIT_EXCEEDED")
    direct_cell_count = sum(
        len(row.findall(f"{{{_SPREADSHEET_NS}}}c")) for row in rows
    )
    if len(sheet_data.findall(f".//{{{_SPREADSHEET_NS}}}c")) != direct_cell_count:
        raise XlsxInspectionError("XLSX_CELL_OUTSIDE_ROW")
    if len(sheet_root.findall(f".//{{{_SPREADSHEET_NS}}}c")) != direct_cell_count:
        raise XlsxInspectionError("XLSX_CELL_OUTSIDE_SHEET_DATA")

    parsed_rows: dict[int, dict[int, str]] = {}
    nonempty_rows: set[int] = set()
    formula_count = 0
    max_used_column = 0
    prior_row_index = 0
    for row in rows:
        raw_index = row.get("r")
        try:
            row_index = int(raw_index or "0")
        except ValueError as exc:
            raise XlsxInspectionError("XLSX_ROW_INDEX_INVALID") from exc
        if row_index < 1 or row_index > limits.max_rows:
            raise XlsxInspectionError("XLSX_ROW_INDEX_INVALID")
        if row_index <= prior_row_index:
            raise XlsxInspectionError("XLSX_ROW_ORDER_INVALID")
        prior_row_index = row_index

        cells: dict[int, str] = {}
        row_has_content = False
        for cell in row.findall(f"{{{_SPREADSHEET_NS}}}c"):
            reference = cell.get("r") or ""
            column, cell_row_index = _cell_position(reference)
            if cell_row_index != row_index:
                raise XlsxInspectionError("XLSX_CELL_ROW_MISMATCH")
            if column > limits.max_columns:
                raise XlsxInspectionError("XLSX_COLUMN_LIMIT_EXCEEDED")
            if column in cells:
                raise XlsxInspectionError("XLSX_CELL_DUPLICATE")
            value = _cell_text(cell, shared)
            cells[column] = value
            has_formula = cell.find(f"{{{_SPREADSHEET_NS}}}f") is not None
            if has_formula:
                formula_count += 1
            if has_formula or value.strip():
                row_has_content = True
                max_used_column = max(max_used_column, column)
        parsed_rows[row_index] = cells
        if row_has_content:
            nonempty_rows.add(row_index)

    return _ParsedWorksheet(
        rows=parsed_rows,
        nonempty_rows=frozenset(nonempty_rows),
        formula_count=formula_count,
        max_used_column=max_used_column,
    )


def _workbook_shape(
    workbook: bytes,
    *,
    policy: XlsxInspectionPolicy,
    package_kind: str,
) -> _WorkbookShape:
    limits = policy.limits
    try:
        with ZipFile(BytesIO(workbook)) as zf:
            names = _validate_archive(zf, limits)
            if not {item.casefold() for item in _XLSX_REQUIRED_PARTS}.issubset(names):
                raise XlsxInspectionError("XLSX_REQUIRED_PART_MISSING")
            content_types = _read_limited(zf, "[Content_Types].xml", limits)
            content_lower = content_types.lower()
            if b"macroenabled" in content_lower or b"vbaproject" in content_lower:
                raise XlsxInspectionError("XLSX_ACTIVE_CONTENT_FORBIDDEN")
            for info in zf.infolist():
                if info.filename.casefold().endswith(".rels"):
                    relationships = _read_limited(zf, info.filename, limits)
                    root = _xml_root(
                        relationships,
                        "XLSX_RELATIONSHIPS_INVALID",
                    )
                    for relation in root.findall(
                        f"{{{_RELATIONSHIP_NS}}}Relationship"
                    ):
                        target_mode = relation.get("TargetMode")
                        if (
                            isinstance(target_mode, str)
                            and target_mode.casefold() == "external"
                        ):
                            raise XlsxInspectionError(
                                "XLSX_EXTERNAL_RELATIONSHIP_FORBIDDEN"
                            )

            workbook_root = _xml_root(
                _read_limited(zf, "xl/workbook.xml", limits),
                "XLSX_WORKBOOK_INVALID",
            )
            relation_root = _xml_root(
                _read_limited(zf, "xl/_rels/workbook.xml.rels", limits),
                "XLSX_WORKBOOK_RELATIONSHIPS_INVALID",
            )
            targets: dict[str, str] = {}
            for relation in relation_root.findall(
                f"{{{_RELATIONSHIP_NS}}}Relationship"
            ):
                relation_id = relation.get("Id")
                if not relation_id:
                    continue
                if relation_id in targets:
                    raise XlsxInspectionError("XLSX_RELATIONSHIP_ID_DUPLICATE")
                targets[relation_id] = _relationship_target(
                    relation.get("Target") or ""
                )
            sheets = workbook_root.find(f"{{{_SPREADSHEET_NS}}}sheets")
            if sheets is None:
                raise XlsxInspectionError("XLSX_SHEETS_MISSING")
            sheet_nodes = sheets.findall(f"{{{_SPREADSHEET_NS}}}sheet")
            if not sheet_nodes:
                raise XlsxInspectionError("XLSX_SHEETS_MISSING")
            sheet_names = [node.get("name") or "" for node in sheet_nodes]
            normalized_sheet_names = [
                _normalized_header(name).casefold() for name in sheet_names
            ]
            if len(set(normalized_sheet_names)) != len(normalized_sheet_names):
                raise XlsxInspectionError("XLSX_SHEET_NAME_DUPLICATE")

            sheet_paths: list[str] = []
            for node in sheet_nodes:
                relation_id = node.get(f"{{{_OFFICE_RELATIONSHIP_NS}}}id")
                sheet_path = targets.get(relation_id)
                if sheet_path is None:
                    raise XlsxInspectionError("XLSX_SHEET_RELATIONSHIP_MISSING")
                lower = sheet_path.casefold()
                if not lower.startswith("xl/worksheets/") or not lower.endswith(".xml"):
                    raise XlsxInspectionError("XLSX_WORKSHEET_TOPOLOGY_INVALID")
                sheet_paths.append(sheet_path)
            normalized_targets = [path.casefold() for path in sheet_paths]
            if len(set(normalized_targets)) != len(normalized_targets):
                raise XlsxInspectionError("XLSX_SHEET_TARGET_DUPLICATE")
            archive_worksheet_paths = {
                info.filename.replace("\\", "/").casefold()
                for info in zf.infolist()
                if not info.is_dir()
                and info.filename.replace("\\", "/").casefold().startswith(
                    "xl/worksheets/"
                )
                and info.filename.casefold().endswith(".xml")
            }
            if archive_worksheet_paths != set(normalized_targets):
                raise XlsxInspectionError("XLSX_WORKSHEET_TOPOLOGY_INVALID")

            expectation_candidates = [
                schema
                for schema in policy.schemas
                if schema.package_kind == package_kind
            ]
            preferred_names = {
                schema.sheet_name for schema in expectation_candidates
            }
            selected_index = next(
                (
                    index
                    for index, node in enumerate(sheet_nodes)
                    if node.get("name") in preferred_names
                ),
                0,
            )
            selected = sheet_nodes[selected_index]
            sheet_name = selected.get("name") or ""
            _safe_text(sheet_name, "XLSX_SHEET_NAME_INVALID")
            selected_path = sheet_paths[selected_index]

            shared = _shared_strings(zf, limits)
            parsed_sheets = {
                path: _parse_worksheet(
                    zf,
                    sheet_path=path,
                    limits=limits,
                    shared=shared,
                )
                for path in sheet_paths
            }
            unmodeled_worksheet_count = sum(
                1
                for path, candidate in parsed_sheets.items()
                if path != selected_path
                and (candidate.nonempty_rows or candidate.formula_count)
            )
            parsed = parsed_sheets[selected_path]

            header_indexes = {
                schema.header_row_index
                for schema in expectation_candidates
                if schema.sheet_name == sheet_name
            }
            header_row_index = min(header_indexes) if header_indexes else 1
            header_cells = parsed.rows.get(header_row_index)
            if header_cells is None:
                raise XlsxInspectionError("XLSX_HEADER_ROW_MISSING")
            if not header_cells:
                raise XlsxInspectionError("XLSX_HEADERS_INVALID")
            normalized_headers = {
                column: _normalized_header(value)
                for column, value in header_cells.items()
            }
            column_count = max(normalized_headers)
            headers = tuple(
                normalized_headers.get(index, "")
                for index in range(1, column_count + 1)
            )
            if any(not header for header in headers):
                raise XlsxInspectionError("XLSX_HEADER_GAP_INVALID")
            header_hash = normalized_header_sha256(headers)
            tokens = tuple(
                _normalized_sensitive_token(token)
                for token in policy.prohibited_header_tokens
            )
            prohibited = sum(
                1
                for header in headers
                if any(
                    token in _normalized_sensitive_token(header)
                    for token in tokens
                )
            )
            data_rows = sum(
                1
                for row_index in parsed.nonempty_rows
                if row_index > header_row_index
            )
            return _WorkbookShape(
                sheet_name=sheet_name,
                sheet_count=len(sheet_nodes),
                header_row_index=header_row_index,
                header_sha256=header_hash,
                column_count=column_count,
                max_used_column=parsed.max_used_column,
                unmodeled_worksheet_count=unmodeled_worksheet_count,
                data_row_count=data_rows,
                formula_count=parsed.formula_count,
                prohibited_header_count=prohibited,
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
