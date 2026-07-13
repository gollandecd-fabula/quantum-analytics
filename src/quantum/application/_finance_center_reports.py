from __future__ import annotations

from quantum.application._finance_center_shared import *
from quantum.application._finance_center_dialog import FinanceProfileDialog

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

        def add_reports(self) -> None:
            selected = filedialog.askopenfilenames(
                title="Выберите один или несколько отчётов Wildberries",
                filetypes=[("Excel и ZIP", "*.xlsx *.xlsm *.zip"), ("Все файлы", "*.*")],
            )
            for raw_path in selected:
                path = Path(raw_path)
                if not path.is_file():
                    continue
                self.counter += 1
                row = ImportRow(
                    row_id=f"report-{self.counter}",
                    source_path=path,
                    size_text=str(path.stat().st_size),
                    status="Ожидает",
                    progress="0%",
                )
                self.reports[row.row_id] = ReportState(row)
                self._update_report_row(row)
                self._start_worker(row)
            if selected:
                self.show_page("reports")

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
                state.row = row
                state.product_records = products
                self._update_report_row(row)
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
            if changed_profile:
                self.refresh_finance_summary()
                self.open_finance_profile()
            self.refresh_cards()
            self.refresh_quality()
            self.root_widget.after(150, self._drain_events)

        def _update_report_row(self, row: ImportRow) -> None:
            values = (str(row.source_path), row.status, row.detected_format, row.progress, row.comment)
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
