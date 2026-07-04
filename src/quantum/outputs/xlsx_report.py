from __future__ import annotations

from collections.abc import Mapping
from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape as xml_escape
from zipfile import ZIP_DEFLATED, ZipFile

from .local_bundle import (
    EXPECTED_XLSX_SHEETS,
    OutputBundleError,
    validate_local_output_bundle,
)
from .xlsx_ooxml import _worksheet_xml, _zip_write
from .xlsx_rows import (
    _calculation_metric_rows,
    _flatten_rows,
    _journal_rows,
    _metric_headers,
    _recommendation_rows,
    _rows_matching,
    _summary_rows,
)


def render_xlsx_report(bundle: Mapping[str, Any]) -> bytes:
    validate_local_output_bundle(bundle)
    sheets: list[tuple[str, list[list[str]], bool]] = [
        (
            "Управленческое резюме",
            [["Показатель", "Значение"], *_summary_rows(bundle)],
            False,
        ),
        (
            "Рекомендации",
            [
                [
                    "ID",
                    "Приоритет цели",
                    "Срочность",
                    "Категория",
                    "Действие",
                    "Причина",
                    "Код действия",
                    "Уверенность",
                    "Текущий статус",
                    "Текущий эффект",
                    "Валюта",
                    "Статус min",
                    "Прогноз min",
                    "Валюта min",
                    "Статус max",
                    "Прогноз max",
                    "Валюта max",
                    "Ссылки на доказательства",
                    "Ограничения",
                ],
                *_recommendation_rows(bundle),
            ],
            True,
        ),
        (
            "Финансы по товарам",
            [_metric_headers(), *_calculation_metric_rows(bundle)],
            True,
        ),
        (
            "Продажи",
            [
                _metric_headers(),
                *_rows_matching(
                    bundle,
                    ("sale", "sold", "order", "bought", "payout", "income"),
                ),
            ],
            True,
        ),
        (
            "Реклама",
            [_metric_headers(), *_rows_matching(bundle, ("advert", "promotion"))],
            True,
        ),
        (
            "Возвраты",
            [_metric_headers(), *_rows_matching(bundle, ("return", "reverse"))],
            True,
        ),
        (
            "Остатки и хранение",
            [_metric_headers(), *_rows_matching(bundle, ("stock", "storage"))],
            True,
        ),
        (
            "Расходы",
            [
                _metric_headers(),
                *_rows_matching(
                    bundle,
                    (
                        "cost",
                        "expense",
                        "commission",
                        "logistic",
                        "storage",
                        "advert",
                        "fine",
                        "tax",
                    ),
                ),
            ],
            True,
        ),
        (
            "Качество данных",
            [["Поле", "Значение"], *_flatten_rows(bundle["data_quality"])],
            True,
        ),
        (
            "Параметры расчёта",
            [["Параметр", "Значение"], *_flatten_rows(bundle["parameters"])],
            True,
        ),
        (
            "Источники данных",
            [["Поле", "Значение"], *_flatten_rows(bundle["provenance"])],
            True,
        ),
        (
            "Журнал изменений",
            [["Время UTC", "Событие", "Идентификатор / SHA-256"], *_journal_rows(bundle)],
            True,
        ),
    ]
    if tuple(name for name, _, _ in sheets) != EXPECTED_XLSX_SHEETS:
        raise OutputBundleError("OUTPUT_XLSX_SHEET_CONTRACT_INVALID")
    workbook_sheets = "".join(
        f'<sheet name="{xml_escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, (name, _, _) in enumerate(sheets, start=1)
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets>{workbook_sheets}</sheets></workbook>'
    ).encode("utf-8")
    workbook_rels = [
        f'<Relationship Id="rId{index}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        f'Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, len(sheets) + 1)
    ]
    workbook_rels.append(
        f'<Relationship Id="rId{len(sheets) + 1}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
    )
    relationships = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(workbook_rels)
        + '</Relationships>'
    ).encode("utf-8")
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        '</Relationships>'
    ).encode("utf-8")
    content_types = [
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>',
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>',
    ]
    content_types.extend(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, len(sheets) + 1)
    )
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        + "".join(content_types)
        + '</Types>'
    ).encode("utf-8")
    styles = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        '</styleSheet>'
    ).encode("utf-8")
    generated = bundle["generated_at"]
    core = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<dc:title>Quantum Analytics</dc:title><dc:creator>Quantum Analytics</dc:creator>'
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{generated}</dcterms:created>'
        '</cp:coreProperties>'
    ).encode("utf-8")
    app = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        '<Application>Quantum Analytics</Application></Properties>'
    ).encode("utf-8")
    stream = BytesIO()
    with ZipFile(stream, "w", compression=ZIP_DEFLATED) as archive:
        _zip_write(archive, "[Content_Types].xml", content_types_xml)
        _zip_write(archive, "_rels/.rels", root_rels)
        _zip_write(archive, "xl/workbook.xml", workbook)
        _zip_write(archive, "xl/_rels/workbook.xml.rels", relationships)
        _zip_write(archive, "xl/styles.xml", styles)
        _zip_write(archive, "docProps/core.xml", core)
        _zip_write(archive, "docProps/app.xml", app)
        for index, (_, rows, filtered) in enumerate(sheets, start=1):
            _zip_write(
                archive,
                f"xl/worksheets/sheet{index}.xml",
                _worksheet_xml(rows, freeze_header=True, auto_filter=filtered),
            )
    return stream.getvalue()
