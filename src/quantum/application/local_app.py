from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:  # pragma: no cover - handled by CLI/self-test callers
    tk = None  # type: ignore[assignment]
    filedialog = None  # type: ignore[assignment]
    messagebox = None  # type: ignore[assignment]
    ttk = None  # type: ignore[assignment]


APP_TITLE = "Центр решений Quantum — загрузка отчётов"
READY_CONFIG_NAMES = (
    "config/default-home-local.json",
    "config/production.local.json",
    "config/default-production.json",
)
SUCCESS_STATUSES = {
    "ADMISSION_COMPLETE",
    "PILOT_RUN_COMPLETE",
    "CALCULATED_RECONCILIATION_PENDING",
    "ROUTE_XLSX",
}
PARTIAL_STATUSES = {
    "SOURCE_BRIDGE_COMPLETE",
    "SOURCE_BRIDGE_PARTIAL",
    "ACCEPTED_PARTIAL",
    "ACCEPTED_UNPARSED",
    "ADMISSION_REJECTED",
    "CALCULATION_BLOCKED",
    "SOURCE_BRIDGE_BLOCKED",
}
ERROR_STATUSES = {
    "ERROR",
    "QUARANTINED_SECURITY",
    "QUARANTINED_CORRUPTED",
}


@dataclass
class ImportRow:
    row_id: str
    source_path: Path
    size_text: str
    output_path: Path | None = None
    status: str = "Ожидает"
    detected_format: str = "—"
    progress: str = "—"
    comment: str = "—"
    stdout: str = ""
    stderr: str = ""
    report: dict[str, Any] | None = None
    error: str | None = None
    raw_status: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


def _human_size(size_bytes: int) -> str:
    value = float(size_bytes)
    for suffix in ("Б", "КБ", "МБ", "ГБ"):
        if value < 1024 or suffix == "ГБ":
            if suffix == "Б":
                return f"{int(value)} {suffix}"
            return f"{value:.1f} {suffix}"
        value /= 1024
    return f"{size_bytes} Б"


def _safe_json_load(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _find_project_root(start: Path | None = None) -> Path:
    if start is None:
        start = Path(__file__).resolve()
    candidates = [start, *start.parents]
    env_root = os.environ.get("QUANTUM_HOME_LOCAL_ROOT")
    if env_root:
        candidates.insert(0, Path(env_root))
    for candidate in candidates:
        root = candidate if candidate.is_dir() else candidate.parent
        if (root / "scripts" / "import_source.ps1").is_file():
            return root
        if (root / "scripts" / "windows" / "import_source.ps1").is_file():
            return root
    return Path.cwd().resolve()


def _import_script(root: Path) -> Path:
    installed = root / "scripts" / "import_source.ps1"
    if installed.is_file():
        return installed
    source_tree = root / "scripts" / "windows" / "import_source.ps1"
    if source_tree.is_file():
        return source_tree
    raise FileNotFoundError(f"Сценарий import_source.ps1 не найден в папке {root}")


def _is_ready_config(path: Path) -> bool:
    payload = _safe_json_load(path)
    if payload is None:
        return False
    status = payload.get("configuration_status")
    if status is not None and status != "READY":
        return False
    mode = payload.get("execution_mode", "FULL")
    if mode == "ADMISSION_ONLY":
        return True
    if mode != "FULL":
        return False
    finance = payload.get("finance_request")
    if not isinstance(finance, dict):
        return False
    return finance.get("replace_with_a_valid_versioned_finance_request") is not True


def _find_ready_config(root: Path) -> Path | None:
    for relative in READY_CONFIG_NAMES:
        candidate = root / relative
        if candidate.is_file() and _is_ready_config(candidate):
            return candidate
    return None


def _collect_reason_codes(value: Any) -> list[str]:
    result: list[str] = []
    if isinstance(value, str) and value.strip():
        result.append(value.strip())
    elif isinstance(value, list):
        for item in value:
            result.extend(_collect_reason_codes(item))
    elif isinstance(value, dict):
        for key in (
            "reason_codes",
            "finance_request_reason_codes",
            "finance_request_reason_code",
            "admission_diagnostics",
            "diagnostics",
            "limitations",
        ):
            if key in value:
                result.extend(_collect_reason_codes(value[key]))
    return result


def _first_text(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _source_bridge(report: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {}
    value = report.get("source_bridge")
    return value if isinstance(value, dict) else {}


def summarize_report(report: dict[str, Any] | None, return_code: int) -> tuple[str, str, str, str]:
    if not isinstance(report, dict):
        return "Ошибка", "—", "—", "Импорт не создал JSON-результат."

    bridge = _source_bridge(report)
    raw_status = _first_text(bridge.get("status"), report.get("status")) or "UNKNOWN"
    detected_format = _first_text(
        bridge.get("source_type"),
        report.get("detected_format"),
        bridge.get("detected_format"),
        report.get("route"),
    ) or "—"

    reason_codes = _collect_reason_codes(report)
    bridge_reasons = _collect_reason_codes(bridge)
    all_reasons = []
    for item in [*bridge_reasons, *reason_codes]:
        if item not in all_reasons:
            all_reasons.append(item)

    finance_state = _first_text(bridge.get("finance_request_state"))
    if raw_status in ERROR_STATUSES:
        status = "Ошибка"
    elif raw_status in PARTIAL_STATUSES or finance_state == "BLOCKED":
        status = "Частично"
    elif raw_status in SUCCESS_STATUSES and return_code == 0:
        status = "Готово"
    elif return_code != 0:
        status = "Ошибка"
    else:
        status = "Готово"

    if status == "Частично" and detected_format == "WB_SUPPLIER_GOODS":
        comment = "Отчёт supplier-goods загружен. Финансовый расчёт заблокирован: нужен событийный финансовый отчёт WB."
    elif all_reasons:
        comment = "; ".join(all_reasons[:6])
    elif status == "Готово":
        comment = "Импорт завершён."
    else:
        comment = "Проверьте подробности результата."

    return status, detected_format, raw_status, comment


def run_import(source_path: Path, root: Path | None = None) -> ImportRow:
    root = root or _find_project_root()
    row = ImportRow(
        row_id="runtime",
        source_path=source_path,
        size_text=_human_size(source_path.stat().st_size),
    )
    output_dir = root / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"pilot_gui_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
    row.output_path = output_path

    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(_import_script(root)),
        "-File",
        str(source_path),
        "-StorageRoot",
        str(root / "data"),
        "-Output",
        str(output_path),
    ]
    config = _find_ready_config(root)
    if config is not None:
        command.extend(["-Config", str(config)])

    completed = subprocess.run(
        command,
        cwd=str(root),
        text=True,
        capture_output=False,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
    )
    row.stdout = "Интерактивное подтверждение полномочий и проверка схемы выполнены в консоли Quantum."
    row.stderr = ""
    report = _safe_json_load(output_path)
    row.report = report
    row.status, row.detected_format, row.raw_status, row.comment = summarize_report(
        report,
        completed.returncode,
    )
    row.progress = "100%" if row.status != "Ошибка" else "Сбой"
    if completed.returncode != 0 and row.status != "Частично":
        row.error = f"Код процесса: {completed.returncode}"
    row.details = {
        "command": command,
        "return_code": completed.returncode,
        "config": str(config) if config else None,
        "output_path": str(output_path),
    }
    return row


class QuantumLocalApp:
    def __init__(self, root_widget: tk.Tk) -> None:  # type: ignore[name-defined]
        self.root_widget = root_widget
        self.project_root = _find_project_root()
        self.rows: dict[str, ImportRow] = {}
        self.counter = 0
        self.events: queue.Queue[tuple[str, str, Any]] = queue.Queue()
        self.root_widget.title(APP_TITLE)
        self.root_widget.geometry("1180x720")
        self._build_ui()
        self.root_widget.after(150, self._drain_events)

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root_widget, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(frame, text="Центр решений Quantum", font=("Segoe UI", 18, "bold"))
        title.pack(anchor=tk.W)
        subtitle = ttk.Label(
            frame,
            text="HOME_LOCAL · АВТОНОМНО · отчёты выбираются и обрабатываются внутри проекта",
        )
        subtitle.pack(anchor=tk.W, pady=(0, 8))

        button_bar = ttk.Frame(frame)
        button_bar.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(button_bar, text="Добавить отчёты", command=self.add_reports).pack(side=tk.LEFT)
        ttk.Button(button_bar, text="Повторить", command=self.repeat_selected).pack(side=tk.LEFT, padx=6)
        ttk.Button(button_bar, text="Открыть результат", command=self.open_selected_result).pack(side=tk.LEFT)
        ttk.Button(button_bar, text="Подробности", command=self.show_selected_details).pack(side=tk.LEFT, padx=6)
        ttk.Button(button_bar, text="Удалить", command=self.delete_selected).pack(side=tk.LEFT)

        table_frame = ttk.Frame(frame)
        table_frame.pack(fill=tk.BOTH, expand=True)
        columns = ("file", "size", "status", "format", "progress", "comment")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings")
        headings = {
            "file": ("Файл", 380, tk.W),
            "size": ("Размер", 90, tk.E),
            "status": ("Статус", 120, tk.W),
            "format": ("Формат", 190, tk.W),
            "progress": ("Прогресс", 90, tk.W),
            "comment": ("Комментарий", 560, tk.W),
        }
        for name, (label, width, anchor) in headings.items():
            self.tree.heading(name, text=label)
            self.tree.column(name, width=width, minwidth=70, stretch=True, anchor=anchor)
        yscroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        xscroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        self.tree.bind("<Double-1>", lambda _event: self.show_selected_details())

        status_bar = ttk.Frame(frame)
        status_bar.pack(fill=tk.X, pady=(8, 0))
        self.status_label = ttk.Label(status_bar, text="Готово. Файлы не отправляются во внешние сервисы.")
        self.status_label.pack(side=tk.LEFT)

    def _insert_or_update(self, row: ImportRow) -> None:
        values = (
            str(row.source_path),
            row.size_text,
            row.status,
            row.detected_format,
            row.progress,
            row.comment,
        )
        if self.tree.exists(row.row_id):
            self.tree.item(row.row_id, values=values)
        else:
            self.tree.insert("", tk.END, iid=row.row_id, values=values)
        self.rows[row.row_id] = row

    def _selected_row(self) -> ImportRow | None:
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo(APP_TITLE, "Выберите строку отчёта.")
            return None
        return self.rows.get(selection[0])

    def add_reports(self) -> None:
        selected = filedialog.askopenfilenames(title="Выберите один или несколько отчётов")
        for raw_path in selected:
            source = Path(raw_path)
            if not source.is_file():
                continue
            self.counter += 1
            row = ImportRow(
                row_id=f"row-{self.counter}",
                source_path=source,
                size_text=_human_size(source.stat().st_size),
                progress="0%",
            )
            self._insert_or_update(row)
            self._start_worker(row)

    def _start_worker(self, row: ImportRow) -> None:
        row.status = "В обработке"
        row.progress = "10%"
        row.comment = "Импорт запущен."
        self._insert_or_update(row)
        thread = threading.Thread(target=self._worker, args=(row,), daemon=True)
        thread.start()

    def _worker(self, row: ImportRow) -> None:
        try:
            result = run_import(row.source_path, self.project_root)
            result.row_id = row.row_id
            self.events.put(("done", row.row_id, result))
        except Exception as exc:  # pragma: no cover - defensive GUI boundary
            row.status = "Ошибка"
            row.progress = "Сбой"
            row.comment = str(exc)
            row.error = type(exc).__name__
            self.events.put(("done", row.row_id, row))

    def _drain_events(self) -> None:
        while True:
            try:
                event, _row_id, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if event == "done" and isinstance(payload, ImportRow):
                self._insert_or_update(payload)
                self.status_label.configure(text=f"Последний результат: {payload.status} · {payload.source_path.name}")
        self.root_widget.after(150, self._drain_events)

    def repeat_selected(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        self._start_worker(row)

    def open_selected_result(self) -> None:
        row = self._selected_row()
        if row is None or row.output_path is None:
            return
        target = row.output_path
        if not target.exists():
            messagebox.showwarning(APP_TITLE, f"Файл результата не найден:\n{target}")
            return
        if sys.platform.startswith("win"):
            os.startfile(str(target))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(target)])

    def show_selected_details(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        window = tk.Toplevel(self.root_widget)
        window.title(f"Подробности — {row.source_path.name}")
        window.geometry("980x680")
        text = tk.Text(window, wrap=tk.NONE)
        yscroll = ttk.Scrollbar(window, orient=tk.VERTICAL, command=text.yview)
        xscroll = ttk.Scrollbar(window, orient=tk.HORIZONTAL, command=text.xview)
        text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        window.rowconfigure(0, weight=1)
        window.columnconfigure(0, weight=1)
        payload = {
            "file": str(row.source_path),
            "status": row.status,
            "raw_status": row.raw_status,
            "format": row.detected_format,
            "comment": row.comment,
            "output_path": str(row.output_path) if row.output_path else None,
            "error": row.error,
            "details": row.details,
            "report": row.report,
            "stdout": row.stdout,
            "stderr": row.stderr,
        }
        text.insert("1.0", json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        text.configure(state=tk.DISABLED)

    def delete_selected(self) -> None:
        for row_id in self.tree.selection():
            self.tree.delete(row_id)
            self.rows.pop(row_id, None)


def main() -> int:
    if tk is None:
        print(json.dumps({"status": "ERROR", "reason_code": "TKINTER_NOT_AVAILABLE"}, ensure_ascii=False))
        return 2
    root_widget = tk.Tk()
    QuantumLocalApp(root_widget)
    root_widget.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
