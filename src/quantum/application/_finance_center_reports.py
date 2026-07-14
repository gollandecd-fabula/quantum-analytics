from __future__ import annotations

from quantum.application._finance_center_shared import *
from quantum.application._finance_center_dialog import FinanceProfileDialog
from quantum.application._finance_center_persistence import (
    restore_reports,
    save_report_index,
)


class FinanceCenterReportsMixin:
    def _set_text(self, widget: tk.Text, value: str) -> None:
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert("1.0", value)
        widget.configure(state=tk.DISABLED)

    def describe_error(self, exc: FinanceProfileError) -> str:
        messages = {
            "FINANCE_PROFILE_INCOMPLETE": (
                "Расчёт заблокирован. Заполните обязательные данные:"
            ),
            "XLSX_HEADER_NOT_UNIQUE": (
                "Не удалось однозначно определить заголовки Excel."
            ),
            "PRODUCTS_NOT_FOUND": "В отчёте не найдены товары.",
            "COST_ROWS_NOT_FOUND": (
                "В Excel не найдены заполненные строки себестоимости."
            ),
            "DETAILED_ROWS_NOT_FOUND": (
                "В финансовом отчёте WB не найдены строки операций."
            ),
        }
        base = messages.get(exc.code, exc.code)
        if exc.details:
            base += "\n\n" + "\n".join(
                f"• {item}" for item in exc.details
            )
        return base

    def restore_persisted_reports(self) -> None:
        restored = restore_reports(self.project_root, self.config_path)
        if not restored:
            return
        collections: list[tuple[ProductRecord, ...]] = []
        for item in restored:
            row = item.row
            self.reports[row.row_id] = ReportState(
                row,
                item.product_records,
            )
            self._update_report_row(row)
            if item.product_records:
                collections.append(item.product_records)
                for record in item.product_records:
                    self.products[record.product_id] = record
        self.counter = max(self.counter, len(self.reports))
        if collections:
            try:
                merged = merge_detected_products(collections)
                self.profile = build_profile(merged, self.profile)
            except FinanceProfileError as exc:
                self.set_status(self.describe_error(exc), "error")
        self._persist_report_index()
        available = sum(
            state.row.source_path.is_file()
            for state in self.reports.values()
        )
        self.set_status(
            f"Восстановлено отчётов: {len(self.reports)}; "
            f"исходники доступны: {available}.",
            "success" if available else "warning",
        )

    def _persist_report_index(self) -> None:
        try:
            save_report_index(
                self.project_root,
                (state.row for state in self.reports.values()),
            )
        except (OSError, TypeError, ValueError) as exc:
            self.set_status(
                "Не удалось сохранить индекс загруженных отчётов: "
                + type(exc).__name__,
                "warning",
            )

    def _loaded_digest(self, digest: str) -> bool:
        for state in self.reports.values():
            report = state.row.report
            if not isinstance(report, dict):
                continue
            if (
                str(report.get("file_sha256") or "")
                .strip()
                .lower()
                != digest
            ):
                continue
            if state.row.source_path.is_file() and state.row.status not in {
                "Ошибка",
                "Недоступен",
                "Отменено",
            }:
                return True
        return False

    def _update_report_row(self, row: ImportRow) -> None:
        display_name = str(
            row.details.get("original_source_name")
            or (
                row.report.get("sanitized_filename")
                if isinstance(row.report, dict)
                else None
            )
            or row.source_path
        )
        values = (
            display_name,
            row.status,
            row.detected_format,
            row.progress,
            row.comment,
        )
        if self.report_tree.exists(row.row_id):
            self.report_tree.item(row.row_id, values=values)
        else:
            self.report_tree.insert(
                "",
                tk.END,
                iid=row.row_id,
                values=values,
            )

    def _selected_report(self) -> ImportRow | None:
        selection = self.report_tree.selection()
        if not selection:
            messagebox.showinfo(APP_TITLE, "Выберите строку отчёта.")
            return None
        state = self.reports.get(selection[0])
        return state.row if state else None

    def open_selected_result(self) -> None:
        row = self._selected_report()
        if (
            row is None
            or row.output_path is None
            or not row.output_path.exists()
        ):
            return
        _open_path(row.output_path)

    def show_selected_details(self) -> None:
        row = self._selected_report()
        if row is None:
            return
        window = tk.Toplevel(self.root_widget)
        window.title(f"Подробности — {row.source_path.name}")
        window.geometry("980x680")
        text = tk.Text(window, wrap=tk.NONE, font=("Consolas", 9))
        text.pack(fill=tk.BOTH, expand=True)
        payload = {
            "file": str(row.source_path),
            "status": row.status,
            "raw_status": row.raw_status,
            "format": row.detected_format,
            "comment": row.comment,
            "output_path": (
                str(row.output_path) if row.output_path else None
            ),
            "error": row.error,
            "details": row.details,
            "report": row.report,
        }
        text.insert(
            "1.0",
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
        )
        text.configure(state=tk.DISABLED)

    def open_finance_profile(self) -> None:
        if not self.profile.groups:
            messagebox.showwarning(
                APP_TITLE,
                "Сначала загрузите отчёт WB, содержащий товары и артикулы.",
            )
            return
        FinanceProfileDialog(self, self.profile, self.products)

    def refresh_finance_summary(self) -> None:
        missing = validate_profile(self.profile)
        lines = ["ФИНАНСОВЫЙ ПРОФИЛЬ", ""]
        lines.append(f"Групп: {len(self.profile.groups)}")
        lines.append(
            "Налоговая ставка: "
            f"{self.profile.tax_rate_percent or 'не заполнена'}"
        )
        lines.append(
            "Налоговая база: "
            + TAX_BASE_OPTIONS.get(
                self.profile.tax_base_metric_id or "",
                "не выбрана",
            )
        )
        lines.append(
            "Прочие расходы на единицу: "
            f"{self.profile.other_expense_per_unit or 'не заполнены'}"
        )
        lines.append("")
        for name, group in sorted(self.profile.groups.items()):
            lines.append(
                f"• {name}: товаров {len(group.product_ids)}, "
                f"себестоимость {group.cost_per_unit or 'не заполнена'}"
            )
        lines.append("")
        if missing:
            lines.append("РАСЧЁТ ЗАБЛОКИРОВАН")
            lines.extend(f"• {item}" for item in missing)
        else:
            lines.append(
                "Обязательные поля профиля заполнены. Дополнительные данные "
                "проверяются при расчёте по фактическому отчёту WB."
            )
        self._set_text(self.finance_summary, "\n".join(lines))
        self.refresh_cards()


__all__ = [name for name in globals() if not name.startswith("__")]
