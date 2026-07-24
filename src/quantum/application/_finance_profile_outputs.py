from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any
from xml.etree import ElementTree
from zipfile import ZIP_DEFLATED, ZipFile

from quantum.adapters.wildberries.detailed_financial import (
    WbDetailedFinancialError,
    _ALIASES as _WB_DETAILED_ALIASES,
    normalize_detailed_financial_rows,
)
from quantum.adapters.wildberries.source_bridge import _sheet_rows
from quantum.finance import FinanceError, calculate, canonical_hash
from quantum.ingestion import XlsxInspectionLimits
from quantum.ingestion._xlsx_archive import _extract_workbook

from quantum.application._finance_profile_model import *
from quantum.application._finance_profile_groups import *
from quantum.application._finance_profile_engine import *

def _xml_escape(value: object) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _xlsx_inline_cell(reference: str, value: object) -> str:
    return (
        f'<c r="{reference}" t="inlineStr"><is><t xml:space="preserve">'
        f'{_xml_escape(value)}</t></is></c>'
    )


def _xlsx_number_cell(reference: str, value: object) -> str:
    text = str(value).replace(",", ".").strip()
    try:
        parsed = Decimal(text)
    except InvalidOperation:
        return _xlsx_inline_cell(reference, value)
    if not parsed.is_finite():
        return _xlsx_inline_cell(reference, value)
    return f'<c r="{reference}" t="n"><v>{format(parsed, "f")}</v></c>'


def _xlsx_sheet(
    rows: Sequence[Sequence[tuple[str, object, bool]]],
    *,
    autofilter_end: str = "D",
) -> str:
    xml_rows: list[str] = []
    for row_index, cells in enumerate(rows, start=1):
        values: list[str] = []
        for column, value, numeric in cells:
            reference = f"{column}{row_index}"
            values.append(
                _xlsx_number_cell(reference, value)
                if numeric
                else _xlsx_inline_cell(reference, value)
            )
        xml_rows.append(f'<row r="{row_index}">{"".join(values)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetViews><sheetView workbookViewId="0"/></sheetViews>'
        '<sheetFormatPr defaultRowHeight="18"/>'
        '<sheetData>' + "".join(xml_rows) + '</sheetData>'
        f'<autoFilter ref="A1:{autofilter_end}1"/>'
        '</worksheet>'
    )


def _recommendation_rows(
    recommendations: Sequence[Mapping[str, Any]],
    recommendation_errors: Sequence[str],
) -> list[list[tuple[str, object, bool]]]:
    rows: list[list[tuple[str, object, bool]]] = [[
        ("A", "Группа", False),
        ("B", "Категория", False),
        ("C", "Критичность", False),
        ("D", "Действие", False),
        ("E", "Текущий эффект, ₽", False),
        ("F", "Прогноз min, ₽", False),
        ("G", "Прогноз max, ₽", False),
        ("H", "Уверенность", False),
        ("I", "Ограничения", False),
    ]]
    for record in recommendations:
        item = record.get("recommendation")
        if not isinstance(item, Mapping):
            continue
        current = item.get("current_effect")
        forecast = item.get("forecast_effect")
        confidence = item.get("confidence")
        rows.append([
            ("A", record.get("group_name", ""), False),
            ("B", item.get("category", ""), False),
            ("C", item.get("severity", ""), False),
            ("D", item.get("action_code", ""), False),
            (
                "E",
                current.get("amount", "")
                if isinstance(current, Mapping)
                else "",
                True,
            ),
            (
                "F",
                forecast.get("amount_min", "")
                if isinstance(forecast, Mapping)
                else "",
                True,
            ),
            (
                "G",
                forecast.get("amount_max", "")
                if isinstance(forecast, Mapping)
                else "",
                True,
            ),
            (
                "H",
                confidence.get("state", "")
                if isinstance(confidence, Mapping)
                else "",
                False,
            ),
            (
                "I",
                "; ".join(
                    str(value) for value in item.get("limitations", [])
                ),
                False,
            ),
        ])
    for error in recommendation_errors:
        rows.append([
            ("A", "", False),
            ("B", "DATA_QUALITY", False),
            ("C", "BLOCKED", False),
            ("D", "RECOMMENDATION_BUILD_BLOCKED", False),
            ("E", "", False),
            ("F", "", False),
            ("G", "", False),
            ("H", "LOW", False),
            ("I", error, False),
        ])
    if len(rows) == 1:
        rows.append([
            ("A", "", False),
            ("B", "", False),
            ("C", "", False),
            ("D", "Нет подтверждённых рекомендаций", False),
            ("E", "", False),
            ("F", "", False),
            ("G", "", False),
            ("H", "", False),
            ("I", "Рекомендации не создаются без доказуемого основания", False),
        ])
    return rows


def write_run_result_xlsx(
    path: Path,
    result: FinanceRunResult,
    *,
    recommendations: Sequence[Mapping[str, Any]] = (),
    recommendation_errors: Sequence[str] = (),
) -> None:
    summary_labels = {
        "net_sold_units": "Продано единиц",
        "net_marketplace_income_amount": "Чистый доход маркетплейса, ₽",
        "product_cost_amount": "Себестоимость, ₽",
        "other_expense_amount": "Прочие расходы, ₽",
        "tax_amount": "Налог, ₽",
        "net_profit_amount": "Чистая прибыль, ₽",
        "profit_per_sold_unit": "Прибыль на единицу, ₽",
    }
    summary_rows: list[list[tuple[str, object, bool]]] = [
        [("A", "Показатель", False), ("B", "Значение", False), ("C", "Статус", False)]
    ]
    for metric_id, label in summary_labels.items():
        summary_rows.append(
            [
                ("A", label, False),
                ("B", result.totals.get(metric_id, ""), True),
                ("C", result.status, False),
            ]
        )
    group_rows: list[list[tuple[str, object, bool]]] = [
        [
            ("A", "Группа", False),
            ("B", "Статус", False),
            ("C", "Чистая прибыль, ₽", False),
            ("D", "Причины блокировки", False),
        ]
    ]
    for item in result.group_results:
        profit: object = ""
        if item.calculation:
            results = item.calculation.get("results")
            if isinstance(results, Mapping):
                metric = results.get("net_profit_amount")
                if isinstance(metric, Mapping) and metric.get("value") is not None:
                    profit = metric.get("value")
        group_rows.append(
            [
                ("A", item.group_name, False),
                ("B", item.state, False),
                ("C", profit, True),
                ("D", "; ".join(item.reason_codes), False),
            ]
        )
    recommendation_rows = _recommendation_rows(
        recommendations,
        recommendation_errors,
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets>'
        '<sheet name="Итоги" sheetId="1" r:id="rId1"/>'
        '<sheet name="Группы" sheetId="2" r:id="rId2"/>'
        '<sheet name="Рекомендации" sheetId="3" r:id="rId3"/>'
        '</sheets></workbook>'
    )
    relationships = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet3.xml"/>'
        '</Relationships>'
    )
    root_relationships = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/worksheets/sheet3.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '</Types>'
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_relationships)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relationships)
        archive.writestr("xl/worksheets/sheet1.xml", _xlsx_sheet(summary_rows))
        archive.writestr("xl/worksheets/sheet2.xml", _xlsx_sheet(group_rows))
        archive.writestr(
            "xl/worksheets/sheet3.xml",
            _xlsx_sheet(recommendation_rows, autofilter_end="I"),
        )


def write_run_dashboard(
    path: Path,
    result: FinanceRunResult,
    *,
    recommendations: Sequence[Mapping[str, Any]] = (),
    recommendation_errors: Sequence[str] = (),
) -> None:
    from html import escape

    metrics = (
        ("Чистая прибыль", result.totals.get("net_profit_amount", "—"), "₽"),
        ("Прибыль на единицу", result.totals.get("profit_per_sold_unit", "—"), "₽"),
        ("Чистый доход WB", result.totals.get("net_marketplace_income_amount", "—"), "₽"),
        ("Продано", result.totals.get("net_sold_units", "—"), "шт."),
    )
    cards = "".join(
        '<article class="card"><span>{}</span><strong>{}</strong><small>{}</small></article>'.format(
            escape(label), escape(str(value)), escape(unit)
        )
        for label, value, unit in metrics
    )
    group_rows = []
    for item in result.group_results:
        profit = "—"
        if item.calculation:
            calculation_results = item.calculation.get("results")
            if isinstance(calculation_results, Mapping):
                metric = calculation_results.get("net_profit_amount")
                if isinstance(metric, Mapping) and metric.get("value") is not None:
                    profit = str(metric.get("value"))
        group_rows.append(
            '<tr><td>{}</td><td><span class="status {}">{}</span></td><td>{}</td><td>{}</td></tr>'.format(
                escape(item.group_name),
                "ok" if item.state == "VALID" else "blocked",
                escape(item.state),
                escape(profit),
                escape("; ".join(item.reason_codes)),
            )
        )
    missing = "".join(f"<li>{escape(value)}</li>" for value in result.missing_inputs)
    recommendation_cards: list[str] = []
    for record in recommendations:
        item = record.get("recommendation")
        if not isinstance(item, Mapping):
            continue
        current = item.get("current_effect")
        forecast = item.get("forecast_effect")
        confidence = item.get("confidence")
        current_amount = (
            current.get("amount") if isinstance(current, Mapping) else None
        )
        forecast_min = (
            forecast.get("amount_min")
            if isinstance(forecast, Mapping)
            else None
        )
        forecast_max = (
            forecast.get("amount_max")
            if isinstance(forecast, Mapping)
            else None
        )
        confidence_state = (
            confidence.get("state")
            if isinstance(confidence, Mapping)
            else "UNVERIFIED"
        )
        recommendation_cards.append(
            '<article class="recommendation">'
            f'<h3>{escape(str(record.get("group_name") or "Общие данные"))}</h3>'
            f'<p><strong>{escape(str(item.get("action_code") or ""))}</strong></p>'
            f'<p>Текущий эффект: {escape(str(current_amount or "—"))} ₽</p>'
            f'<p>Прогноз: {escape(str(forecast_min or "—"))}…{escape(str(forecast_max or "—"))} ₽</p>'
            f'<p>Уверенность: {escape(str(confidence_state))}</p>'
            f'<p>Ограничения: {escape("; ".join(str(v) for v in item.get("limitations", [])) or "нет")}</p>'
            '</article>'
        )
    for error in recommendation_errors:
        recommendation_cards.append(
            '<article class="recommendation blocked">'
            '<h3>Рекомендация заблокирована</h3>'
            f'<p>{escape(error)}</p></article>'
        )
    if not recommendation_cards:
        recommendation_cards.append(
            '<article class="recommendation"><h3>Нет подтверждённых рекомендаций</h3>'
            '<p>Quantum не создаёт совет без доказуемого финансового основания.</p></article>'
        )
    html = f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Quantum — финансовая аналитика WB</title>
<style>
:root{{--navy:#102a43;--blue:#1769aa;--cyan:#00a6c8;--green:#14866d;--orange:#e97824;--red:#c0392b;--bg:#f3f7fa;--line:#d9e2ec;--text:#172b4d}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:15px/1.45 Segoe UI,Arial,sans-serif}}
header{{background:linear-gradient(120deg,var(--navy),var(--blue));color:white;padding:34px 6vw}}header h1{{margin:0 0 6px;font-size:30px}}header p{{margin:0;color:#d9eaf7}}
main{{max-width:1220px;margin:0 auto;padding:24px}}.grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}}
.card{{background:white;border:1px solid var(--line);border-top:5px solid var(--cyan);border-radius:10px;padding:18px;box-shadow:0 5px 15px #102a4312}}
.card span,.card small{{display:block;color:#627d98}}.card strong{{display:block;font-size:28px;margin:8px 0;color:var(--navy)}}
section{{background:white;border:1px solid var(--line);border-radius:10px;margin-top:18px;padding:20px;overflow:auto}}table{{border-collapse:collapse;width:100%}}th,td{{text-align:left;padding:11px;border-bottom:1px solid var(--line)}}th{{background:#eaf3f9;color:var(--navy)}}
.status{{display:inline-block;padding:4px 9px;border-radius:999px;color:white;font-size:12px;font-weight:700}}.ok{{background:var(--green)}}.blocked{{background:var(--red)}}
.recommendations{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}}.recommendation{{border:1px solid var(--line);border-left:5px solid var(--blue);padding:14px;border-radius:8px}}.recommendation h3{{margin:0 0 8px}}
.notice{{border-left:5px solid var(--orange)}}footer{{padding:20px;text-align:center;color:#627d98}}@media(max-width:850px){{.grid{{grid-template-columns:1fr 1fr}}}}
</style></head><body>
<header><h1>Quantum · аналитика Wildberries</h1><p>Локальный режим · WB_ONLY · запись на маркетплейс отключена</p></header>
<main><div class="grid">{cards}</div>
<section><h2>Результаты по товарным группам</h2><table><thead><tr><th>Группа</th><th>Статус</th><th>Прибыль, ₽</th><th>Контроль</th></tr></thead><tbody>{''.join(group_rows)}</tbody></table></section>
<section><h2>Рекомендации</h2><div class="recommendations">{''.join(recommendation_cards)}</div></section>
<section class="notice"><h2>Контроль полноты данных</h2><p>Статус: <strong>{escape(result.status)}</strong></p><ul>{missing or '<li>Обязательные данные заполнены.</li>'}</ul></section>
</main><footer>Quantum HOME_LOCAL · данные не отправляются во внешние сервисы</footer></body></html>'''
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")

__all__ = [name for name in globals() if not name.startswith("__")]
