from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import os
import re
import time
import zipfile
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

_ALLOWED_UPLOAD_SUFFIXES = {".csv", ".xlsx"}
_COST_TABLE_SUFFIXES = {".csv", ".xlsx"}
_REQUIRED_CALCULATION_FIELDS = (
    "sale_price",
    "product_cost",
    "commission_amount",
    "forward_logistics",
    "reverse_logistics",
    "paid_storage",
    "advertising",
    "fines",
    "tax",
    "software",
    "defects",
    "loss_damage",
    "other_expense",
)
_ANALYSIS_EXPENSE_FIELDS = (
    "commission_amount",
    "forward_logistics",
    "reverse_logistics",
    "paid_storage",
    "advertising",
    "fines",
    "software",
    "defects",
    "loss_damage",
)
_MONEY = Decimal("0.01")

_ALIASES = {
    "article": (
        "article",
        "supplier_article",
        "vendor_code",
        "nm_id",
        "barcode",
        "Артикул",
        "Артикул поставщика",
        "Номенклатура",
        "Код номенклатуры",
        "Баркод",
        "Штрихкод",
    ),
    "quantity": ("quantity", "qty", "Количество", "Кол-во", "Продано, шт.", "sold_qty"),
    "sale_price": (
        "sale_price",
        "price",
        "retail_price",
        "retail_price_withdisc_rub",
        "Цена розничная с учетом согласованной скидки",
        "Цена розничная",
        "Сумма продаж",
        "Выручка",
    ),
    "product_cost": ("product_cost", "cost", "Себестоимость", "Себестоимость товара"),
    "commission_amount": ("commission_amount", "commission", "Комиссия", "Вознаграждение Вайлдберриз"),
    "forward_logistics": ("forward_logistics", "logistics", "Логистика", "Логистика прямая"),
    "reverse_logistics": ("reverse_logistics", "return_logistics", "Обратная логистика", "Логистика обратная"),
    "paid_storage": ("paid_storage", "storage", "Хранение", "Платное хранение"),
    "advertising": ("advertising", "ads", "Реклама", "Продвижение"),
    "fines": ("fines", "penalty", "Штрафы", "Удержания", "Доплаты"),
    "software": ("software", "software_services", "Сервисы", "ПО", "software"),
    "defects": ("defects", "defect", "Брак", "Производственный брак"),
    "loss_damage": ("loss_damage", "loss", "damage", "Потери", "Порча", "Утеря"),
}


def runtime_root() -> Path:
    configured = os.environ.get("QUANTUM_RUNTIME_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / ".quantum-analytics" / "local-pilot").resolve()


def ensure_runtime_layout() -> dict[str, str]:
    root = runtime_root()
    layout = {
        "root": root,
        "config": root / "config",
        "data": root / "data",
        "uploads": root / "uploads",
        "receipts": root / "receipts",
        "evidence": root / "evidence",
        "output": root / "output",
        "logs": root / "logs",
    }
    for path in layout.values():
        path.mkdir(parents=True, exist_ok=True)
    return {name: str(path) for name, path in layout.items()}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_name(name: str) -> str:
    candidate = re.sub(r"[^A-Za-z0-9А-Яа-яЁё._-]+", "_", name.strip())
    return candidate[:120] or "upload.bin"


def _json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    try:
        with temp.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_write_bytes(
        path,
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8"),
    )


def _decimal(value: Any, field: str) -> Decimal:
    if value is None or value == "":
        raise ValueError(f"missing:{field}")
    try:
        return Decimal(str(value).replace("\xa0", "").replace(" ", "").replace(",", ".")).quantize(
            _MONEY, rounding=ROUND_HALF_UP
        )
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid_decimal:{field}") from exc


def _non_negative_decimal(value: Any, field: str) -> Decimal:
    parsed = _decimal(value, field)
    if parsed < 0:
        raise ValueError(f"negative_not_allowed:{field}")
    return parsed


def _percent(value: Any, field: str) -> Decimal:
    parsed = _non_negative_decimal(value, field)
    if parsed > Decimal("100.00"):
        raise ValueError(f"percent_out_of_range:{field}")
    return parsed


def _normalize(value: str) -> str:
    return re.sub(r"[^0-9a-zа-яё]+", "", str(value).strip().lower())


_ALIAS_INDEX = {
    canonical: {_normalize(alias) for alias in aliases}
    for canonical, aliases in _ALIASES.items()
}


def _canonical_columns(header: list[str]) -> dict[str, str]:
    by_normalized = {_normalize(name): name for name in header}
    result: dict[str, str] = {}
    for canonical, aliases in _ALIAS_INDEX.items():
        for alias in aliases:
            if alias in by_normalized:
                result[canonical] = by_normalized[alias]
                break
    return result


def _decode_csv(data: bytes) -> str:
    last_error: UnicodeDecodeError | None = None
    for encoding in ("utf-8-sig", "cp1251", "windows-1251"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error is not None:
        raise ValueError("unsupported_csv_encoding") from last_error
    raise ValueError("unsupported_csv_encoding")


def _rows_from_csv(data: bytes) -> list[dict[str, str]]:
    text = _decode_csv(data)
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
        if ";" in sample:
            dialect.delimiter = ";"
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if reader.fieldnames is None:
        raise ValueError("empty_csv_header")
    return [{str(k or "").strip(): str(v or "").strip() for k, v in row.items()} for row in reader]


def _xlsx_col_index(cell_ref: str) -> int:
    letters = re.sub(r"[^A-Z]", "", cell_ref.upper())
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return max(index - 1, 0)


def _xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        xml = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ElementTree.fromstring(xml)
    values = []
    for item in root.findall(".//{*}si"):
        values.append("".join(text.text or "" for text in item.findall(".//{*}t")))
    return values


def _xlsx_cell_value(cell: ElementTree.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(text.text or "" for text in cell.findall(".//{*}t")).strip()
    value = cell.find("{*}v")
    if value is None or value.text is None:
        return ""
    raw = value.text.strip()
    if cell_type == "s":
        try:
            return shared_strings[int(raw)].strip()
        except (ValueError, IndexError):
            return ""
    return raw


def _rows_from_xlsx(data: bytes) -> list[dict[str, str]]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            sheet_names = [name for name in archive.namelist() if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")]
            if not sheet_names:
                raise ValueError("xlsx_no_worksheets")
            sheet_xml = archive.read(sorted(sheet_names)[0])
            shared_strings = _xlsx_shared_strings(archive)
    except zipfile.BadZipFile as exc:
        raise ValueError("invalid_xlsx") from exc

    root = ElementTree.fromstring(sheet_xml)
    parsed_rows: list[list[str]] = []
    for row in root.findall(".//{*}sheetData/{*}row"):
        cells: dict[int, str] = {}
        for cell in row.findall("{*}c"):
            ref = cell.attrib.get("r", "A")
            cells[_xlsx_col_index(ref)] = _xlsx_cell_value(cell, shared_strings)
        if not cells:
            continue
        max_index = max(cells)
        parsed_rows.append([cells.get(index, "") for index in range(max_index + 1)])
    if not parsed_rows:
        raise ValueError("xlsx_empty")

    header = [str(value).strip() for value in parsed_rows[0]]
    result = []
    for row in parsed_rows[1:]:
        result.append({header[index]: str(row[index]).strip() if index < len(row) else "" for index in range(len(header))})
    return result


def _rows_from_table(filename: str, body: bytes) -> list[dict[str, str]]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        return _rows_from_csv(body)
    if suffix == ".xlsx":
        return _rows_from_xlsx(body)
    raise ValueError("unsupported_table_format_for_analysis")


def _value_from_row(row: dict[str, str], columns: dict[str, str], field: str) -> str | None:
    column = columns.get(field)
    if column is None:
        return None
    value = row.get(column)
    if value is None or value == "":
        return None
    return value


def upload_local_file(filename: str, body: bytes, content_type: str = "") -> tuple[int, dict[str, Any]]:
    layout = ensure_runtime_layout()
    original_name = _safe_name(filename)
    suffix = Path(original_name).suffix.lower()
    if suffix not in _ALLOWED_UPLOAD_SUFFIXES:
        return 400, {
            "status": "rejected",
            "reason": "unsupported_file_type",
            "allowed_suffixes": sorted(_ALLOWED_UPLOAD_SUFFIXES),
        }
    if not body:
        return 400, {"status": "rejected", "reason": "empty_upload"}

    digest = sha256_bytes(body)
    receipt_path = Path(layout["receipts"]) / f"{digest}.json"
    existing = _json_file(receipt_path)
    if existing is not None:
        existing["duplicate"] = True
        existing["marketplace_write_enabled"] = False
        return 200, existing

    stored_name = f"{digest}{suffix}"
    stored_path = Path(layout["uploads"]) / stored_name
    _atomic_write_bytes(stored_path, body)
    receipt = {
        "status": "accepted",
        "duplicate": False,
        "sha256": digest,
        "original_filename": original_name,
        "stored_filename": stored_name,
        "size_bytes": len(body),
        "content_type": content_type,
        "received_at_epoch": int(time.time()),
        "data_status": "UPLOADED",
        "marketplace_write_enabled": False,
    }
    _atomic_write_json(receipt_path, receipt)
    return 201, receipt


def calculate_unit(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    missing = [field for field in _REQUIRED_CALCULATION_FIELDS if field not in payload]
    if missing:
        return 400, {
            "status": "blocked",
            "reason": "missing_required_fields",
            "missing_fields": missing,
            "no_hidden_defaults": True,
        }

    try:
        values = {field: _non_negative_decimal(payload.get(field), field) for field in _REQUIRED_CALCULATION_FIELDS}
    except ValueError as exc:
        return 400, {"status": "blocked", "reason": str(exc), "no_hidden_defaults": True}

    expense_fields = [field for field in _REQUIRED_CALCULATION_FIELDS if field != "sale_price"]
    total_expense = sum((values[field] for field in expense_fields), Decimal("0.00"))
    net_profit = values["sale_price"] - total_expense
    profitability = None
    if total_expense != 0:
        profitability = (net_profit / total_expense * Decimal("100.00")).quantize(_MONEY)

    response = {
        "status": "calculated",
        "currency": "RUB",
        "inputs": {field: str(values[field]) for field in _REQUIRED_CALCULATION_FIELDS},
        "total_expense": str(total_expense.quantize(_MONEY)),
        "net_profit": str(net_profit.quantize(_MONEY)),
        "profitability_percent_of_costs": None if profitability is None else str(profitability),
        "no_hidden_defaults": True,
        "marketplace_write_enabled": False,
        "evidence_chain": {
            "calculation_engine": "local-pilot-decimal-v1",
            "rounding": "Decimal ROUND_HALF_UP to 0.01 RUB",
            "required_fields": list(_REQUIRED_CALCULATION_FIELDS),
        },
    }
    return 200, response


def save_cost_table(filename: str, body: bytes, content_type: str = "") -> tuple[int, dict[str, Any]]:
    original_name = _safe_name(filename)
    if Path(original_name).suffix.lower() not in _COST_TABLE_SUFFIXES:
        return 400, {"status": "rejected", "reason": "unsupported_cost_table_type", "allowed_suffixes": sorted(_COST_TABLE_SUFFIXES)}
    if not body:
        return 400, {"status": "rejected", "reason": "empty_cost_table"}

    try:
        rows = _rows_from_table(original_name, body)
    except ValueError as exc:
        return 400, {"status": "blocked", "reason": str(exc), "no_hidden_defaults": True}

    if not rows:
        return 400, {"status": "blocked", "reason": "empty_cost_table", "no_hidden_defaults": True}

    columns = _canonical_columns(list(rows[0].keys()))
    if "article" not in columns or "product_cost" not in columns:
        return 400, {
            "status": "blocked",
            "reason": "cost_table_requires_article_and_product_cost",
            "detected_columns": columns,
            "no_hidden_defaults": True,
        }

    costs: dict[str, str] = {}
    rejected = 0
    for row in rows:
        article = _value_from_row(row, columns, "article")
        cost = _value_from_row(row, columns, "product_cost")
        if not article or cost is None:
            rejected += 1
            continue
        try:
            costs[str(article).strip()] = str(_non_negative_decimal(cost, "product_cost"))
        except ValueError:
            rejected += 1

    if not costs:
        return 400, {"status": "blocked", "reason": "cost_table_has_no_valid_rows", "no_hidden_defaults": True}

    layout = ensure_runtime_layout()
    digest = sha256_bytes(body)
    payload = {
        "status": "accepted",
        "sha256": digest,
        "original_filename": original_name,
        "content_type": content_type,
        "costs": costs,
        "accepted_rows": len(costs),
        "rejected_rows": rejected,
        "marketplace_write_enabled": False,
    }
    _atomic_write_json(Path(layout["config"]) / "cost_table.json", payload)
    return 201, {key: value for key, value in payload.items() if key != "costs"} | {"articles": sorted(costs)}


def _load_costs() -> dict[str, str]:
    layout = ensure_runtime_layout()
    payload = _json_file(Path(layout["config"]) / "cost_table.json")
    if not payload:
        return {}
    costs = payload.get("costs")
    return costs if isinstance(costs, dict) else {}


def _settings_decimal(settings: dict[str, Any], field: str) -> Decimal:
    return _non_negative_decimal(settings.get(field), field)


def _expense_for_row(row: dict[str, str], columns: dict[str, str], settings: dict[str, Any], field: str) -> Decimal:
    value = _value_from_row(row, columns, field)
    if value is not None:
        return _non_negative_decimal(value, field)
    explicit = settings.get(field)
    if explicit is not None and explicit != "":
        return _non_negative_decimal(explicit, field)
    raise ValueError(f"missing:{field}")


def _quantity_for_row(row: dict[str, str], columns: dict[str, str], settings: dict[str, Any]) -> Decimal:
    value = _value_from_row(row, columns, "quantity")
    if value is not None:
        return _non_negative_decimal(value, "quantity")
    if settings.get("row_quantity_mode") == "one_per_row":
        return Decimal("1.00")
    raise ValueError("missing:quantity")


def _product_cost_for_row(row: dict[str, str], columns: dict[str, str], settings: dict[str, Any], costs: dict[str, str], article: str) -> Decimal:
    value = _value_from_row(row, columns, "product_cost")
    if value is not None:
        return _non_negative_decimal(value, "product_cost")
    if article in costs:
        return _non_negative_decimal(costs[article], "product_cost")
    if settings.get("product_cost") not in (None, ""):
        return _settings_decimal(settings, "product_cost")
    raise ValueError("missing:product_cost")


def _recommend(net_profit: Decimal, sale_price_total: Decimal, advertising: Decimal) -> str:
    if net_profit < 0:
        return "STOP_LOSS_REVIEW"
    if sale_price_total == 0:
        return "DATA_REVIEW"
    margin = (net_profit / sale_price_total * Decimal("100.00")).quantize(_MONEY)
    if margin < Decimal("10.00"):
        return "REPRICE_OR_COST_REVIEW"
    if advertising > 0 and net_profit <= advertising:
        return "ADS_EFFICIENCY_REVIEW"
    if margin >= Decimal("20.00"):
        return "PROMOTE_CANDIDATE"
    return "KEEP_MONITORING"


def analyze_wb_rows(rows: list[dict[str, str]], settings: dict[str, Any] | None = None, costs: dict[str, str] | None = None) -> tuple[int, dict[str, Any]]:
    settings = dict(settings or {})
    costs = dict(costs or {})
    if not rows:
        return 400, {"status": "blocked", "reason": "empty_report", "no_hidden_defaults": True}

    columns = _canonical_columns(list(rows[0].keys()))
    if "article" not in columns or "sale_price" not in columns:
        return 400, {
            "status": "blocked",
            "reason": "wb_report_requires_article_and_sale_price",
            "detected_columns": columns,
            "no_hidden_defaults": True,
        }

    missing_settings = [field for field in ("tax_rate_percent", "other_expense") if settings.get(field) in (None, "")]
    if missing_settings:
        return 400, {
            "status": "blocked",
            "reason": "missing_required_settings",
            "missing_fields": missing_settings,
            "no_hidden_defaults": True,
        }

    try:
        tax_rate = _percent(settings.get("tax_rate_percent"), "tax_rate_percent")
        other_expense = _settings_decimal(settings, "other_expense")
    except ValueError as exc:
        return 400, {"status": "blocked", "reason": str(exc), "no_hidden_defaults": True}
    result_rows: list[dict[str, Any]] = []
    blocked_rows: list[dict[str, Any]] = []

    totals = {
        "revenue": Decimal("0.00"),
        "product_cost": Decimal("0.00"),
        "total_expense": Decimal("0.00"),
        "net_profit": Decimal("0.00"),
        "tax": Decimal("0.00"),
        "advertising": Decimal("0.00"),
    }

    for index, row in enumerate(rows, start=2):
        try:
            article = str(_value_from_row(row, columns, "article") or "").strip()
            if not article:
                raise ValueError("missing:article")
            quantity = _quantity_for_row(row, columns, settings)
            sale_price = _non_negative_decimal(_value_from_row(row, columns, "sale_price"), "sale_price")
            product_cost = _product_cost_for_row(row, columns, settings, costs, article)
            sale_price_total = (sale_price * quantity).quantize(_MONEY)
            product_cost_total = (product_cost * quantity).quantize(_MONEY)
            expenses = {field: _expense_for_row(row, columns, settings, field) for field in _ANALYSIS_EXPENSE_FIELDS}
            tax = (sale_price_total * tax_rate / Decimal("100.00")).quantize(_MONEY)
            other = (other_expense * quantity).quantize(_MONEY)
            total_expense = product_cost_total + tax + other + sum(expenses.values(), Decimal("0.00"))
            net_profit = sale_price_total - total_expense
            recommendation = _recommend(net_profit, sale_price_total, expenses["advertising"])
            result = {
                "row_number": index,
                "article": article,
                "quantity": str(quantity),
                "sale_price": str(sale_price.quantize(_MONEY)),
                "revenue": str(sale_price_total.quantize(_MONEY)),
                "product_cost": str(product_cost.quantize(_MONEY)),
                "product_cost_total": str(product_cost_total.quantize(_MONEY)),
                "tax": str(tax.quantize(_MONEY)),
                "other_expense": str(other.quantize(_MONEY)),
                **{field: str(value.quantize(_MONEY)) for field, value in expenses.items()},
                "total_expense": str(total_expense.quantize(_MONEY)),
                "net_profit": str(net_profit.quantize(_MONEY)),
                "recommendation": recommendation,
            }
            result_rows.append(result)
            totals["revenue"] += sale_price_total
            totals["product_cost"] += product_cost_total
            totals["total_expense"] += total_expense
            totals["net_profit"] += net_profit
            totals["tax"] += tax
            totals["advertising"] += expenses["advertising"]
        except ValueError as exc:
            blocked_rows.append({"row_number": index, "status": "blocked", "reason": str(exc)})

    dashboard = {
        "rows_total": len(rows),
        "rows_calculated": len(result_rows),
        "rows_blocked": len(blocked_rows),
        "revenue": str(totals["revenue"].quantize(_MONEY)),
        "product_cost": str(totals["product_cost"].quantize(_MONEY)),
        "total_expense": str(totals["total_expense"].quantize(_MONEY)),
        "net_profit": str(totals["net_profit"].quantize(_MONEY)),
        "tax": str(totals["tax"].quantize(_MONEY)),
        "advertising": str(totals["advertising"].quantize(_MONEY)),
        "negative_items": sum(1 for row in result_rows if Decimal(row["net_profit"]) < 0),
        "promote_candidates": sum(1 for row in result_rows if row["recommendation"] == "PROMOTE_CANDIDATE"),
    }
    confirmed = bool(result_rows) and not blocked_rows
    payload = {
        "status": "analyzed" if confirmed else "blocked",
        "confirmed_calculation": confirmed,
        "partial_results_status": None if confirmed else "UNCONFIRMED_PARTIAL_PREVIEW",
        "currency": "RUB",
        "marketplace": "Wildberries",
        "dashboard": dashboard,
        "rows": result_rows,
        "blocked_rows": blocked_rows,
        "detected_columns": columns,
        "no_hidden_defaults": True,
        "marketplace_write_enabled": False,
        "evidence_chain": {
            "calculation_engine": "wb-local-dashboard-v1",
            "rounding": "Decimal ROUND_HALF_UP to 0.01 RUB",
            "required_settings": ["tax_rate_percent", "other_expense"],
            "cost_sources": ["report_row", "uploaded_cost_table", "manual_product_cost"],
        },
    }
    return (200 if confirmed else 400), payload


def analyze_uploaded_report(sha256: str, settings: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    layout = ensure_runtime_layout()
    receipt = _json_file(Path(layout["receipts"]) / f"{sha256}.json")
    if not receipt:
        return 404, {"status": "blocked", "reason": "upload_receipt_not_found", "sha256": sha256}
    stored_filename = receipt.get("stored_filename")
    original_filename = receipt.get("original_filename")
    if not isinstance(stored_filename, str) or not isinstance(original_filename, str):
        return 400, {"status": "blocked", "reason": "invalid_upload_receipt"}
    body = (Path(layout["uploads"]) / stored_filename).read_bytes()
    try:
        rows = _rows_from_table(original_filename, body)
    except ValueError as exc:
        return 400, {"status": "blocked", "reason": str(exc), "data_status": "QUARANTINED", "no_hidden_defaults": True}

    code, analysis = analyze_wb_rows(rows, settings, _load_costs())
    analysis["source_upload_sha256"] = sha256
    evidence_id = sha256_bytes(json.dumps(analysis, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    analysis["analysis_sha256"] = evidence_id
    _atomic_write_json(Path(layout["evidence"]) / f"analysis-{evidence_id}.json", analysis)
    return code, analysis


def _xml_text(value: Any) -> str:
    return html.escape(str(value), quote=False)


def _xlsx_sheet(rows: list[list[Any]]) -> str:
    out = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>',
    ]
    for row_index, row in enumerate(rows, start=1):
        out.append(f'<row r="{row_index}">')
        for col_index, value in enumerate(row, start=1):
            col = ""
            n = col_index
            while n:
                n, remainder = divmod(n - 1, 26)
                col = chr(65 + remainder) + col
            cell_ref = f"{col}{row_index}"
            out.append(f'<c r="{cell_ref}" t="inlineStr"><is><t>{_xml_text(value)}</t></is></c>')
        out.append("</row>")
    out.append("</sheetData></worksheet>")
    return "".join(out)


def analysis_to_xlsx_bytes(analysis: dict[str, Any]) -> bytes:
    dashboard = analysis.get("dashboard", {})
    summary_rows = [["Metric", "Value"]] + [[key, value] for key, value in sorted(dashboard.items())]
    data_rows = analysis.get("rows", [])
    headers = [
        "article",
        "quantity",
        "revenue",
        "product_cost_total",
        "tax",
        "other_expense",
        "total_expense",
        "net_profit",
        "recommendation",
    ]
    row_rows = [headers] + [[row.get(header, "") for header in headers] for row in data_rows]
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>""")
        archive.writestr("_rels/.rels", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>""")
        archive.writestr("xl/_rels/workbook.xml.rels", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/></Relationships>""")
        archive.writestr("xl/workbook.xml", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Dashboard" sheetId="1" r:id="rId1"/><sheet name="Rows" sheetId="2" r:id="rId2"/></sheets></workbook>""")
        archive.writestr("xl/worksheets/sheet1.xml", _xlsx_sheet(summary_rows))
        archive.writestr("xl/worksheets/sheet2.xml", _xlsx_sheet(row_rows))
    return output.getvalue()


def _analysis_without_digest(analysis: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in analysis.items() if key != "analysis_sha256"}


def save_analysis_export(analysis_evidence_id: Any) -> tuple[int, dict[str, Any]]:
    if not isinstance(analysis_evidence_id, str) or re.fullmatch(r"[0-9a-f]{64}", analysis_evidence_id) is None:
        return 400, {"status": "blocked", "reason": "analysis_evidence_id_required"}

    layout = ensure_runtime_layout()
    evidence_path = Path(layout["evidence"]) / f"analysis-{analysis_evidence_id}.json"
    if not evidence_path.exists():
        return 404, {"status": "blocked", "reason": "analysis_evidence_not_found"}
    analysis = _json_file(evidence_path)
    if analysis is None:
        return 409, {"status": "blocked", "reason": "analysis_evidence_corrupt"}

    actual_id = sha256_bytes(
        json.dumps(_analysis_without_digest(analysis), sort_keys=True, ensure_ascii=False).encode("utf-8")
    )
    if analysis.get("analysis_sha256") != analysis_evidence_id or actual_id != analysis_evidence_id:
        return 409, {"status": "blocked", "reason": "analysis_evidence_integrity_failed"}
    if (
        analysis.get("status") != "analyzed"
        or analysis.get("confirmed_calculation") is not True
        or analysis.get("blocked_rows")
    ):
        return 400, {"status": "blocked", "reason": "confirmed_analysis_required"}

    data = analysis_to_xlsx_bytes(analysis)
    digest = sha256_bytes(data)
    path = Path(layout["output"]) / f"quantum-wb-analysis-{digest[:12]}.xlsx"
    _atomic_write_bytes(path, data)
    return 201, {
        "status": "exported",
        "filename": path.name,
        "path": str(path),
        "sha256": digest,
        "size_bytes": len(data),
        "marketplace_write_enabled": False,
    }


def local_pilot_health() -> dict[str, Any]:
    return {
        "status": "READY",
        "scope_status": "LOCAL_PILOT_READY",
        "release_status": "RELEASE_BLOCKED",
        "component": "quantum-local-pilot",
        "runtime_layout": ensure_runtime_layout(),
        "allowed_upload_suffixes": sorted(_ALLOWED_UPLOAD_SUFFIXES),
        "cost_table_suffixes": sorted(_COST_TABLE_SUFFIXES),
        "required_calculation_fields": list(_REQUIRED_CALCULATION_FIELDS),
        "ready_capabilities": [
            "wb_report_upload",
            "manual_product_cost",
            "cost_table_upload",
            "profit_calculation",
            "dashboard",
            "recommendations",
            "xlsx_export",
        ],
        "marketplace_write_enabled": False,
    }


def render_local_ui() -> str:
    unit_fields = "".join(
        f'<label>{html.escape(field)}<input name="{html.escape(field)}" inputmode="decimal"></label>'
        for field in _REQUIRED_CALCULATION_FIELDS
    )
    profile_fields = "".join(
        f'<label>{html.escape(field)}<input id="{html.escape(field)}" inputmode="decimal" placeholder="обязательно, можно 0"></label>'
        for field in ("product_cost", "tax_rate_percent", "other_expense", *_ANALYSIS_EXPENSE_FIELDS)
    )
    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Quantum WB Release</title>
<style>
body{{font-family:Arial,sans-serif;max-width:1120px;margin:24px auto;padding:0 16px;line-height:1.45}}
section{{border:1px solid #ddd;border-radius:8px;padding:14px;margin:14px 0}}
label{{display:block;margin:8px 0}} input{{width:100%;padding:8px;box-sizing:border-box}} button{{padding:10px 14px;margin:8px 8px 0 0}}
pre{{background:#f4f4f4;padding:12px;overflow:auto;white-space:pre-wrap}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}}
table{{width:100%;border-collapse:collapse}} th,td{{border:1px solid #ddd;padding:6px;text-align:left}}
.bad{{color:#9b0000;font-weight:bold}} .good{{color:#006b2e;font-weight:bold}}
</style>
</head>
<body>
<h1>Quantum WB Release</h1>
<p><b>LOCAL PILOT READY.</b> Локальная read-only программа для Wildberries. Полный production-релиз заблокирован. Данные сохраняются в runtime-папку. Marketplace write disabled.</p>

<section>
<h2>1. Загрузка отчёта Wildberries</h2>
<input id="wbFile" type="file" accept=".csv,.xlsx">
<button onclick="uploadWb()">Загрузить WB отчёт</button>
<p id="uploadStatus"></p>
</section>

<section>
<h2>2. Таблица себестоимости</h2>
<p>CSV/XLSX с колонками: article / Артикул и product_cost / Себестоимость.</p>
<input id="costFile" type="file" accept=".csv,.xlsx">
<button onclick="uploadCostTable()">Загрузить таблицу себестоимости</button>
</section>

<section>
<h2>3. Ручной профиль расчёта</h2>
<p>Скрытых значений нет. Если расходов нет — введи 0.</p>
<div class="grid">{profile_fields}</div>
<label><input id="onePerRow" type="checkbox"> В отчёте одна строка = одна проданная единица, если нет колонки quantity</label>
<button onclick="analyze()">Рассчитать WB</button>
<button onclick="exportXlsx()">Экспорт Excel</button>
</section>

<section>
<h2>Dashboard</h2>
<div id="dashboard"></div>
</section>

<section>
<h2>Рекомендации и строки</h2>
<div id="rows"></div>
</section>

<section>
<h2>Unit calculation</h2>
<form id="calc">{unit_fields}</form>
<button onclick="calculate()">Calculate unit</button>
</section>

<pre id="out" aria-live="polite"></pre>
<script>
let lastUploadSha = null;
let lastAnalysis = null;
function show(payload){{document.getElementById('out').textContent = JSON.stringify(payload,null,2);}}
function escapeHtml(value){{
  return String(value ?? '').replace(/[&<>"']/g, char => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[char]));
}}
async function uploadWb(){{
  const file = document.getElementById('wbFile').files[0];
  if(!file) return show({{status:'blocked', reason:'no_wb_file_selected'}});
  const res = await fetch('/api/local-pilot/upload?filename=' + encodeURIComponent(file.name), {{method:'POST', body:file}});
  const payload = await res.json();
  if(payload.sha256) lastUploadSha = payload.sha256;
  document.getElementById('uploadStatus').textContent = payload.sha256 ? 'Загружено: ' + payload.sha256 : 'Не загружено';
  show(payload);
}}
async function uploadCostTable(){{
  const file = document.getElementById('costFile').files[0];
  if(!file) return show({{status:'blocked', reason:'no_cost_file_selected'}});
  const res = await fetch('/api/local-pilot/cost-table?filename=' + encodeURIComponent(file.name), {{method:'POST', body:file}});
  show(await res.json());
}}
function profile(){{
  const payload = {{}};
  for (const id of ['product_cost','tax_rate_percent','other_expense','commission_amount','forward_logistics','reverse_logistics','paid_storage','advertising','fines','software','defects','loss_damage']) {{
    payload[id] = document.getElementById(id).value;
  }}
  if(document.getElementById('onePerRow').checked) payload.row_quantity_mode = 'one_per_row';
  return payload;
}}
async function analyze(){{
  if(!lastUploadSha) return show({{status:'blocked', reason:'no_uploaded_wb_report'}});
  const payload = profile();
  payload.sha256 = lastUploadSha;
  const res = await fetch('/api/local-pilot/analyze', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify(payload)}});
  lastAnalysis = await res.json();
  renderAnalysis(lastAnalysis);
  show(lastAnalysis);
}}
function renderAnalysis(payload){{
  const dashboard = payload.dashboard || {{}};
  document.getElementById('dashboard').innerHTML = '<table>' + Object.entries(dashboard).map(([k,v]) => `<tr><th>${{escapeHtml(k)}}</th><td>${{escapeHtml(v)}}</td></tr>`).join('') + '</table>';
  const rows = payload.rows || [];
  document.getElementById('rows').innerHTML = '<table><tr><th>Артикул</th><th>Выручка</th><th>Прибыль</th><th>Рекомендация</th></tr>' +
    rows.map(row => `<tr><td>${{escapeHtml(row.article)}}</td><td>${{escapeHtml(row.revenue)}}</td><td class="${{Number(row.net_profit)<0?'bad':'good'}}">${{escapeHtml(row.net_profit)}}</td><td>${{escapeHtml(row.recommendation)}}</td></tr>`).join('') + '</table>';
}}
async function exportXlsx(){{
  if(!lastAnalysis || lastAnalysis.status !== 'analyzed') return show({{status:'blocked', reason:'no_successful_analysis_to_export'}});
  const res = await fetch('/api/local-pilot/export', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify({{analysis_sha256:lastAnalysis.analysis_sha256}})}});
  show(await res.json());
}}
async function calculate(){{
  const payload = {{}};
  for (const item of new FormData(document.getElementById('calc')).entries()) payload[item[0]] = item[1];
  const res = await fetch('/api/local-pilot/calculate', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify(payload)}});
  show(await res.json());
}}
</script>
</body>
</html>"""
