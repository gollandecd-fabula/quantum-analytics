from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape as xml_escape
from zipfile import ZIP_DEFLATED, ZipFile

from .local_bundle import (
    EXPECTED_XLSX_SHEETS,
    OutputBundleError,
    validate_local_output_bundle,
)
from .xlsx_chart import (
    ChartSpec,
    chart_xml,
    drawing_relationships_xml,
    drawing_xml,
    worksheet_drawing_relationships_xml,
)
from .xlsx_ooxml import (
    Cell,
    ColumnSpec,
    ConditionalFormat,
    ConditionalRule,
    WorksheetSpec,
    _cell_reference,
    _worksheet_xml,
    _zip_write,
    styles_xml,
)
from .xlsx_rows import (
    _calculation_metric_rows,
    _flatten_rows,
    _journal_rows,
    _metric_headers,
    _recommendation_headers,
    _recommendation_rows,
    _result_decimal,
    _rows_matching,
    _state_style,
    _summary_control_rows,
    _summary_financial_rows,
    _summary_technical_rows,
)


_SHEET_META = {
    "Рекомендации": ("РЕКОМЕНДАЦИИ QUANTUM", "B54708"),
    "Финансы по товарам": ("ФИНАНСОВЫЕ РЕЗУЛЬТАТЫ", "0F766E"),
    "Продажи": ("ПРОДАЖИ", "175CD3"),
    "Реклама": ("РЕКЛАМА", "7F56D9"),
    "Возвраты": ("ВОЗВРАТЫ", "E04F16"),
    "Остатки и хранение": ("ОСТАТКИ И ХРАНЕНИЕ", "067647"),
    "Расходы": ("РАСХОДЫ", "B42318"),
    "Качество данных": ("КАЧЕСТВО ДАННЫХ", "CA8504"),
    "Параметры расчёта": ("ПАРАМЕТРЫ РАСЧЁТА", "475467"),
    "Источники данных": ("ИСТОЧНИКИ ДАННЫХ", "0E7490"),
    "Журнал изменений": ("ЖУРНАЛ ИЗМЕНЕНИЙ", "344054"),
}


def _row(width: int, style: str = "normal") -> list[Cell]:
    return [Cell("", style) for _ in range(width)]


def _set_block(
    rows: list[list[Cell]],
    *,
    start_row: int,
    start_col: int,
    end_row: int,
    end_col: int,
    style: str,
    value: object = "",
    kind: str = "auto",
) -> None:
    for row_number in range(start_row, end_row + 1):
        for column_number in range(start_col, end_col + 1):
            rows[row_number - 1][column_number - 1] = Cell("", style)
    rows[start_row - 1][start_col - 1] = Cell(value, style, kind)


def _kpi_styles(value: Decimal | None, value_type: str) -> tuple[str, str]:
    if value is None:
        return "kpi_label_neutral", f"kpi_{value_type}_neutral"
    if value < 0:
        return "kpi_label_bad", f"kpi_{value_type}_bad"
    return "kpi_label_good", f"kpi_{value_type}_good"


def _summary_sheet(bundle: Mapping[str, Any]) -> tuple[WorksheetSpec, ChartSpec | None]:
    width = 17
    rows = [_row(width) for _ in range(36)]
    merges: list[str] = [
        "A1:H2",
        "A3:H3",
        "A5:B5",
        "A6:B7",
        "C5:D5",
        "C6:D7",
        "E5:F5",
        "E6:F7",
        "G5:H5",
        "G6:H7",
        "A9:D9",
        "F9:H9",
        "G10:H10",
    ]
    _set_block(
        rows,
        start_row=1,
        start_col=1,
        end_row=2,
        end_col=8,
        style="title",
        value="QUANTUM ANALYTICS — УПРАВЛЕНЧЕСКИЙ ОТЧЁТ",
    )
    metadata = (
        f"Набор: {bundle['dataset_id']}  •  Источник: {bundle.get('source_type') or 'NOT_AVAILABLE'}"
        f"  •  Сформирован: {bundle['generated_at']}"
    )
    _set_block(
        rows,
        start_row=3,
        start_col=1,
        end_row=3,
        end_col=8,
        style="subtitle",
        value=metadata,
    )

    kpis = (
        (1, 2, "Чистая прибыль", _result_decimal(bundle, "net_profit_amount"), "currency"),
        (3, 4, "Прибыль на единицу", _result_decimal(bundle, "profit_per_sold_unit"), "currency"),
        (5, 6, "Рентабельность", _result_decimal(bundle, "profitability_of_costs"), "percent"),
        (7, 8, "Продано единиц", _result_decimal(bundle, "net_sold_units"), "integer"),
    )
    for start_col, end_col, label, value, value_type in kpis:
        label_style, value_style = _kpi_styles(value, value_type)
        _set_block(
            rows,
            start_row=5,
            start_col=start_col,
            end_row=5,
            end_col=end_col,
            style=label_style,
            value=label,
        )
        _set_block(
            rows,
            start_row=6,
            start_col=start_col,
            end_row=7,
            end_col=end_col,
            style=value_style,
            value="" if value is None else value,
            kind="number" if value is not None else "string",
        )

    _set_block(rows, start_row=9, start_col=1, end_row=9, end_col=4, style="section", value="Финансовая структура")
    _set_block(rows, start_row=9, start_col=6, end_row=9, end_col=8, style="section", value="Контроль и статус")
    for column, value in enumerate(("Показатель", "Сумма, ₽", "Состояние", "Источник"), start=1):
        rows[9][column - 1] = Cell(value, "header")
    rows[9][5] = Cell("Показатель", "header")
    _set_block(rows, start_row=10, start_col=7, end_row=10, end_col=8, style="header", value="Значение")

    financial = _summary_financial_rows(bundle)
    chart_categories: list[str] = []
    chart_values: list[Decimal] = []
    finance_start = 11
    for offset, (label, metric_id, value, source) in enumerate(financial):
        row_number = finance_start + offset
        rows[row_number - 1][0] = Cell(label, "label")
        value_style = "currency_expense" if metric_id != "net_profit_amount" and any(
            keyword in metric_id
            for keyword in ("cost", "expense", "commission", "logistic", "storage", "advert", "tax")
        ) else "currency"
        rows[row_number - 1][1] = Cell(value, value_style, "number")
        rows[row_number - 1][2] = Cell("VALID", "status_good")
        rows[row_number - 1][3] = Cell(source, "technical")
        chart_categories.append(
            {
                "gross_sales_amount": "Продажи",
                "payout_amount": "Выплата",
                "marketplace_commission_amount": "Комиссия",
                "forward_logistics_amount": "Прям. логистика",
                "reverse_logistics_amount": "Обр. логистика",
                "storage_amount": "Хранение",
                "advertising_amount": "Реклама",
                "product_cost_amount": "Себестоимость",
                "other_expense_amount": "Прочие",
                "tax_amount": "Налог",
                "net_profit_amount": "Прибыль",
            }.get(metric_id, label)
        )
        chart_values.append(value)

    control_start = 11
    for offset, (label, value, style) in enumerate(_summary_control_rows(bundle)):
        row_number = control_start + offset
        rows[row_number - 1][5] = Cell(label, "label")
        merges.append(f"G{row_number}:H{row_number}")
        kind = "boolean" if style == "boolean" else "number" if style in {"integer", "decimal"} else "string"
        _set_block(
            rows,
            start_row=row_number,
            start_col=7,
            end_row=row_number,
            end_col=8,
            style=style,
            value=value,
            kind=kind,
        )

    financial_end = finance_start + max(len(financial), 1) - 1
    navigation_start = max(23, financial_end + 2)
    merges.append(f"A{navigation_start}:H{navigation_start}")
    _set_block(
        rows,
        start_row=navigation_start,
        start_col=1,
        end_row=navigation_start,
        end_col=8,
        style="section",
        value="Навигация по отчёту",
    )
    navigation = [
        ("Рекомендации", "Рекомендации"),
        ("Финансы", "Финансы по товарам"),
        ("Продажи", "Продажи"),
        ("Реклама", "Реклама"),
        ("Возвраты", "Возвраты"),
        ("Остатки", "Остатки и хранение"),
        ("Расходы", "Расходы"),
        ("Качество", "Качество данных"),
        ("Параметры", "Параметры расчёта"),
        ("Источники", "Источники данных"),
        ("Журнал", "Журнал изменений"),
    ]
    navigation_columns = (1, 2, 3, 4, 6, 7, 8)
    for index, (label, sheet_name) in enumerate(navigation):
        row_number = navigation_start + 1 + index // len(navigation_columns)
        column_number = navigation_columns[index % len(navigation_columns)]
        rows[row_number - 1][column_number - 1] = Cell(
            label,
            "link",
            hyperlink=f"'{sheet_name}'!A1",
        )

    technical_start = navigation_start + 4
    merges.append(f"A{technical_start}:H{technical_start}")
    _set_block(
        rows,
        start_row=technical_start,
        start_col=1,
        end_row=technical_start,
        end_col=8,
        style="section",
        value="Технические сведения и контрольные суммы",
    )
    for offset, (label, value) in enumerate(_summary_technical_rows(bundle), start=1):
        row_number = technical_start + offset
        merges.extend([f"A{row_number}:B{row_number}", f"C{row_number}:H{row_number}"])
        _set_block(rows, start_row=row_number, start_col=1, end_row=row_number, end_col=2, style="label", value=label)
        _set_block(rows, start_row=row_number, start_col=3, end_row=row_number, end_col=8, style="technical", value=value)

    last_row = technical_start + len(_summary_technical_rows(bundle))
    rows = rows[:last_row]
    row_heights = {
        1: 28,
        2: 28,
        3: 20,
        5: 20,
        6: 26,
        7: 26,
        9: 22,
        10: 24,
        navigation_start: 22,
        navigation_start + 1: 24,
        navigation_start + 2: 24,
        technical_start: 22,
    }
    for row_number in range(finance_start, financial_end + 1):
        row_heights[row_number] = 21
    for row_number in range(technical_start + 1, last_row + 1):
        row_heights[row_number] = 30
    conditional = ()
    if financial:
        conditional = (
            ConditionalFormat(
                f"B{finance_start}:B{financial_end}",
                (
                    ConditionalRule(0, 1, "lessThan", "0"),
                ),
            ),
        )
    chart = None
    if chart_values:
        chart = ChartSpec(
            title="Финансовая структура, ₽",
            categories=tuple(chart_categories),
            values=tuple(chart_values),
            from_col=9,
            from_row=3,
            to_col=17,
            to_row=max(21, financial_end + 1),
        )
    spec = WorksheetSpec(
        name="Управленческое резюме",
        rows=rows,
        columns=(
            ColumnSpec(25), ColumnSpec(17), ColumnSpec(15), ColumnSpec(15),
            ColumnSpec(3), ColumnSpec(23), ColumnSpec(18), ColumnSpec(18),
            ColumnSpec(3),
            *(ColumnSpec(12) for _ in range(8)),
        ),
        row_heights=row_heights,
        merges=tuple(merges),
        freeze_row=3,
        conditional_formats=conditional,
        tab_color="172554",
        show_grid_lines=False,
        zoom_scale=90,
        landscape=True,
        drawing_rel_id="rId1" if chart is not None else None,
        generated_at=str(bundle["generated_at"]),
    )
    return spec, chart


def _table_sheet(
    bundle: Mapping[str, Any],
    *,
    name: str,
    headers: Sequence[Cell],
    data: Sequence[Sequence[Cell]],
    columns: Sequence[ColumnSpec],
    freeze_col: int = 0,
    body_height: float = 30,
    value_column: str | None = None,
    portrait: bool = False,
) -> WorksheetSpec:
    title, tab_color = _SHEET_META[name]
    width = len(headers)
    rows = [_row(width) for _ in range(5)]
    rows[0][0] = Cell(title, "title")
    for column in range(width):
        rows[1][column] = Cell("", "title")
    rows[2][0] = Cell("← Управленческое резюме", "link", hyperlink="'Управленческое резюме'!A1")
    metadata = (
        f"Набор: {bundle['dataset_id']}  •  Сформирован: {bundle['generated_at']}"
        f"  •  Bundle: {str(bundle['bundle_hash'])[:16]}…"
    )
    rows[2][1] = Cell(metadata, "subtitle")
    rows[4] = list(headers)
    rows.extend([list(row) for row in data])
    last_col = _cell_reference(width, 1).rstrip("1")
    last_row = max(len(rows), 5)
    merges = (f"A1:{last_col}2", f"B3:{last_col}3") if width > 1 else ("A1:A2",)
    row_heights = {1: 26, 2: 26, 3: 20, 5: 32}
    for row_number in range(6, last_row + 1):
        row_heights[row_number] = body_height
    conditional: tuple[ConditionalFormat, ...] = ()
    if value_column and last_row >= 6:
        conditional = (
            ConditionalFormat(
                f"{value_column}6:{value_column}{last_row}",
                (
                    ConditionalRule(0, 1, "lessThan", "0"),
                ),
            ),
        )
    return WorksheetSpec(
        name=name,
        rows=rows,
        columns=columns,
        row_heights=row_heights,
        merges=merges,
        freeze_row=5,
        freeze_col=freeze_col,
        auto_filter=f"A5:{last_col}{last_row}",
        conditional_formats=conditional,
        tab_color=tab_color,
        show_grid_lines=True,
        zoom_scale=85 if width > 11 else 95,
        landscape=not portrait,
        generated_at=str(bundle["generated_at"]),
    )


def _build_sheets(bundle: Mapping[str, Any]) -> tuple[list[WorksheetSpec], ChartSpec | None]:
    summary, chart = _summary_sheet(bundle)
    metric_columns = (
        ColumnSpec(21), ColumnSpec(32), ColumnSpec(16), ColumnSpec(17),
        ColumnSpec(14), ColumnSpec(10), ColumnSpec(30), ColumnSpec(24),
        ColumnSpec(30), ColumnSpec(30), ColumnSpec(42),
    )
    recommendations = _table_sheet(
        bundle,
        name="Рекомендации",
        headers=_recommendation_headers(),
        data=_recommendation_rows(bundle),
        columns=(
            ColumnSpec(13), ColumnSpec(21), ColumnSpec(18), ColumnSpec(32), ColumnSpec(44),
            ColumnSpec(17), ColumnSpec(17), ColumnSpec(17), ColumnSpec(14), ColumnSpec(40),
            ColumnSpec(36), ColumnSpec(38), ColumnSpec(28), ColumnSpec(16), ColumnSpec(11),
            ColumnSpec(16), ColumnSpec(11), ColumnSpec(16), ColumnSpec(11),
        ),
        freeze_col=4,
        body_height=54,
        value_column="F",
    )
    finance = _table_sheet(
        bundle,
        name="Финансы по товарам",
        headers=_metric_headers(),
        data=_calculation_metric_rows(bundle),
        columns=metric_columns,
        freeze_col=2,
        body_height=34,
        value_column="D",
    )
    sales = _table_sheet(
        bundle,
        name="Продажи",
        headers=_metric_headers(),
        data=_rows_matching(bundle, ("sale", "sold", "order", "bought", "payout", "income")),
        columns=metric_columns,
        freeze_col=2,
        body_height=34,
        value_column="D",
    )
    advertising = _table_sheet(
        bundle,
        name="Реклама",
        headers=_metric_headers(),
        data=_rows_matching(bundle, ("advert", "promotion")),
        columns=metric_columns,
        freeze_col=2,
        body_height=34,
        value_column="D",
    )
    returns = _table_sheet(
        bundle,
        name="Возвраты",
        headers=_metric_headers(),
        data=_rows_matching(bundle, ("return", "reverse")),
        columns=metric_columns,
        freeze_col=2,
        body_height=34,
        value_column="D",
    )
    stock = _table_sheet(
        bundle,
        name="Остатки и хранение",
        headers=_metric_headers(),
        data=_rows_matching(bundle, ("stock", "storage")),
        columns=metric_columns,
        freeze_col=2,
        body_height=34,
        value_column="D",
    )
    expenses = _table_sheet(
        bundle,
        name="Расходы",
        headers=_metric_headers(),
        data=_rows_matching(bundle, ("cost", "expense", "commission", "logistic", "storage", "advert", "fine", "tax")),
        columns=metric_columns,
        freeze_col=2,
        body_height=34,
        value_column="D",
    )
    two_column = (ColumnSpec(42), ColumnSpec(78))
    quality = _table_sheet(
        bundle,
        name="Качество данных",
        headers=(Cell("Поле", "header"), Cell("Значение", "header")),
        data=_flatten_rows(bundle["data_quality"]),
        columns=two_column,
        freeze_col=1,
        body_height=30,
        portrait=True,
    )
    parameters = _table_sheet(
        bundle,
        name="Параметры расчёта",
        headers=(Cell("Параметр", "header"), Cell("Значение", "header")),
        data=_flatten_rows(bundle["parameters"]),
        columns=two_column,
        freeze_col=1,
        body_height=30,
        portrait=True,
    )
    sources = _table_sheet(
        bundle,
        name="Источники данных",
        headers=(Cell("Поле", "header"), Cell("Значение", "header")),
        data=_flatten_rows(bundle["provenance"]),
        columns=two_column,
        freeze_col=1,
        body_height=32,
        portrait=True,
    )
    journal = _table_sheet(
        bundle,
        name="Журнал изменений",
        headers=(Cell("Время UTC", "header"), Cell("Событие", "header"), Cell("Идентификатор / SHA-256", "header")),
        data=_journal_rows(bundle),
        columns=(ColumnSpec(24), ColumnSpec(30), ColumnSpec(78)),
        freeze_col=1,
        body_height=30,
        portrait=True,
    )
    sheets = [
        summary,
        recommendations,
        finance,
        sales,
        advertising,
        returns,
        stock,
        expenses,
        quality,
        parameters,
        sources,
        journal,
    ]
    if tuple(sheet.name for sheet in sheets) != EXPECTED_XLSX_SHEETS:
        raise OutputBundleError("OUTPUT_XLSX_SHEET_CONTRACT_INVALID")
    return sheets, chart


def _workbook_xml(sheets: Sequence[WorksheetSpec]) -> bytes:
    workbook_sheets = "".join(
        f'<sheet name="{xml_escape(sheet.name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, sheet in enumerate(sheets, start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<fileVersion appName="xl" lastEdited="7" lowestEdited="7" rupBuild="9303"/>'
        '<workbookPr date1904="0"/>'
        '<bookViews><workbookView xWindow="0" yWindow="0" windowWidth="28800" windowHeight="16200" activeTab="0"/></bookViews>'
        f'<sheets>{workbook_sheets}</sheets>'
        '<calcPr calcId="191029" calcMode="manual" fullCalcOnLoad="0" forceFullCalc="0"/>'
        '</workbook>'
    ).encode("utf-8")


def _workbook_relationships(sheet_count: int) -> bytes:
    relationships = [
        f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, sheet_count + 1)
    ]
    relationships.append(
        f'<Relationship Id="rId{sheet_count + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(relationships)
        + '</Relationships>'
    ).encode("utf-8")


def _content_types(sheet_count: int, has_chart: bool) -> bytes:
    parts = [
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>',
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>',
    ]
    parts.extend(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, sheet_count + 1)
    )
    if has_chart:
        parts.extend(
            [
                '<Override PartName="/xl/drawings/drawing1.xml" ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/>',
                '<Override PartName="/xl/charts/chart1.xml" ContentType="application/vnd.openxmlformats-officedocument.drawingml.chart+xml"/>',
            ]
        )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        + "".join(parts)
        + '</Types>'
    ).encode("utf-8")


def _root_relationships() -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        '</Relationships>'
    ).encode("utf-8")


def _core_properties(bundle: Mapping[str, Any]) -> bytes:
    generated = xml_escape(str(bundle["generated_at"]))
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<dc:title>Quantum Analytics — Управленческий отчёт</dc:title>'
        '<dc:subject>Локальная аналитика, рекомендации и контрольные суммы</dc:subject>'
        '<dc:creator>Quantum Analytics</dc:creator><cp:lastModifiedBy>Quantum Analytics</cp:lastModifiedBy>'
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{generated}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{generated}</dcterms:modified>'
        '</cp:coreProperties>'
    ).encode("utf-8")


def _app_properties(sheets: Sequence[WorksheetSpec]) -> bytes:
    titles = "".join(f'<vt:lpstr>{xml_escape(sheet.name)}</vt:lpstr>' for sheet in sheets)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        '<Application>Quantum Analytics</Application><DocSecurity>0</DocSecurity><ScaleCrop>false</ScaleCrop>'
        '<HeadingPairs><vt:vector size="2" baseType="variant"><vt:variant><vt:lpstr>Листы</vt:lpstr></vt:variant>'
        f'<vt:variant><vt:i4>{len(sheets)}</vt:i4></vt:variant></vt:vector></HeadingPairs>'
        f'<TitlesOfParts><vt:vector size="{len(sheets)}" baseType="lpstr">{titles}</vt:vector></TitlesOfParts>'
        '<Company>Quantum Analytics</Company><LinksUpToDate>false</LinksUpToDate><SharedDoc>false</SharedDoc>'
        '<HyperlinksChanged>false</HyperlinksChanged><AppVersion>1.0</AppVersion></Properties>'
    ).encode("utf-8")


def render_xlsx_report(bundle: Mapping[str, Any]) -> bytes:
    validate_local_output_bundle(bundle)
    sheets, chart = _build_sheets(bundle)
    stream = BytesIO()
    with ZipFile(stream, "w", compression=ZIP_DEFLATED) as archive:
        _zip_write(archive, "[Content_Types].xml", _content_types(len(sheets), chart is not None))
        _zip_write(archive, "_rels/.rels", _root_relationships())
        _zip_write(archive, "xl/workbook.xml", _workbook_xml(sheets))
        _zip_write(archive, "xl/_rels/workbook.xml.rels", _workbook_relationships(len(sheets)))
        _zip_write(archive, "xl/styles.xml", styles_xml())
        _zip_write(archive, "docProps/core.xml", _core_properties(bundle))
        _zip_write(archive, "docProps/app.xml", _app_properties(sheets))
        for index, sheet in enumerate(sheets, start=1):
            _zip_write(archive, f"xl/worksheets/sheet{index}.xml", _worksheet_xml(sheet))
        if chart is not None:
            _zip_write(archive, "xl/worksheets/_rels/sheet1.xml.rels", worksheet_drawing_relationships_xml())
            _zip_write(archive, "xl/drawings/drawing1.xml", drawing_xml(chart))
            _zip_write(archive, "xl/drawings/_rels/drawing1.xml.rels", drawing_relationships_xml())
            _zip_write(archive, "xl/charts/chart1.xml", chart_xml(chart))
    return stream.getvalue()
