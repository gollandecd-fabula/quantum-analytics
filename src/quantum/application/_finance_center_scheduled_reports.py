from __future__ import annotations

from quantum.application._finance_center_shared import *
from quantum.application.scheduled_reports import (
    ScheduledReportError,
    register_windows_task,
    run_scheduled_report,
)


class FinanceCenterScheduledReportsMixin:
    def _set_scheduled_report_busy(self, busy: bool) -> None:
        self.scheduled_report_busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        for name in (
            "weekly_report_button",
            "monthly_report_button",
            "enable_schedule_button",
        ):
            button = getattr(self, name, None)
            if button is not None:
                button.configure(state=state)

    def _launch_scheduled_action(self, action: str) -> None:
        if self.import_queue.is_busy:
            messagebox.showwarning(
                APP_TITLE,
                "Дождитесь завершения импорта отчётов.",
            )
            return
        if getattr(self, "scheduled_report_busy", False):
            messagebox.showwarning(
                APP_TITLE,
                "Дождитесь завершения текущего отчёта по расписанию.",
            )
            return
        self._set_scheduled_report_busy(True)
        labels = {
            "weekly": "недельный отчёт",
            "monthly": "месячный отчёт",
            "register": "регистрацию расписания",
        }
        self.set_status(f"Quantum выполняет {labels[action]}…", "info")
        threading.Thread(
            target=self._scheduled_action_worker,
            args=(action,),
            daemon=True,
        ).start()

    def _scheduled_action_worker(self, action: str) -> None:
        try:
            if action == "register":
                payload: Any = {
                    "task_name": register_windows_task(
                        project_root=self.project_root,
                        config_path=self.config_path,
                        time_of_day="08:00",
                    )
                }
            else:
                payload = run_scheduled_report(
                    project_root=self.project_root,
                    config_path=self.config_path,
                    kind=action,
                )
            self.events.put(("scheduled_report_done", action, payload))
        except ScheduledReportError as exc:
            self.events.put(
                (
                    "scheduled_report_failed",
                    action,
                    {"code": exc.code, "details": exc.details},
                )
            )
        except Exception as exc:
            self.events.put(
                (
                    "scheduled_report_failed",
                    action,
                    {"code": type(exc).__name__, "details": ()},
                )
            )

    def _handle_scheduled_report_event(
        self,
        event: str,
        action: str,
        payload: Any,
    ) -> None:
        self._set_scheduled_report_busy(False)
        if event == "scheduled_report_failed":
            code = str(payload.get("code") or "SCHEDULED_REPORT_FAILED")
            details = tuple(payload.get("details") or ())
            message = "Автоматический отчёт не сформирован: " + code
            if details:
                message += "\n\n" + "\n".join(f"• {item}" for item in details)
            self.set_status(message, "error")
            messagebox.showerror(APP_TITLE, message)
            return
        if action == "register":
            task_name = str(payload.get("task_name") or "Quantum")
            message = (
                "Ежедневная проверка отчётов включена на 08:00 по локальному "
                f"времени Windows. Задача: {task_name}."
            )
            self.set_status(message, "success")
            messagebox.showinfo(APP_TITLE, message)
            return
        package = getattr(payload, "package_path", None)
        period = getattr(payload, "period_key", action)
        status = getattr(payload, "status", "GENERATED")
        calculation_status = getattr(payload, "calculation_status", None)
        message = (
            f"Отчёт {period}: {status}. "
            f"Статус расчёта: {calculation_status or '—'}."
        )
        self.set_status(message, "success")
        if isinstance(package, Path) and package.is_dir():
            _open_path(package)

    def run_weekly_scheduled_report(self) -> None:
        self._launch_scheduled_action("weekly")

    def run_monthly_scheduled_report(self) -> None:
        self._launch_scheduled_action("monthly")

    def enable_scheduled_reports(self) -> None:
        if not messagebox.askyesno(
            APP_TITLE,
            "Включить ежедневную проверку в 08:00?\n\n"
            "Quantum будет формировать предыдущий завершённый недельный и "
            "месячный отчёт, если для периода есть полное подтверждённое "
            "покрытие исходными файлами.",
        ):
            return
        self._launch_scheduled_action("register")

    def open_scheduled_reports_folder(self) -> None:
        path = self.project_root / "output" / "scheduled"
        path.mkdir(parents=True, exist_ok=True)
        _open_path(path)


__all__ = [name for name in globals() if not name.startswith("__")]
