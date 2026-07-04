from __future__ import annotations

from collections.abc import Sequence
from io import BytesIO
from xml.sax.saxutils import escape as xml_escape
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from .local_bundle import _XML_INVALID


def _clean_xml(value: object) -> str:
    return _XML_INVALID.sub("", str(value))


def _cell_reference(column: int, row: int) -> str:
    letters = ""
    current = column
    while current:
        current, remainder = divmod(current - 1, 26)
        letters = chr(65 + remainder) + letters
    return f"{letters}{row}"


def _worksheet_xml(
    rows: Sequence[Sequence[object]],
    *,
    freeze_header: bool,
    auto_filter: bool,
) -> bytes:
    materialized = [[_clean_xml(cell) for cell in row] for row in rows]
    max_columns = max((len(row) for row in materialized), default=1)
    widths: list[float] = []
    for column in range(max_columns):
        longest = max(
            (len(row[column]) if column < len(row) else 0 for row in materialized),
            default=0,
        )
        widths.append(float(min(max(longest + 2, 10), 60)))
    cols = "".join(
        f'<col min="{index}" max="{index}" width="{width:.1f}" customWidth="1"/>'
        for index, width in enumerate(widths, start=1)
    )
    xml_rows: list[str] = []
    for row_number, row in enumerate(materialized, start=1):
        cells: list[str] = []
        for column_number, value in enumerate(row, start=1):
            reference = _cell_reference(column_number, row_number)
            style = "1" if row_number == 1 else "0"
            escaped = xml_escape(value)
            cells.append(
                f'<c r="{reference}" s="{style}" t="inlineStr">'
                f'<is><t xml:space="preserve">{escaped}</t></is></c>'
            )
        xml_rows.append(f'<row r="{row_number}">{"".join(cells)}</row>')
    pane = (
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        if freeze_header and materialized
        else ""
    )
    selection = (
        '<selection pane="bottomLeft" activeCell="A2" sqref="A2"/>'
        if pane
        else ""
    )
    sheet_views = (
        f'<sheetViews><sheetView workbookViewId="0">{pane}{selection}'
        '</sheetView></sheetViews>'
    )
    dimension = f"A1:{_cell_reference(max_columns, max(len(materialized), 1))}"
    filter_xml = (
        f'<autoFilter ref="{dimension}"/>'
        if auto_filter and len(materialized) > 1
        else ""
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<dimension ref="{dimension}"/>{sheet_views}'
        f'<cols>{cols}</cols><sheetData>{"".join(xml_rows)}</sheetData>{filter_xml}'
        '</worksheet>'
    )
    return xml.encode("utf-8")


def _zip_write(archive: ZipFile, name: str, payload: bytes) -> None:
    info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    archive.writestr(info, payload)
