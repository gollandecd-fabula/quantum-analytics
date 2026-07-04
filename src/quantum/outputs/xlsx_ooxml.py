from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any
from xml.sax.saxutils import escape as xml_escape, quoteattr
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from .local_bundle import _XML_INVALID


STYLE_IDS: Mapping[str, int] = {
    "normal": 0,
    "title": 1,
    "subtitle": 2,
    "section": 3,
    "header": 4,
    "body": 5,
    "body_wrap": 6,
    "label": 7,
    "currency": 8,
    "percent": 9,
    "integer": 10,
    "decimal": 11,
    "code": 12,
    "technical": 13,
    "link": 14,
    "status_good": 15,
    "status_warn": 16,
    "status_bad": 17,
    "status_neutral": 18,
    "severity_critical": 19,
    "severity_high": 20,
    "severity_medium": 21,
    "severity_low": 22,
    "kpi_label_bad": 23,
    "kpi_currency_bad": 24,
    "kpi_percent_bad": 25,
    "kpi_integer_bad": 26,
    "kpi_label_good": 27,
    "kpi_currency_good": 28,
    "kpi_percent_good": 29,
    "kpi_integer_good": 30,
    "kpi_label_neutral": 31,
    "kpi_currency_neutral": 32,
    "kpi_percent_neutral": 33,
    "kpi_integer_neutral": 34,
    "currency_expense": 35,
    "currency_positive": 36,
    "center": 37,
    "center_wrap": 38,
    "boolean": 39,
}


@dataclass(frozen=True, slots=True)
class Cell:
    value: Any = ""
    style: str = "body"
    kind: str = "auto"
    hyperlink: str | None = None


@dataclass(frozen=True, slots=True)
class ColumnSpec:
    width: float
    hidden: bool = False


@dataclass(frozen=True, slots=True)
class ConditionalRule:
    dxf_id: int
    priority: int
    operator: str
    formula: str


@dataclass(frozen=True, slots=True)
class ConditionalFormat:
    sqref: str
    rules: tuple[ConditionalRule, ...]


@dataclass(frozen=True, slots=True)
class WorksheetSpec:
    name: str
    rows: Sequence[Sequence[Any]]
    columns: Sequence[ColumnSpec]
    row_heights: Mapping[int, float] = field(default_factory=dict)
    merges: tuple[str, ...] = ()
    freeze_row: int = 0
    freeze_col: int = 0
    auto_filter: str | None = None
    conditional_formats: tuple[ConditionalFormat, ...] = ()
    tab_color: str = "64748B"
    show_grid_lines: bool = True
    zoom_scale: int = 90
    landscape: bool = True
    drawing_rel_id: str | None = None
    generated_at: str = ""


def _clean_xml(value: object) -> str:
    return _XML_INVALID.sub("", str(value))


def _cell_reference(column: int, row: int) -> str:
    letters = ""
    current = column
    while current:
        current, remainder = divmod(current - 1, 26)
        letters = chr(65 + remainder) + letters
    return f"{letters}{row}"


def _style_id(style: str) -> int:
    try:
        return STYLE_IDS[style]
    except KeyError as exc:
        raise ValueError("OUTPUT_XLSX_STYLE_UNKNOWN:" + style) from exc


def _number_text(value: Any) -> str:
    if isinstance(value, bool):
        raise ValueError("OUTPUT_XLSX_NUMBER_INVALID")
    if isinstance(value, Decimal):
        number = value
    else:
        try:
            number = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError("OUTPUT_XLSX_NUMBER_INVALID") from exc
    if not number.is_finite():
        raise ValueError("OUTPUT_XLSX_NUMBER_INVALID")
    return format(number, "f")


def _cell_xml(cell: Any, column: int, row: int) -> tuple[str, tuple[str, str, str] | None]:
    if not isinstance(cell, Cell):
        cell = Cell(cell)
    reference = _cell_reference(column, row)
    style_id = _style_id(cell.style)
    value = cell.value
    hyperlink = (reference, cell.hyperlink, _clean_xml(value)) if cell.hyperlink else None
    if value is None or value == "":
        return f'<c r="{reference}" s="{style_id}"/>', hyperlink
    kind = cell.kind
    if kind == "auto":
        if isinstance(value, bool):
            kind = "boolean"
        elif isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
            kind = "number"
        else:
            kind = "string"
    if kind == "number":
        return (
            f'<c r="{reference}" s="{style_id}"><v>{_number_text(value)}</v></c>',
            hyperlink,
        )
    if kind == "boolean":
        flag = "1" if bool(value) else "0"
        return f'<c r="{reference}" s="{style_id}" t="b"><v>{flag}</v></c>', hyperlink
    text = xml_escape(_clean_xml(value))
    return (
        f'<c r="{reference}" s="{style_id}" t="inlineStr">'
        f'<is><t xml:space="preserve">{text}</t></is></c>',
        hyperlink,
    )


def _pane_xml(freeze_row: int, freeze_col: int) -> tuple[str, str]:
    if not freeze_row and not freeze_col:
        return "", '<selection activeCell="A1" sqref="A1"/>'
    top_left = _cell_reference(freeze_col + 1, freeze_row + 1)
    attributes: list[str] = []
    if freeze_col:
        attributes.append(f'xSplit="{freeze_col}"')
    if freeze_row:
        attributes.append(f'ySplit="{freeze_row}"')
    if freeze_row and freeze_col:
        pane = "bottomRight"
    elif freeze_row:
        pane = "bottomLeft"
    else:
        pane = "topRight"
    attributes.extend(
        [
            f'topLeftCell="{top_left}"',
            f'activePane="{pane}"',
            'state="frozen"',
        ]
    )
    return (
        "<pane " + " ".join(attributes) + "/>",
        f'<selection pane="{pane}" activeCell="{top_left}" sqref="{top_left}"/>',
    )


def _conditional_format_xml(item: ConditionalFormat) -> str:
    rules = "".join(
        f'<cfRule type="cellIs" dxfId="{rule.dxf_id}" priority="{rule.priority}" '
        f'operator="{xml_escape(rule.operator)}"><formula>{xml_escape(rule.formula)}</formula></cfRule>'
        for rule in item.rules
    )
    return f'<conditionalFormatting sqref="{xml_escape(item.sqref)}">{rules}</conditionalFormatting>'


def _worksheet_xml(spec: WorksheetSpec) -> bytes:
    rows = [list(row) for row in spec.rows]
    max_columns = max(
        len(spec.columns),
        max((len(row) for row in rows), default=1),
    )
    max_rows = max(len(rows), 1)
    columns = list(spec.columns) + [ColumnSpec(12.0)] * (max_columns - len(spec.columns))
    cols = "".join(
        f'<col min="{index}" max="{index}" width="{column.width:.2f}" customWidth="1"'
        + (' hidden="1"' if column.hidden else "")
        + "/>"
        for index, column in enumerate(columns, start=1)
    )
    xml_rows: list[str] = []
    hyperlinks: list[tuple[str, str, str]] = []
    for row_number, row in enumerate(rows, start=1):
        cells: list[str] = []
        for column_number, value in enumerate(row, start=1):
            cell_xml, hyperlink = _cell_xml(value, column_number, row_number)
            cells.append(cell_xml)
            if hyperlink is not None:
                hyperlinks.append(hyperlink)
        height = spec.row_heights.get(row_number)
        row_attrs = f' r="{row_number}"'
        if height is not None:
            row_attrs += f' ht="{height:.2f}" customHeight="1"'
        xml_rows.append(f'<row{row_attrs}>{"".join(cells)}</row>')
    pane, selection = _pane_xml(spec.freeze_row, spec.freeze_col)
    sheet_view = (
        '<sheetViews><sheetView workbookViewId="0" '
        f'showGridLines="{1 if spec.show_grid_lines else 0}" '
        f'zoomScale="{spec.zoom_scale}" zoomScaleNormal="100">'
        f'{pane}{selection}</sheetView></sheetViews>'
    )
    dimension = f"A1:{_cell_reference(max_columns, max_rows)}"
    sheet_pr = (
        f'<sheetPr><tabColor rgb="FF{spec.tab_color}"/>'
        '<outlinePr summaryBelow="1" summaryRight="1"/>'
        '<pageSetUpPr fitToPage="1"/></sheetPr>'
    )
    auto_filter = f'<autoFilter ref="{xml_escape(spec.auto_filter)}"/>' if spec.auto_filter else ""
    merge_xml = (
        f'<mergeCells count="{len(spec.merges)}">'
        + "".join(f'<mergeCell ref="{xml_escape(item)}"/>' for item in spec.merges)
        + '</mergeCells>'
        if spec.merges
        else ""
    )
    conditional_xml = "".join(_conditional_format_xml(item) for item in spec.conditional_formats)
    hyperlink_xml = (
        '<hyperlinks>'
        + "".join(
            f'<hyperlink ref="{reference}" location={quoteattr(location)} display={quoteattr(display)}/>'
            for reference, location, display in hyperlinks
        )
        + '</hyperlinks>'
        if hyperlinks
        else ""
    )
    print_options = '<printOptions horizontalCentered="0" verticalCentered="0"/>'
    margins = '<pageMargins left="0.25" right="0.25" top="0.5" bottom="0.5" header="0.2" footer="0.2"/>'
    orientation = "landscape" if spec.landscape else "portrait"
    page_setup = f'<pageSetup paperSize="9" orientation="{orientation}" fitToWidth="1" fitToHeight="0"/>'
    generated = xml_escape(_clean_xml(spec.generated_at))
    header_footer = (
        '<headerFooter><oddHeader>&amp;C&amp;"Calibri,Bold"&amp;12 Quantum Analytics</oddHeader>'
        f'<oddFooter>&amp;L{generated}&amp;RСтраница &amp;P из &amp;N</oddFooter></headerFooter>'
    )
    drawing = f'<drawing r:id="{spec.drawing_rel_id}"/>' if spec.drawing_rel_id else ""
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'{sheet_pr}<dimension ref="{dimension}"/>{sheet_view}'
        f'<sheetFormatPr defaultRowHeight="15"/><cols>{cols}</cols>'
        f'<sheetData>{"".join(xml_rows)}</sheetData>{auto_filter}{merge_xml}'
        f'{conditional_xml}{hyperlink_xml}{print_options}{margins}{page_setup}'
        f'{header_footer}{drawing}</worksheet>'
    )
    return xml.encode("utf-8")


def _xf(
    font: int,
    fill: int,
    border: int,
    *,
    num_fmt: int = 0,
    horizontal: str = "left",
    vertical: str = "center",
    wrap: bool = False,
) -> str:
    alignment = (
        f'<alignment horizontal="{horizontal}" vertical="{vertical}"'
        + (' wrapText="1"' if wrap else "")
        + '/>'
    )
    return (
        f'<xf numFmtId="{num_fmt}" fontId="{font}" fillId="{fill}" borderId="{border}" xfId="0" '
        'applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"'
        + (' applyNumberFormat="1"' if num_fmt else "")
        + f'>{alignment}</xf>'
    )


def styles_xml() -> bytes:
    fonts = [
        '<font><sz val="11"/><color rgb="FF17202A"/><name val="Calibri"/><family val="2"/></font>',
        '<font><b/><sz val="18"/><color rgb="FFFFFFFF"/><name val="Calibri"/><family val="2"/></font>',
        '<font><sz val="10"/><color rgb="FF475467"/><name val="Calibri"/><family val="2"/></font>',
        '<font><b/><sz val="12"/><color rgb="FFFFFFFF"/><name val="Calibri"/><family val="2"/></font>',
        '<font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Calibri"/><family val="2"/></font>',
        '<font><b/><sz val="10"/><color rgb="FF344054"/><name val="Calibri"/><family val="2"/></font>',
        '<font><sz val="9"/><color rgb="FF475467"/><name val="Consolas"/><family val="3"/></font>',
        '<font><u/><sz val="10"/><color rgb="FF1D4ED8"/><name val="Calibri"/><family val="2"/></font>',
        '<font><b/><sz val="10"/><color rgb="FF067647"/><name val="Calibri"/><family val="2"/></font>',
        '<font><b/><sz val="10"/><color rgb="FFB54708"/><name val="Calibri"/><family val="2"/></font>',
        '<font><b/><sz val="10"/><color rgb="FFB42318"/><name val="Calibri"/><family val="2"/></font>',
        '<font><b/><sz val="10"/><color rgb="FF475467"/><name val="Calibri"/><family val="2"/></font>',
        '<font><b/><sz val="18"/><color rgb="FFB42318"/><name val="Calibri"/><family val="2"/></font>',
        '<font><b/><sz val="18"/><color rgb="FF067647"/><name val="Calibri"/><family val="2"/></font>',
        '<font><b/><sz val="18"/><color rgb="FF175CD3"/><name val="Calibri"/><family val="2"/></font>',
        '<font><sz val="9"/><color rgb="FF667085"/><name val="Calibri"/><family val="2"/></font>',
        '<font><b/><sz val="10"/><color rgb="FF175CD3"/><name val="Calibri"/><family val="2"/></font>',
    ]
    fills = [
        '<fill><patternFill patternType="none"/></fill>',
        '<fill><patternFill patternType="gray125"/></fill>',
        '<fill><patternFill patternType="solid"><fgColor rgb="FF172554"/><bgColor indexed="64"/></patternFill></fill>',
        '<fill><patternFill patternType="solid"><fgColor rgb="FFE2E8F0"/><bgColor indexed="64"/></patternFill></fill>',
        '<fill><patternFill patternType="solid"><fgColor rgb="FF0F766E"/><bgColor indexed="64"/></patternFill></fill>',
        '<fill><patternFill patternType="solid"><fgColor rgb="FF334155"/><bgColor indexed="64"/></patternFill></fill>',
        '<fill><patternFill patternType="solid"><fgColor rgb="FFFEE2E2"/><bgColor indexed="64"/></patternFill></fill>',
        '<fill><patternFill patternType="solid"><fgColor rgb="FFDCFCE7"/><bgColor indexed="64"/></patternFill></fill>',
        '<fill><patternFill patternType="solid"><fgColor rgb="FFFFEDD5"/><bgColor indexed="64"/></patternFill></fill>',
        '<fill><patternFill patternType="solid"><fgColor rgb="FFDBEAFE"/><bgColor indexed="64"/></patternFill></fill>',
        '<fill><patternFill patternType="solid"><fgColor rgb="FFF1F5F9"/><bgColor indexed="64"/></patternFill></fill>',
    ]
    borders = [
        '<border><left/><right/><top/><bottom/><diagonal/></border>',
        '<border><left style="thin"><color rgb="FFCBD5E1"/></left><right style="thin"><color rgb="FFCBD5E1"/></right><top style="thin"><color rgb="FFCBD5E1"/></top><bottom style="thin"><color rgb="FFCBD5E1"/></bottom><diagonal/></border>',
    ]
    xfs = [
        _xf(0, 0, 0),
        _xf(1, 2, 0, horizontal="left", wrap=True),
        _xf(2, 3, 0, horizontal="left", wrap=True),
        _xf(3, 4, 0, horizontal="left", wrap=True),
        _xf(4, 5, 1, horizontal="center", wrap=True),
        _xf(0, 0, 1),
        _xf(0, 0, 1, vertical="top", wrap=True),
        _xf(5, 10, 1),
        _xf(0, 0, 1, num_fmt=164, horizontal="right"),
        _xf(0, 0, 1, num_fmt=165, horizontal="right"),
        _xf(0, 0, 1, num_fmt=166, horizontal="right"),
        _xf(0, 0, 1, num_fmt=167, horizontal="right"),
        _xf(6, 10, 1, vertical="top", wrap=True),
        _xf(15, 10, 1, vertical="top", wrap=True),
        _xf(7, 0, 1, horizontal="center", wrap=True),
        _xf(8, 7, 1, horizontal="center", wrap=True),
        _xf(9, 8, 1, horizontal="center", wrap=True),
        _xf(10, 6, 1, horizontal="center", wrap=True),
        _xf(5, 9, 1, horizontal="center", wrap=True),
        _xf(10, 6, 1, horizontal="center", wrap=True),
        _xf(9, 8, 1, horizontal="center", wrap=True),
        _xf(16, 9, 1, horizontal="center", wrap=True),
        _xf(5, 10, 1, horizontal="center", wrap=True),
        _xf(11, 6, 1, horizontal="center", wrap=True),
        _xf(12, 6, 1, num_fmt=164, horizontal="center", wrap=True),
        _xf(12, 6, 1, num_fmt=165, horizontal="center", wrap=True),
        _xf(12, 6, 1, num_fmt=166, horizontal="center", wrap=True),
        _xf(11, 7, 1, horizontal="center", wrap=True),
        _xf(13, 7, 1, num_fmt=164, horizontal="center", wrap=True),
        _xf(13, 7, 1, num_fmt=165, horizontal="center", wrap=True),
        _xf(13, 7, 1, num_fmt=166, horizontal="center", wrap=True),
        _xf(11, 9, 1, horizontal="center", wrap=True),
        _xf(14, 9, 1, num_fmt=164, horizontal="center", wrap=True),
        _xf(14, 9, 1, num_fmt=165, horizontal="center", wrap=True),
        _xf(14, 9, 1, num_fmt=166, horizontal="center", wrap=True),
        _xf(9, 8, 1, num_fmt=164, horizontal="right"),
        _xf(8, 7, 1, num_fmt=164, horizontal="right"),
        _xf(0, 0, 1, horizontal="center"),
        _xf(0, 0, 1, horizontal="center", wrap=True),
        _xf(0, 0, 1, horizontal="center"),
    ]
    dxfs = (
        '<dxfs count="4">'
        '<dxf><font><color rgb="FFB42318"/></font><fill><patternFill patternType="solid"><fgColor rgb="FFFEE2E2"/><bgColor indexed="64"/></patternFill></fill></dxf>'
        '<dxf><font><color rgb="FF067647"/></font><fill><patternFill patternType="solid"><fgColor rgb="FFDCFCE7"/><bgColor indexed="64"/></patternFill></fill></dxf>'
        '<dxf><font><color rgb="FFB54708"/></font><fill><patternFill patternType="solid"><fgColor rgb="FFFFEDD5"/><bgColor indexed="64"/></patternFill></fill></dxf>'
        '<dxf><font><color rgb="FF175CD3"/></font><fill><patternFill patternType="solid"><fgColor rgb="FFDBEAFE"/><bgColor indexed="64"/></patternFill></fill></dxf>'
        '</dxfs>'
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<numFmts count="4">'
        '<numFmt numFmtId="164" formatCode="#,##0.00 &quot;₽&quot;;[Red]-#,##0.00 &quot;₽&quot;"/>'
        '<numFmt numFmtId="165" formatCode="0.00%;[Red]-0.00%"/>'
        '<numFmt numFmtId="166" formatCode="#,##0"/>'
        '<numFmt numFmtId="167" formatCode="#,##0.00"/>'
        '</numFmts>'
        f'<fonts count="{len(fonts)}">{"".join(fonts)}</fonts>'
        f'<fills count="{len(fills)}">{"".join(fills)}</fills>'
        f'<borders count="{len(borders)}">{"".join(borders)}</borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        f'<cellXfs count="{len(xfs)}">{"".join(xfs)}</cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        f'{dxfs}'
        '<tableStyles count="0" defaultTableStyle="TableStyleMedium2" defaultPivotStyle="PivotStyleLight16"/>'
        '</styleSheet>'
    )
    return xml.encode("utf-8")


def _zip_write(archive: ZipFile, name: str, payload: bytes) -> None:
    info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    archive.writestr(info, payload)
