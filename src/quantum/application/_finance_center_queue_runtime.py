from __future__ import annotations

from quantum.application._finance_center_shared import *


class FinanceCenterQueueRuntimeMixin:
    def _refresh_queue_controls(self) -> None:
        busy = self.import_queue.is_busy
        for name in ("decision_add_button", "reports_add_button", "reports_repeat_button"):
            button = getattr(self, name, None)
            if button is not None:
                button.configure(state=tk.DISABLED if busy else tk.NORMAL)
        for name in ("decision_cancel_button", "reports_cancel_button"):
            button = getattr(self, name, None)
            if button is not None:
                button.configure(state=tk.NORMAL if busy else tk.DISABLED)

    def add_reports(self) -> None:
        if self.import_queue.is_busy:
            messagebox.showwarning(APP_TITLE, "Дождитесь завершения текущей очереди или нажмите «Остановить очередь».")
            return
        selected = filedialog.askopenfilenames(
            title="Выберите один или несколько отчётов Wildberries",
            filetypes=[("Excel и ZIP", "*.xlsx *.xlsm *.zip"), ("Все файлы", "*.*")],
        )
        added = 0
        duplicates = 0
        for raw_path in selected:
            path = Path(raw_path)
            if not path.is_file():
                continue
            row_id = f"report-{self.counter + 1}"
            if not self.import_queue.add(row_id, path):
                duplicates += 1
                continue
            self.counter += 1
            row = ImportRow(
                row_id=row_id,
                source_path=path,
                size_text=str(path.stat().st_size),
                status="В очереди",
                progress="0%",
                comment="Ожидает последовательной обработки.",
            )
            self.reports[row_id] = ReportState(row)
            self._update_report_row(row)
            added += 1
        if selected:
            self.show_page("reports")
        if duplicates:
            self.set_status(f"Пропущено дубликатов: {duplicates}.", "warning")
        if added:
            self.set_status(f"Партия подтверждена выбором файлов. В очередь добавлено: {added}.", "info")
            self._start_next_if_idle()
        self._refresh_queue_controls()

    def _start_next_if_idle(self) -> None:
        if self.closing:
            return
        row_id = self.import_queue.start_next()
        if row_id is None:
            self._refresh_queue_controls()
            return
        state = self.reports.get(row_id)
        if state is None:
            self.import_queue.complete(row_id)
            self._start_next_if_idle()
            return
        row = state.row
        self.cancel_event.clear()
        row.status = "В обработке"
        row.progress = "10%"
        row.comment = "Проверка и локальный импорт запущены. Остальные файлы ожидают в очереди."
        self._update_report_row(row)
        self.set_status(
            f"Обрабатывается: {row.source_path.name} · ожидает: {self.import_queue.pending_count}",
            "info",
        )
        self._refresh_queue_controls()
        threading.Thread(target=self._worker, args=(row,), daemon=True).start()

    def _register_active_process(self, process: subprocess.Popen[object] | None) -> None:
        with self.process_lock:
            self.active_process = process

    def _worker(self, row: ImportRow) -> None:
        try:
            result = run_import(
                row.source_path,
                self.project_root,
                cancel_event=self.cancel_event,
                process_callback=self._register_active_process,
            )
            result.row_id = row.row_id
            products: tuple[ProductRecord, ...] = ()
            if result.status not in {"Отменено", "Ошибка"}:
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
        while True:
            try:
                event, row_id, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if event != "done":
                continue
            row, products = payload
            self.import_queue.complete(row_id)
            state = self.reports.get(row_id)
            if state is None:
                self._start_next_if_idle()
                continue
            state.row = row
            state.product_records = products
            self._update_report_row(row)
            if products:
                for record in products:
                    self.products[record.product_id] = record
                collections = [item.product_records for item in self.reports.values() if item.product_records]
                try:
                    self.profile = build_profile(merge_detected_products(collections), self.profile)
                    self.profile_changed_pending = True
                except FinanceProfileError as exc:
                    self.set_status(self.describe_error(exc), "error")
            kind = "success" if row.status == "Готово" else "warning"
            self.set_status(f"Последний результат: {row.status} · {row.source_path.name}", kind)
            self._start_next_if_idle()

        if not self.import_queue.is_busy and self.profile_changed_pending:
            self.profile_changed_pending = False
            self.refresh_finance_summary()
            if not self.closing:
                self.open_finance_profile()
        self._refresh_queue_controls()
        self.refresh_cards()
        self.refresh_quality()
        if self.closing and not self.import_queue.is_busy:
            self.root_widget.destroy()
            return
        self.root_widget.after(150, self._drain_events)

    def cancel_queue(self, silent: bool = False) -> None:
        if not self.import_queue.is_busy:
            return
        self.cancel_event.set()
        for row_id in self.import_queue.cancel_pending():
            state = self.reports.get(row_id)
            if state is None:
                continue
            row = state.row
            row.status = "Отменено"
            row.progress = "Остановлено"
            row.comment = "Удалено из очереди пользователем."
            row.error = "CANCELLED_BY_USER"
            self._update_report_row(row)
        active_id = self.import_queue.active
        if active_id is not None and active_id in self.reports:
            self.reports[active_id].row.comment = "Остановка активного процесса…"
            self._update_report_row(self.reports[active_id].row)
        if not silent:
            self.set_status("Очередь остановлена. Активный процесс завершается безопасно.", "warning")
        self._refresh_queue_controls()

    def request_close(self) -> None:
        if self.import_queue.is_busy and not messagebox.askyesno(
            APP_TITLE,
            "Идёт обработка отчёта. Остановить очередь и закрыть Quantum?",
        ):
            return
        self.closing = True
        if self.import_queue.is_busy:
            self.cancel_queue(silent=True)
            self.set_status("Quantum завершает активный процесс…", "warning")
            return
        self.root_widget.destroy()

    def repeat_selected(self) -> None:
        row = self._selected_report()
        if row is None:
            return
        if self.import_queue.is_busy:
            messagebox.showwarning(APP_TITLE, "Повторный запуск заблокирован до завершения текущей очереди.")
            return
        if not self.import_queue.requeue(row.row_id):
            messagebox.showwarning(APP_TITLE, "Этот отчёт уже находится в обработке или очереди.")
            return
        row.status = "В очереди"
        row.progress = "0%"
        row.comment = "Ожидает повторной последовательной обработки."
        row.error = None
        self._update_report_row(row)
        self._start_next_if_idle()
