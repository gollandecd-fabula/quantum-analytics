from __future__ import annotations

from quantum.application._finance_center_shared import *
from quantum.application._finance_center_dialog import FinanceProfileDialog
from quantum.application._finance_center_persistence import (
    managed_source_path,
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
                "FINANCE_PROFILE_INCOMPLETE": "Расчёт заблокирован. Заполните обязательные данные:",
                "XLSX_HEADER_NOT_UNIQUE": "Не удалось однозначно определить заголовки Excel.",
                "PRODUCTS_NOT_FOUND": "В отчёте не найдены товары.",
                "COST_ROWS_NOT_FOUND": "В Excel не найдены заполненные строки себестоимости.",
                "DETAILED_ROWS_NOT_FOUND": "В финансовом отчёте WB не найдены строки операций.",
            }
            base = messages.get(exc.code, exc.code)
            if exc.details:
                base += "\n\n" + "\n".join(f"• {item}" for item in exc.details)
            return base

        def restore_persisted_reports(self) -> None:
            restored = restore_reports(self.project_root, self.config_path)
            if not restored:
                return
            collections: list[tuple[ProductRecord, ...]] = []
            for item in restored:
                row = item.row
                self.reports[row.row_id] = ReportState(row, item.product_records)
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
                if str(report.get("file_sha256") or "").strip().lower() != digest:
                    continue
                if state.row.source_path.is_file() and state.row.status not in {
                    "Ошибка",
                    "Недоступен",
                    "Отменено",
                }:
                    return True
            return False

        def add_reports(self) -> None:
            selected = filedialog.askopenfilenames(
                title="Выберите один или несколько отчётов Wildberries",
                filetypes=[("Excel и ZIP", "*.xlsx *.xlsm *.zip"), ("Все файлы", "*.*")],
            )
            added = 0
            skipped = 0
            for raw_path in selected:
                path = Path(raw_path)
                if not path.is_file():
                    continue
                try:
                    digest = sha256(path.read_bytes()).hexdigest()
                except OSError:
                    continue
                if self._loaded_digest(digest):
                    skipped += 1
                    continue
                self.counter += 1
                row = ImportRow(
                    row_id=f"report-{self.counter}",
                    source_path=path,
                    size_text=str(path.stat().st_size),
                    status="Ожидает",
                    progress="0%",
                    details={
                        "original_source_name": path.name,
                        "selected_file_sha256": digest,
                    },
                )
                self.reports[row.row_id] = ReportState(row)
                self._update_report_row(row)
                self._start_worker(row)
                added += 1
            if selected:
                self.show_page("reports")
            if skipped and not added:
                self.set_status(
                    "Выбранный отчёт уже загружен и доступен для расчёта.",
                    "success",
                )
            elif skipped:
                self.set_status(
                    f"Добавлено: {added}; уже были загружены: {skipped}.",
                    "info",
                )

        def _start_worker(self, row: ImportRow) -> None:
            row.status = "В обработке"
            row.progress = "10%"
            row.comment = "Проверка и локальный импорт запущены."
            self._update_report_row(row)
            self.set_status(f"Обрабатывается: {row.source_path.name}", "info")
            threading.Thread(target=self._worker, args=(row,), daemon=True).start()

        def _worker(self, row: ImportRow) -> None:
            try:
                result = run_import(row.source_path, self.project_root)
                result.row_id = row.row_id
                result.details["original_source_name"] = (
                    row.details.get("original_source_name")
                    or row.source_path.name
                )
                products: tuple[ProductRecord, ...] = ()
                try:
                    products = detect_products_from_xlsx(row.source_path)
                except FinanceProfileError:
                    products = ()
                self.events.put(("done", row.row_id, (result, products)))
            except Exception as exc:  # pragma: no cover - defensive desktop boundary
                row.status = "Ошибка"
                row.progress = "Сбой"
                row.comment = str(exc)
                row.error = type(exc).__name__
                self.events.put(("done", row.row_id, (row, ())))

        def _drain_events(self) -> None:
            changed_profile = False
            changed_reports = False
            while True:
                try:
                    event, row_id, payload = self.events.get_nowait()
                except queue.Empty:
                    break
                if event != "done":
                    continue
                row, products = payload
                state = self.reports.get(row_id)
                if state is None:
                    continue
                original_source = row.source_path
                if isinstance(row.report, dict):
                    managed = managed_source_path(
                        self.project_root,
                        self.config_path,
                        row.report,
                        original_source,
                    )
                    if managed is not None:
                        row.details["original_source_path"] = str(original_source)
                        row.details["managed_source_path"] = str(managed)
                        row.source_path = managed
                state.row = row
                state.product_records = products
                self._update_report_row(row)
                changed_reports = True
                if products:
                    for record in products:
                        self.products[record.product_id] = record
                    collections = [item.product_records for item in self.reports.values() if item.product_records]
                    try:
                        merged = merge_detected_products(collections)
                        self.profile = build_profile(merged, self.profile)
                        changed_profile = True
                    except FinanceProfileError as exc:
                        self.set_status(self.describe_error(exc), "error")
                self.set_status(f"Последний результат: {row.status} · {row.source_path.name}", "success" if row.status == "Готово" else "warning")
            if changed_reports:
                self._persist_report_index()
            if changed_profile:
                self.refresh_finance_summary()
                self.open_finance_profile()
            self.refresh_cards()
            self.refresh_quality()
            self.root_widget.after(150, self._drain_events)

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
            values = (display_name, row.status, row.detected_format, row.progress, row.comment)
            if self.report_tree.exists(row.row_id):
                self.report_tree.item(row.row_id, values=values)
            else:
                self.report_tree.insert("", tk.END, iid=row.row_id, values=values)

        def _selected_report(self) -> ImportRow | None:
            selection = self.report_tree.selection()
            if not selection:
                messagebox.showinfo(APP_TITLE, "Выберите строку отчёта.")
                return None
            state = self.reports.get(selection[0])
            return state.row if state else None

        def repeat_selected(self) -> None:
            row = self._selected_report()
            if row is not None:
                if not row.source_path.is_file():
                    messagebox.showwarning(
                        APP_TITLE,
                        "Сохранённый исходник отчёта недоступен. Выберите файл заново.",
                    )
                    return
                self._start_worker(row)

        def open_selected_result(self) -> None:
            row = self._selected_report()
            if row is None or row.output_path is None or not row.output_path.exists():
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
                "output_path": str(row.output_path) if row.output_path else None,
                "error": row.error,
                "details": row.details,
                "report": row.report,
            }
            text.insert("1.0", json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            text.configure(state=tk.DISABLED)

        def open_finance_profile(self) -> None:
            if not self.profile.groups:
                messagebox.showwarning(APP_TITLE, "Сначала загрузите отчёт WB, содержащий товары и артикулы.")
                return
            FinanceProfileDialog(self, self.profile, self.products)

        def refresh_finance_summary(self) -> None:
            missing = validate_profile(self.profile)
            lines = ["ФИНАНСОВЫЙ ПРОФИЛЬ", ""]
            lines.append(f"Групп: {len(self.profile.groups)}")
            lines.append(f"Налоговая ставка: {self.profile.tax_rate_percent or 'не заполнена'}")
            lines.append(f"Прочие расходы на единицу: {self.profile.other_expense_per_unit or 'не заполнены'}")
            lines.append("")
            for name, group in sorted(self.profile.groups.items()):
                lines.append(f"• {name}: товаров {len(group.product_ids)}, себестоимость {group.cost_per_unit or 'не заполнена'}")
            lines.append("")
            if missing:
                lines.append("РАСЧЁТ ЗАБЛОКИРОВАН")
                lines.extend(f"• {item}" for item in missing)
            else:
                lines.append("Обязательные поля профиля заполнены. Дополнительные данные проверяются при расчёте по фактическому отчёту WB.")
            self._set_text(self.finance_summary, "\n".join(lines))
            self.refresh_cards()


__all__ = [name for name in globals() if not name.startswith("__")]
