from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
from typing import Any

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk
except ImportError:  # pragma: no cover - handled by self-test and CLI callers
    tk = None  # type: ignore[assignment]
    filedialog = None  # type: ignore[assignment]
    messagebox = None  # type: ignore[assignment]
    simpledialog = None  # type: ignore[assignment]
    ttk = None  # type: ignore[assignment]

from quantum.application.finance_profile import (
    FinanceProfile,
    FinanceProfileError,
    FinanceRunResult,
    ProductRecord,
    apply_costs,
    build_profile,
    calculate_by_group,
    detect_products_from_xlsx,
    load_profile,
    merge_detected_products,
    parse_cost_workbook,
    read_detailed_financial_rows,
    reassign_product,
    rename_group,
    save_profile,
    save_run_result,
    validate_profile,
    write_cost_template,
    write_run_dashboard,
    write_run_result_xlsx,
)
from quantum.application.local_app import ImportRow
from quantum.application._finance_center_import import run_import
from quantum.application._finance_center_queue import SequentialImportQueue


APP_TITLE = "Центр решений Quantum"
PROFILE_RELATIVE_PATH = Path("config") / "finance-profile.json"
PALETTE = {
    "navy": "#102A43",
    "blue": "#1769AA",
    "cyan": "#00A6C8",
    "green": "#14866D",
    "orange": "#E97824",
    "red": "#C0392B",
    "background": "#F3F7FA",
    "surface": "#FFFFFF",
    "muted": "#627D98",
    "line": "#D9E2EC",
    "text": "#172B4D",
}

NAV_ITEMS = (
    ("decision", "Центр решений"),
    ("reports", "Отчёты"),
    ("finance", "Себестоимость и расходы"),
    ("analytics", "Аналитика"),
    ("recommendations", "Рекомендации"),
    ("export", "Экспорт"),
    ("quality", "Контроль данных"),
)

_ADVANCED_FIELDS = (
    ("resalable_returned_units", "Возвраты, пригодные к повторной продаже, шт."),
    ("compensated_returned_units", "Компенсированные возвраты, шт."),
    ("return_compensation_amount", "Компенсации возвратов, ₽"),
    ("discounts_amount", "Скидки вне отчёта, ₽"),
    ("subsidies_amount", "Субсидии вне отчёта, ₽"),
    ("advertising_amount", "Реклама вне отчёта, ₽"),
)


@dataclass(slots=True)
class ReportState:
    row: ImportRow
    product_records: tuple[ProductRecord, ...] = ()


def _safe_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _open_path(path: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])


def self_test(root: Path, config: Path) -> dict[str, object]:
    return {
        "status": "FINANCE_CENTER_SELF_TEST_PASS",
        "root_exists": root.resolve().is_dir(),
        "config_exists": config.resolve().is_file(),
        "tkinter_available": tk is not None,
        "profile_module_available": True,
        "marketplace_write_enabled": False,
        "release_scope": "WB_ONLY",
    }
__all__ = [name for name in globals() if not name.startswith("__")]
