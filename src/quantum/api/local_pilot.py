from __future__ import annotations

import hashlib
import html
import json
import os
import re
import time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

_ALLOWED_UPLOAD_SUFFIXES = {".csv", ".xlsx", ".xls"}
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
_MONEY = Decimal("0.01")


def runtime_root() -> Path:
    configured = os.environ.get("QUANTUM_RUNTIME_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / ".quantum-analytics" / "local-pilot").resolve()


def ensure_runtime_layout() -> dict[str, str]:
    root = runtime_root()
    layout = {
        "root": root,
        "uploads": root / "uploads",
        "receipts": root / "receipts",
        "evidence": root / "evidence",
    }
    for path in layout.values():
        path.mkdir(parents=True, exist_ok=True)
    return {name: str(path) for name, path in layout.items()}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_name(name: str) -> str:
    candidate = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip())
    return candidate[:120] or "upload.bin"


def _json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


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
    stored_path.write_bytes(body)
    receipt = {
        "status": "accepted",
        "duplicate": False,
        "sha256": digest,
        "original_filename": original_name,
        "stored_filename": stored_name,
        "size_bytes": len(body),
        "content_type": content_type,
        "received_at_epoch": int(time.time()),
        "data_status": "QUARANTINED",
        "marketplace_write_enabled": False,
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    return 201, receipt


def _decimal(value: Any, field: str) -> Decimal:
    if value is None or value == "":
        raise ValueError(f"missing:{field}")
    try:
        return Decimal(str(value)).quantize(_MONEY, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid_decimal:{field}") from exc


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
        values = {field: _decimal(payload.get(field), field) for field in _REQUIRED_CALCULATION_FIELDS}
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


def local_pilot_health() -> dict[str, Any]:
    return {
        "status": "ok",
        "component": "quantum-local-pilot",
        "runtime_layout": ensure_runtime_layout(),
        "allowed_upload_suffixes": sorted(_ALLOWED_UPLOAD_SUFFIXES),
        "required_calculation_fields": list(_REQUIRED_CALCULATION_FIELDS),
        "marketplace_write_enabled": False,
    }


def render_local_ui() -> str:
    fields = "".join(
        f'<label>{html.escape(field)}<input name="{html.escape(field)}" inputmode="decimal"></label>'
        for field in _REQUIRED_CALCULATION_FIELDS
    )
    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Quantum Local Pilot</title>
<style>
body{{font-family:Arial,sans-serif;max-width:920px;margin:32px auto;padding:0 16px;line-height:1.45}}
label{{display:block;margin:8px 0}} input{{width:100%;padding:8px}} button{{padding:10px 14px;margin-top:10px}}
pre{{background:#f4f4f4;padding:12px;overflow:auto}}
</style>
</head>
<body>
<h1>Quantum Local Pilot</h1>
<p>Локальный режим. Marketplace write disabled. Данные сохраняются только в локальную runtime-папку.</p>
<h2>Upload WB CSV/XLSX</h2>
<input id="file" type="file" accept=".csv,.xlsx,.xls">
<button onclick="uploadFile()">Upload</button>
<h2>Unit calculation</h2>
<form id="calc">{fields}</form>
<button onclick="calculate()">Calculate</button>
<pre id="out" aria-live="polite"></pre>
<script>
async function uploadFile(){{
  const file = document.getElementById('file').files[0];
  if(!file) return show({{status:'blocked', reason:'no_file_selected'}});
  const res = await fetch('/api/local-pilot/upload?filename=' + encodeURIComponent(file.name), {{method:'POST', body:file}});
  show(await res.json());
}}
async function calculate(){{
  const payload = {{}};
  for (const item of new FormData(document.getElementById('calc')).entries()) payload[item[0]] = item[1];
  const res = await fetch('/api/local-pilot/calculate', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify(payload)}});
  show(await res.json());
}}
function show(payload){{document.getElementById('out').textContent = JSON.stringify(payload,null,2);}}
</script>
</body>
</html>"""
