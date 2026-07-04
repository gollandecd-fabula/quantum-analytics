from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from hashlib import sha256
from html import escape as html_escape
from io import BytesIO
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any
from xml.sax.saxutils import escape as xml_escape
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


LOCAL_OUTPUT_BUNDLE_SCHEMA_VERSION = "quantum-local-output-bundle-v1"
LOCAL_OUTPUT_MANIFEST_SCHEMA_VERSION = "quantum-local-output-manifest-v1"
MAX_LOCAL_OUTPUT_JSON_BYTES = 10_000_000
_FORBIDDEN_KEYS = frozenset({"raw_rows", "raw_payload", "source_rows"})
_HASH = re.compile(r"^[0-9a-f]{64}$")
_SAFE_TOKEN = re.compile(r"[^A-Za-z0-9._-]+")
_XML_INVALID = re.compile(
    "[\x00-\x08\x0B\x0C\x0E-\x1F\uD800-\uDFFF\uFFFE\uFFFF]"
)

_ACTION_LABELS = {
    "COMPLETE_REQUIRED_INPUTS": "Заполнить обязательные данные",
    "INVESTIGATE_LOW_BUYOUT": "Разобрать низкий выкуп",
    "REVIEW_STOCKOUT": "Проверить дефицит остатка",
    "REVIEW_STOCK_WITHOUT_BUYOUT": "Проверить остаток без выкупа",
    "REVIEW_HIGH_STOCK_TO_BUYOUT_RATIO": "Проверить избыточный остаток",
    "INVESTIGATE_HIGH_RETURN_RATE": "Разобрать высокий уровень возвратов",
    "REVIEW_COMMISSION_AND_PRICE_STRUCTURE": "Проверить комиссию и цену",
    "REVIEW_FORWARD_LOGISTICS_COST": "Проверить прямую логистику",
    "REVIEW_REVERSE_LOGISTICS_COST": "Проверить обратную логистику",
    "REVIEW_STORAGE_COST": "Проверить стоимость хранения",
    "RECONCILE_SETTLEMENT_GAP": "Сверить расхождение выплаты",
}
_SEVERITY_LABELS = {
    "CRITICAL": "Критический",
    "HIGH": "Высокий",
    "MEDIUM": "Средний",
    "LOW": "Низкий",
}
_CATEGORY_LABELS = {
    "DATA_QUALITY": "Качество данных",
    "SALES": "Продажи",
    "INVENTORY": "Остатки",
    "RETURNS": "Возвраты",
    "COST": "Расходы",
    "LOGISTICS": "Логистика",
    "RECONCILIATION": "Сверка",
}


class OutputBundleError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _canonical_json_text(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise OutputBundleError("OUTPUT_JSON_INVALID") from exc


def _canonical_json_bytes(value: Any) -> bytes:
    payload = _canonical_json_text(value).encode("utf-8")
    if len(payload) > MAX_LOCAL_OUTPUT_JSON_BYTES:
        raise OutputBundleError("OUTPUT_JSON_SIZE_LIMIT_EXCEEDED")
    return payload


def _clone(value: Any) -> Any:
    return json.loads(_canonical_json_text(value))


def _timestamp(value: datetime | str) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise OutputBundleError("OUTPUT_TIMESTAMP_INVALID")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if not isinstance(value, str) or not value:
        raise OutputBundleError("OUTPUT_TIMESTAMP_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OutputBundleError("OUTPUT_TIMESTAMP_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OutputBundleError("OUTPUT_TIMESTAMP_INVALID")
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _text(value: object, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OutputBundleError(code)
    return value.strip()


def _walk_privacy(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise OutputBundleError("OUTPUT_NON_STRING_KEY")
            if key in _FORBIDDEN_KEYS:
                raise OutputBundleError("OUTPUT_RAW_DATA_FORBIDDEN:" + path + "." + key)
            if key == "raw_rows_in_report" and item is not False:
                raise OutputBundleError("OUTPUT_RAW_ROWS_FLAG_INVALID")
            _walk_privacy(item, path + "." + key)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _walk_privacy(item, f"{path}[{index}]")


def _bundle_hash(bundle: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in bundle.items() if key != "bundle_hash"}
    return sha256(_canonical_json_bytes(payload)).hexdigest()


def _unique_strings(values: Sequence[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if isinstance(value, str) and value and value not in seen:
            result.append(value)
            seen.add(value)
    return result


def build_local_output_bundle(
    report: Mapping[str, Any],
    *,
    generated_at: datetime | str,
) -> dict[str, Any]:
    if not isinstance(report, Mapping):
        raise OutputBundleError("OUTPUT_REPORT_INVALID")
    dataset_id = _text(report.get("dataset_id"), "OUTPUT_DATASET_ID_INVALID")
    run_status = _text(report.get("status"), "OUTPUT_RUN_STATUS_INVALID")
    source_bridge_raw = report.get("source_bridge")
    if not isinstance(source_bridge_raw, Mapping):
        raise OutputBundleError("OUTPUT_SOURCE_BRIDGE_REQUIRED")
    source_bridge = _clone(source_bridge_raw)
    recommendations_raw = source_bridge.pop("recommendations", None)
    if not isinstance(recommendations_raw, Mapping):
        raise OutputBundleError("OUTPUT_RECOMMENDATIONS_REQUIRED")
    recommendations = _clone(recommendations_raw)
    source_type = source_bridge.get("source_type")
    if source_type is not None and not isinstance(source_type, str):
        raise OutputBundleError("OUTPUT_SOURCE_TYPE_INVALID")
    source_sha256 = source_bridge.get("source_sha256") or report.get("file_sha256")
    source_sha256 = _text(source_sha256, "OUTPUT_SOURCE_SHA256_INVALID").lower()
    if _HASH.fullmatch(source_sha256) is None:
        raise OutputBundleError("OUTPUT_SOURCE_SHA256_INVALID")

    report_limitations = report.get("limitations", [])
    bridge_limitations = source_bridge.get("limitations", [])
    if not isinstance(report_limitations, list) or not isinstance(
        bridge_limitations, list
    ):
        raise OutputBundleError("OUTPUT_LIMITATIONS_INVALID")
    limitations = _unique_strings([*report_limitations, *bridge_limitations])
    generated = _timestamp(generated_at)
    bundle_id = "local-output:" + dataset_id
    bundle: dict[str, Any] = {
        "schema_version": LOCAL_OUTPUT_BUNDLE_SCHEMA_VERSION,
        "bundle_id": bundle_id,
        "generated_at": generated,
        "dataset_id": dataset_id,
        "run_status": run_status,
        "source_type": source_type,
        "source_sha256": source_sha256,
        "analysis": source_bridge,
        "recommendations": recommendations,
        "limitations": limitations,
        "bundle_hash": "",
    }
    _walk_privacy(bundle)
    bundle["bundle_hash"] = _bundle_hash(bundle)
    validate_local_output_bundle(bundle)
    return bundle


def validate_local_output_bundle(bundle: object) -> None:
    expected = {
        "schema_version",
        "bundle_id",
        "generated_at",
        "dataset_id",
        "run_status",
        "source_type",
        "source_sha256",
        "analysis",
        "recommendations",
        "limitations",
        "bundle_hash",
    }
    if not isinstance(bundle, Mapping) or set(bundle) != expected:
        raise OutputBundleError("OUTPUT_BUNDLE_FIELDS_INVALID")
    if bundle.get("schema_version") != LOCAL_OUTPUT_BUNDLE_SCHEMA_VERSION:
        raise OutputBundleError("OUTPUT_BUNDLE_SCHEMA_UNSUPPORTED")
    _text(bundle.get("bundle_id"), "OUTPUT_BUNDLE_ID_INVALID")
    _text(bundle.get("dataset_id"), "OUTPUT_DATASET_ID_INVALID")
    _text(bundle.get("run_status"), "OUTPUT_RUN_STATUS_INVALID")
    _timestamp(bundle.get("generated_at"))
    source_type = bundle.get("source_type")
    if source_type is not None and (
        not isinstance(source_type, str) or not source_type
    ):
        raise OutputBundleError("OUTPUT_SOURCE_TYPE_INVALID")
    source_sha256 = bundle.get("source_sha256")
    if not isinstance(source_sha256, str) or _HASH.fullmatch(source_sha256) is None:
        raise OutputBundleError("OUTPUT_SOURCE_SHA256_INVALID")
    if not isinstance(bundle.get("analysis"), Mapping):
        raise OutputBundleError("OUTPUT_ANALYSIS_INVALID")
    recommendations = bundle.get("recommendations")
    if not isinstance(recommendations, Mapping):
        raise OutputBundleError("OUTPUT_RECOMMENDATIONS_INVALID")
    items = recommendations.get("recommendations")
    count = recommendations.get("recommendation_count")
    if not isinstance(items, list) or not isinstance(count, int) or isinstance(count, bool):
        raise OutputBundleError("OUTPUT_RECOMMENDATIONS_INVALID")
    if count != len(items):
        raise OutputBundleError("OUTPUT_RECOMMENDATION_COUNT_MISMATCH")
    limitations = bundle.get("limitations")
    if not isinstance(limitations, list) or any(
        not isinstance(item, str) or not item for item in limitations
    ):
        raise OutputBundleError("OUTPUT_LIMITATIONS_INVALID")
    _walk_privacy(bundle)
    supplied_hash = bundle.get("bundle_hash")
    if not isinstance(supplied_hash, str) or supplied_hash != _bundle_hash(bundle):
        raise OutputBundleError("OUTPUT_BUNDLE_HASH_MISMATCH")
    _canonical_json_bytes(bundle)


def _metric_rows(bundle: Mapping[str, Any]) -> list[list[str]]:
    analysis = bundle["analysis"]
    metrics = analysis.get("observed_metrics", {})
    if not isinstance(metrics, Mapping):
        return []
    result: list[list[str]] = []
    for metric_id in sorted(metrics):
        metric = metrics[metric_id]
        if not isinstance(metric, Mapping):
            continue
        source_ids = metric.get("source_ids")
        if isinstance(source_ids, list):
            source_text = " | ".join(str(item) for item in source_ids)
        else:
            source_text = str(metric.get("authority") or "")
        result.append(
            [
                str(metric_id),
                str(metric.get("state") or ""),
                "" if metric.get("value") is None else str(metric.get("value")),
                str(metric.get("unit") or ""),
                str(metric.get("currency") or ""),
                str(metric.get("reason_code") or ""),
                source_text,
            ]
        )
    return result


def _effect_text(effect: object) -> tuple[str, str, str]:
    if not isinstance(effect, Mapping):
        return "", "", ""
    state = str(effect.get("state") or "")
    if "amount" in effect:
        amount = "" if effect.get("amount") is None else str(effect.get("amount"))
        return state, amount, str(effect.get("currency") or "")
    minimum = "" if effect.get("amount_min") is None else str(effect.get("amount_min"))
    maximum = "" if effect.get("amount_max") is None else str(effect.get("amount_max"))
    value = minimum if minimum == maximum else f"{minimum} .. {maximum}".strip(" .")
    return state, value, str(effect.get("currency") or "")


def _recommendation_rows(bundle: Mapping[str, Any]) -> list[list[str]]:
    recommendation_bundle = bundle["recommendations"]
    items = recommendation_bundle.get("recommendations", [])
    if not isinstance(items, list):
        return []
    result: list[list[str]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        current_state, current_value, current_currency = _effect_text(
            item.get("current_effect")
        )
        forecast_state, forecast_value, forecast_currency = _effect_text(
            item.get("forecast_effect")
        )
        confidence = item.get("confidence")
        confidence_state = (
            str(confidence.get("state") or "")
            if isinstance(confidence, Mapping)
            else ""
        )
        limitations = item.get("limitations")
        limitations_text = (
            " | ".join(str(value) for value in limitations)
            if isinstance(limitations, list)
            else ""
        )
        action_code = str(item.get("action_code") or "")
        category = str(item.get("category") or "")
        severity = str(item.get("severity") or "")
        result.append(
            [
                str(item.get("recommendation_id") or ""),
                _SEVERITY_LABELS.get(severity, severity),
                _CATEGORY_LABELS.get(category, category),
                _ACTION_LABELS.get(action_code, action_code),
                action_code,
                confidence_state,
                current_state,
                current_value,
                current_currency,
                forecast_state,
                forecast_value,
                forecast_currency,
                limitations_text,
            ]
        )
    return result


def _summary_rows(bundle: Mapping[str, Any]) -> list[list[str]]:
    recommendations = bundle["recommendations"]
    policy_ref = recommendations.get("policy_ref")
    if isinstance(policy_ref, Mapping):
        policy = (
            f"{policy_ref.get('id', '')} v{policy_ref.get('version', '')} "
            f"{policy_ref.get('content_hash', '')}"
        ).strip()
    else:
        policy = ""
    return [
        ["Идентификатор пакета", str(bundle["bundle_id"])],
        ["Сформирован", str(bundle["generated_at"])],
        ["Набор данных", str(bundle["dataset_id"])],
        ["Статус запуска", str(bundle["run_status"])],
        ["Тип источника", str(bundle.get("source_type") or "")],
        ["SHA-256 источника", str(bundle["source_sha256"])],
        ["Статус рекомендаций", str(recommendations.get("status") or "")],
        ["Количество рекомендаций", str(recommendations.get("recommendation_count", 0))],
        ["Политика рекомендаций", policy],
        ["SHA-256 пакета", str(bundle["bundle_hash"])],
    ]


def _limitation_rows(bundle: Mapping[str, Any]) -> list[list[str]]:
    rows = [["Пакет", item] for item in bundle["limitations"]]
    recommendations = bundle["recommendations"].get("recommendations", [])
    if isinstance(recommendations, list):
        for item in recommendations:
            if not isinstance(item, Mapping):
                continue
            recommendation_id = str(item.get("recommendation_id") or "")
            limitations = item.get("limitations", [])
            if isinstance(limitations, list):
                rows.extend(
                    [recommendation_id, str(value)] for value in limitations
                )
    return rows


def _source_rows(bundle: Mapping[str, Any]) -> list[list[str]]:
    analysis = bundle["analysis"]
    result = [
        ["Тип источника", str(bundle.get("source_type") or "")],
        ["SHA-256 источника", str(bundle["source_sha256"])],
        ["Статус моста", str(analysis.get("status") or "")],
        ["Версия схемы", str(analysis.get("schema_version") or "")],
    ]
    for key in (
        "canonical_rows_sha256",
        "canonical_ledger_sha256",
        "header_sha256",
    ):
        if analysis.get(key):
            result.append([key, str(analysis[key])])
    return result


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
    selection = '<selection pane="bottomLeft" activeCell="A2" sqref="A2"/>' if pane else ""
    sheet_views = f'<sheetViews><sheetView workbookViewId="0">{pane}{selection}</sheetView></sheetViews>'
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


def render_xlsx_report(bundle: Mapping[str, Any]) -> bytes:
    validate_local_output_bundle(bundle)
    sheets = [
        ("Сводка", [["Показатель", "Значение"], *_summary_rows(bundle)], False),
        (
            "Показатели",
            [["Метрика", "Состояние", "Значение", "Единица", "Валюта", "Причина", "Источник"], *_metric_rows(bundle)],
            True,
        ),
        (
            "Рекомендации",
            [["ID", "Приоритет", "Категория", "Действие", "Код действия", "Уверенность", "Текущий статус", "Текущий эффект", "Валюта", "Статус прогноза", "Прогноз", "Валюта прогноза", "Ограничения"], *_recommendation_rows(bundle)],
            True,
        ),
        ("Ограничения", [["Область", "Ограничение"], *_limitation_rows(bundle)], True),
        ("Источники", [["Поле", "Значение"], *_source_rows(bundle)], False),
    ]
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
    generated = xml_escape(str(bundle["generated_at"]))
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


def _json_for_html(bundle: Mapping[str, Any]) -> str:
    return (
        _canonical_json_text(bundle)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def render_dashboard_html(bundle: Mapping[str, Any]) -> bytes:
    validate_local_output_bundle(bundle)
    embedded = _json_for_html(bundle)
    title = html_escape(f"Quantum — {bundle.get('source_type') or 'источник'}")
    html = f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
:root{{--bg:#f5f7fa;--panel:#fff;--text:#17202a;--muted:#667085;--border:#dfe3e8;--critical:#b42318;--high:#b54708;--medium:#175cd3;--low:#475467}}
*{{box-sizing:border-box}}body{{margin:0;font-family:Arial,sans-serif;background:var(--bg);color:var(--text)}}
header{{padding:24px 28px;background:#111827;color:white}}header h1{{margin:0 0 6px;font-size:24px}}header p{{margin:0;color:#cbd5e1}}
main{{padding:24px;max-width:1500px;margin:auto}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin-bottom:18px}}
.card,.panel{{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:16px}}.card .k{{color:var(--muted);font-size:12px;text-transform:uppercase}}.card .v{{font-size:22px;font-weight:700;margin-top:7px;word-break:break-word}}
.panel{{margin-bottom:18px;overflow:auto}}h2{{font-size:18px;margin:0 0 14px}}table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{border-bottom:1px solid var(--border);padding:9px;text-align:left;vertical-align:top}}th{{position:sticky;top:0;background:#f8fafc}}input,select{{border:1px solid var(--border);border-radius:6px;padding:8px;margin:0 8px 10px 0}}
.badge{{display:inline-block;padding:3px 7px;border-radius:999px;font-weight:700;font-size:11px}}.CRITICAL{{color:var(--critical);background:#fee4e2}}.HIGH{{color:var(--high);background:#ffead5}}.MEDIUM{{color:var(--medium);background:#dbeafe}}.LOW{{color:var(--low);background:#e4e7ec}}.muted{{color:var(--muted)}}
</style></head><body>
<header><h1>Quantum Analytics</h1><p>Локальный отчёт · данные не отправляются во внешние сервисы</p></header>
<main><section id="summary" class="grid"></section>
<section class="panel"><h2>Показатели</h2><table><thead><tr><th>Метрика</th><th>Состояние</th><th>Значение</th><th>Единица</th><th>Валюта</th></tr></thead><tbody id="metrics"></tbody></table></section>
<section class="panel"><h2>Рекомендации</h2><input id="search" placeholder="Поиск"><select id="severity"><option value="">Все приоритеты</option><option>CRITICAL</option><option>HIGH</option><option>MEDIUM</option><option>LOW</option></select><select id="category"><option value="">Все категории</option></select>
<table><thead><tr><th>Приоритет</th><th>Категория</th><th>Действие</th><th>Текущий эффект</th><th>Прогноз</th><th>Уверенность</th><th>Ограничения</th></tr></thead><tbody id="recommendations"></tbody></table></section>
<section class="panel"><h2>Ограничения</h2><ul id="limitations"></ul></section>
<section class="panel"><h2>Контроль</h2><div class="muted" id="control"></div></section></main>
<script id="bundle-data" type="application/json">{embedded}</script>
<script>
const B=JSON.parse(document.getElementById('bundle-data').textContent);const A=B.analysis||{{}},R=B.recommendations||{{}};
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
const cards=[['Статус',B.run_status],['Источник',B.source_type||'—'],['Рекомендации',R.recommendation_count??0],['Статус рекомендаций',R.status||'—'],['Пакет',B.bundle_hash.slice(0,16)+'…']];
document.getElementById('summary').innerHTML=cards.map(x=>`<div class="card"><div class="k">${{esc(x[0])}}</div><div class="v">${{esc(x[1])}}</div></div>`).join('');
const metrics=A.observed_metrics||{{}};document.getElementById('metrics').innerHTML=Object.keys(metrics).sort().map(k=>{{const m=metrics[k]||{{}};return `<tr><td>${{esc(k)}}</td><td>${{esc(m.state)}}</td><td>${{esc(m.value)}}</td><td>${{esc(m.unit)}}</td><td>${{esc(m.currency)}}</td></tr>`}}).join('');
const items=Array.isArray(R.recommendations)?R.recommendations:[];const cats=[...new Set(items.map(x=>x.category).filter(Boolean))].sort();document.getElementById('category').innerHTML+==cats.map(x=>`<option>${{esc(x)}}</option>`).join('');
function effect(e){{if(!e)return '—';if(e.amount!=null)return `${{e.amount}} ${{e.currency||''}}`;if(e.amount_min!=null||e.amount_max!=null)return `${{e.amount_min??'—'}}…${{e.amount_max??'—'}} ${{e.currency||''}}`;return e.reason_code||e.state||'—'}}
function render(){{const q=document.getElementById('search').value.toLowerCase(),s=document.getElementById('severity').value,c=document.getElementById('category').value;const rows=items.filter(x=>(!s||x.severity===s)&&(!c||x.category===c)&&(!q||JSON.stringify(x).toLowerCase().includes(q)));document.getElementById('recommendations').innerHTML=rows.map(x=>`<tr><td><span class="badge ${{esc(x.severity)}}">${{esc(x.severity)}}</span></td><td>${{esc(x.category)}}</td><td>${{esc(x.action_code)}}</td><td>${{esc(effect(x.current_effect))}}</td><td>${{esc(effect(x.forecast_effect))}}</td><td>${{esc(x.confidence?.state)}}</td><td>${{esc((x.limitations||[]).join(' | '))}}</td></tr>`).join('')}}
['search','severity','category'].forEach(id=>document.getElementById(id).addEventListener(id==='search'?'input':'change',render));render();
document.getElementById('limitations').innerHTML=(B.limitations||[]).map(x=>`<li>${{esc(x)}}</li>`).join('');document.getElementById('control').textContent=`Bundle SHA-256: ${{B.bundle_hash}} · Source SHA-256: ${{B.source_sha256}} · Generated: ${{B.generated_at}}`;
</script></body></html>'''
    return html.encode("utf-8")


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def _artifact_entry(path: Path, payload: bytes) -> dict[str, Any]:
    return {
        "name": path.name,
        "size_bytes": len(payload),
        "sha256": sha256(payload).hexdigest(),
    }


def write_local_output_bundle(
    report: Mapping[str, Any],
    *,
    output_root: Path,
    generated_at: datetime | str,
) -> dict[str, Any]:
    if not isinstance(output_root, Path):
        raise OutputBundleError("OUTPUT_ROOT_INVALID")
    bundle = build_local_output_bundle(report, generated_at=generated_at)
    token = _SAFE_TOKEN.sub("-", str(bundle["dataset_id"])).strip("-._")
    if not token:
        token = bundle["bundle_hash"][:16]
    target = output_root.resolve() / ("quantum_" + token[:80])
    target.mkdir(parents=True, exist_ok=True)

    payloads = {
        "quantum_result.json": _canonical_json_bytes(bundle),
        "recommendations.json": _canonical_json_bytes(bundle["recommendations"]),
        "Quantum_Report.xlsx": render_xlsx_report(bundle),
        "dashboard.html": render_dashboard_html(bundle),
    }
    artifacts: list[dict[str, Any]] = []
    for name in sorted(payloads):
        path = target / name
        _atomic_write(path, payloads[name])
        artifacts.append(_artifact_entry(path, payloads[name]))
    manifest: dict[str, Any] = {
        "schema_version": LOCAL_OUTPUT_MANIFEST_SCHEMA_VERSION,
        "bundle_id": bundle["bundle_id"],
        "bundle_hash": bundle["bundle_hash"],
        "generated_at": bundle["generated_at"],
        "manifest_excludes_self": True,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "manifest_hash": "",
    }
    manifest["manifest_hash"] = sha256(
        _canonical_json_bytes(
            {key: value for key, value in manifest.items() if key != "manifest_hash"}
        )
    ).hexdigest()
    manifest_payload = _canonical_json_bytes(manifest)
    manifest_path = target / "evidence_manifest.json"
    _atomic_write(manifest_path, manifest_payload)
    return {
        "status": "OUTPUT_BUNDLE_COMPLETE",
        "schema_version": LOCAL_OUTPUT_MANIFEST_SCHEMA_VERSION,
        "directory": str(target),
        "bundle_hash": bundle["bundle_hash"],
        "manifest_hash": manifest["manifest_hash"],
        "artifacts": [
            {**entry, "path": str(target / entry["name"])} for entry in artifacts
        ]
        + [
            {
                **_artifact_entry(manifest_path, manifest_payload),
                "path": str(manifest_path),
            }
        ],
    }
