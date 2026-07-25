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
    TAX_BASE_OPTIONS,
    apply_costs,
    backup_corrupt_profile,
    build_profile,
    calculate_by_group,
    calculate_metric_groups,
    detect_products_from_any_file,
    detect_products_from_xlsx,
    load_profile,
    merge_detected_products,
    parse_cost_workbook,
    reassign_product,
    rename_group,
    save_profile,
    save_run_result,
    validate_profile,
    write_cost_template,
    write_run_dashboard,
    write_run_result_xlsx,
)
from quantum.application._finance_verified_rows import (
    read_detailed_financial_rows,
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
    ("analytics", "Аналитика"),
    ("finance", "Финансы"),
    ("products", "Товары"),
    ("advertising", "Реклама"),
    ("supply", "Склад и поставки"),
    ("competitors", "Конкуренты"),
    ("seo", "SEO"),
    ("ai", "Аналитик AI"),
    ("reports", "Отчёты"),
    ("settings", "Настройки"),
)

_ADVANCED_FIELDS = (
    (
        "resalable_returned_units",
        "Возвраты, пригодные к повторной продаже, шт.",
    ),
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


_MAX_CONFIG_JSON_BYTES = 1024 * 1024


def _safe_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as stream:
            payload = stream.read(_MAX_CONFIG_JSON_BYTES + 1)
        if len(payload) > _MAX_CONFIG_JSON_BYTES:
            return {}
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _open_path(path: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(
            ["open" if sys.platform == "darwin" else "xdg-open", str(path)]
        )


def self_test(root: Path, config: Path) -> dict[str, object]:
    from quantum.application._finance_center_self_test import (
        run_finance_center_self_test,
    )

    result = run_finance_center_self_test(root, config)
    checks = result.get("checks")
    if isinstance(checks, dict):
        checks["tkinter_available"] = tk is not None
        previous_status = result.get("status")
        passed = all(value is True for value in checks.values())
        configuration_required = (
            previous_status
            == "FINANCE_CENTER_SELF_TEST_CONFIGURATION_REQUIRED"
            and tk is not None
            and all(
                value is True
                for name, value in checks.items()
                if name != "config_valid"
            )
        )
        result["status"] = (
            "FINANCE_CENTER_SELF_TEST_PASS"
            if passed
            else (
                "FINANCE_CENTER_SELF_TEST_CONFIGURATION_REQUIRED"
                if configuration_required
                else "FINANCE_CENTER_SELF_TEST_FAILED"
            )
        )
    return result


def bounded_window_geometry(
    screen_width: int,
    screen_height: int,
    preferred_width: int,
    preferred_height: int,
    minimum_width: int,
    minimum_height: int,
    *,
    margin: int = 32,
) -> tuple[str, tuple[int, int]]:
    """Return centered geometry that never exceeds the usable screen."""
    width_limit = max(320, int(screen_width) - (margin * 2))
    height_limit = max(240, int(screen_height) - (margin * 2))
    width = min(max(320, int(preferred_width)), width_limit)
    height = min(max(240, int(preferred_height)), height_limit)
    x = max(0, (int(screen_width) - width) // 2)
    y = max(0, (int(screen_height) - height) // 2)
    minimum = (
        min(max(320, int(minimum_width)), width),
        min(max(240, int(minimum_height)), height),
    )
    return f"{width}x{height}+{x}+{y}", minimum


def apply_bounded_window_geometry(
    window: Any,
    preferred_width: int,
    preferred_height: int,
    minimum_width: int,
    minimum_height: int,
) -> None:
    geometry, minimum = bounded_window_geometry(
        window.winfo_screenwidth(),
        window.winfo_screenheight(),
        preferred_width,
        preferred_height,
        minimum_width,
        minimum_height,
    )
    window.geometry(geometry)
    window.minsize(*minimum)


__all__ = [name for name in globals() if not name.startswith("__")]
