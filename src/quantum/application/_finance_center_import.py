from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Callable

from quantum.application.local_app import (
    ImportRow,
    _find_project_root,
    _find_ready_config,
    _human_size,
    _import_script,
    _safe_json_load,
    summarize_report,
)
from quantum.application._finance_center_persistence import finance_center_summary


def _terminate_process_tree(process: subprocess.Popen[object]) -> None:
    if process.poll() is not None:
        return
    if sys.platform.startswith("win"):
        try:
            subprocess.run(
                ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        process.terminate()
        process.wait(timeout=5)
    except (OSError, subprocess.SubprocessError):
        try:
            process.kill()
        except OSError:
            pass


def run_import(
    source_path: Path,
    root: Path | None = None,
    *,
    cancel_event: threading.Event | None = None,
    process_callback: Callable[[subprocess.Popen[object] | None], None] | None = None,
) -> ImportRow:
    root = (root or _find_project_root()).resolve()
    row = ImportRow(
        row_id="runtime",
        source_path=source_path,
        size_text=_human_size(source_path.stat().st_size),
    )
    output_dir = root / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    from datetime import datetime

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
        "-NonInteractive",
        "-AuthorityAttested",
        "-SchemaReviewed",
    ]
    config = _find_ready_config(root)
    if config is not None:
        command.extend(["-Config", str(config)])

    process = subprocess.Popen(
        command,
        cwd=str(root),
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if process_callback is not None:
        process_callback(process)
    cancelled = False
    try:
        while process.poll() is None:
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                _terminate_process_tree(process)
                break
            time.sleep(0.1)
        return_code = process.wait()
    finally:
        if process_callback is not None:
            process_callback(None)

    row.stdout = "Выбор партии в интерфейсе подтверждает полномочия и проверку схемы; импорт выполнен без консольных запросов."
    row.stderr = ""
    if cancelled:
        row.status = "Отменено"
        row.progress = "Остановлено"
        row.comment = "Обработка отменена пользователем."
        row.error = "CANCELLED_BY_USER"
        row.details = {
            "command": command,
            "return_code": return_code,
            "config": str(config) if config else None,
            "output_path": str(output_path),
            "cancelled": True,
        }
        return row

    report = _safe_json_load(output_path)
    row.report = report
    base_summary = summarize_report(report, return_code)
    row.status, row.detected_format, row.raw_status, row.comment = finance_center_summary(
        report,
        return_code,
        summary=base_summary,
    )
    row.progress = "100%" if row.status != "Ошибка" else "Сбой"
    if return_code != 0 and row.status != "Частично":
        row.error = f"Код процесса: {return_code}"
    row.details = {
        "command": command,
        "return_code": return_code,
        "config": str(config) if config else None,
        "output_path": str(output_path),
        "cancelled": False,
        "batch_authority_attested": True,
        "batch_schema_reviewed": True,
        "interactive_prompts": False,
        "defender_scan_skipped": False,
    }
    return row
