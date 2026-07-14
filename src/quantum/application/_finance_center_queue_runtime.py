from __future__ import annotations

from quantum.application._finance_center_shared import *
from quantum.application._finance_center_persistence import managed_source_path
from quantum.application._finance_schema_review import (
    SchemaReviewPreview,
    build_schema_review_preview,
)


class FinanceCenterQueueRuntimeMixin:
    def _refresh_queue_controls(self) -> None:
        busy = self.import_queue.is_busy
        for name in (
            "decision_add_button",
            "reports_add_button",
            "reports_repeat_button",
        ):
            button = getattr(self, name, None)
            if button is not None:
                button.configure(state=tk.DISABLED if busy else tk.NORMAL)
        for name in ("decision_cancel_button", "reports_cancel_button"):
            button = getattr(self, name, None)
            if button is not None:
                button.configure(state=tk.NORMAL if busy else tk.DISABLED)

    @staticmethod
    def _source_digest(path: Path) -> str:
        digest = sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    def _confirm_authority(self, count: int) -> bool:
        return messagebox.askyesno(
            APP_TITLE,
            "Подтверждение полномочий\n\n"
            f"Выбрано файлов: {count}.\n\n"
            "Подтвердите, что вы имеете право обрабатывать эти отчёты "
            "и содержащиеся в них коммерческие данные.\n\n"
            "Выбор файла сам по себе не считается подтверждением.",
        )

    def _review_source(
        self,
        path: Path,
        *,
        authority_attested: bool,
    ) -> SchemaReviewPreview | None:
        if not authority_attested:
            return None
        try:
            preview = build_schema_review_preview(path, self.config_path)
        except FinanceProfileError as exc:
            messagebox.showerror(
                APP_TITLE,
                "Файл не добавлен: предварительная проверка схемы "
                "завершилась ошибкой.\n\n"
                + self.describe_error(exc),
            )
            return None
        if preview.requires_schema_review and not messagebox.askyesno(
            APP_TITLE,
            "Проверка схемы отчёта\n\n"
            + preview.confirmation_text()
            + "\n\nПодтвердить эту схему?",
        ):
            return None
        return preview

    def add_reports(self) -> None:
        if self.import_queue.is_busy:
            messagebox.showwarning(
                APP_TITLE,
                "Дождитесь завершения текущей очереди или нажмите "
                "«Остановить очередь».",
            )
            return
        selected = filedialog.askopenfilenames(
            title="Выберите один или несколько отчётов Wildberries",
            filetypes=[
                ("Excel и ZIP", "*.xlsx *.xlsm *.zip"),
                ("Все файлы", "*.*"),
            ],
        )
        if not selected:
            return
        if not self._confirm_authority(len(selected)):
            self.set_status(
                "Партия не добавлена: полномочия не подтверждены.",
                "warning",
            )
            return

        added = 0
        duplicates = 0
        rejected = 0
        for raw_path in selected:
            path = Path(raw_path)
            preview = self._review_source(
                path,
                authority_attested=True,
            )
            if preview is None:
                rejected += 1
                continue
            digest = preview.file_sha256
            if self._loaded_digest(digest):
                duplicates += 1
                continue
            row_id = f"report-{self.counter + 1}"
            if not self.import_queue.add(row_id, path):
                duplicates += 1
                continue
            self.counter += 1
            row = ImportRow(
                row_id=row_id,
                source_path=path,
                size_text=str(preview.file_size_bytes),
                status="В очереди",
                progress="0%",
                comment=(
                    "Полномочия подтверждены; схема проверена. "
                    "Ожидает последовательной обработки."
                    if preview.requires_schema_review
                    else "Полномочия подтверждены; ожидает обработки."
                ),
                details={
                    "original_source_name": path.name,
                    "selected_file_sha256": digest,
                    "authority_attested": True,
                    "schema_reviewed": preview.requires_schema_review,
                    "schema_preview": preview.to_dict(),
                },
            )
            self.reports[row_id] = ReportState(row)
            self._update_report_row(row)
            added += 1

        self.show_page("reports")
        if rejected:
            self.set_status(
                f"Не добавлено после проверки: {rejected}.",
                "warning",
            )
        elif duplicates:
            self.set_status(
                f"Пропущено уже загруженных файлов: {duplicates}.",
                "info",
            )
        if added:
            self.set_status(
                f"После явной проверки в очередь добавлено: {added}.",
                "info",
            )
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
        row.comment = (
            "Проверка и локальный импорт запущены. "
            "Остальные файлы ожидают в очереди."
        )
        self._update_report_row(row)
        self.set_status(
            f"Обрабатывается: {row.source_path.name} · "
            f"ожидает: {self.import_queue.pending_count}",
            "info",
        )
        self._refresh_queue_controls()
        threading.Thread(
            target=self._worker,
            args=(row,),
            daemon=True,
        ).start()

    def _register_active_process(
        self,
        process: subprocess.Popen[object] | None,
    ) -> None:
        with self.process_lock:
            self.active_process = process

    def _worker(self, row: ImportRow) -> None:
        original_source = row.source_path
        selected_digest = str(
            row.details.get("selected_file_sha256") or ""
        ).strip().lower()
        authority_attested = row.details.get("authority_attested") is True
        schema_reviewed = row.details.get("schema_reviewed") is True
        try:
            result = run_import(
                original_source,
                self.project_root,
                authority_attested=authority_attested,
                schema_reviewed=schema_reviewed,
                cancel_event=self.cancel_event,
                process_callback=self._register_active_process,
            )
            result.row_id = row.row_id
            result.details.update(
                {
                    "original_source_name": row.details.get(
                        "original_source_name",
                        original_source.name,
                    ),
                    "selected_file_sha256": selected_digest or None,
                    "authority_attested": authority_attested,
                    "schema_reviewed": schema_reviewed,
                    "schema_preview": row.details.get("schema_preview"),
                }
            )
            products: tuple[ProductRecord, ...] = ()
            if result.status not in {"Отменено", "Ошибка"}:
                report_digest = ""
                if isinstance(result.report, dict):
                    report_digest = str(
                        result.report.get("file_sha256") or ""
                    ).strip().lower()
                if not selected_digest or report_digest != selected_digest:
                    result.status = "Ошибка"
                    result.progress = "Сбой"
                    result.error = "SOURCE_FILE_CHANGED_DURING_IMPORT"
                    result.comment = (
                        "Файл изменился между preview и завершением импорта. "
                        "Результат отклонён; выберите отчёт заново."
                    )
                elif not isinstance(result.report, dict):
                    result.status = "Ошибка"
                    result.progress = "Сбой"
                    result.error = "IMPORT_REPORT_MISSING"
                    result.comment = "Импорт не вернул проверяемый результат."
                else:
                    managed = managed_source_path(
                        self.project_root,
                        self.config_path,
                        result.report,
                        None,
                    )
                    if managed is None:
                        result.status = "Ошибка"
                        result.progress = "Сбой"
                        result.error = "MANAGED_SOURCE_UNAVAILABLE"
                        result.comment = (
                            "Импорт завершён, но проверенная локальная копия "
                            "исходного отчёта не найдена."
                        )
                    else:
                        result.source_path = managed
                        result.details["managed_source_path"] = str(managed)
                        try:
                            products = detect_products_from_xlsx(managed)
                        except FinanceProfileError as exc:
                            result.details["product_detection_error"] = exc.code
                        except Exception as exc:
                            result.details["product_detection_error"] = (
                                type(exc).__name__
                            )
            self.events.put(("done", row.row_id, (result, products)))
        except Exception as exc:
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
            self._persist_report_index()
            if products:
                for record in products:
                    self.products[record.product_id] = record
                collections = [
                    item.product_records
                    for item in self.reports.values()
                    if item.product_records
                ]
                try:
                    self.profile = build_profile(
                        merge_detected_products(collections),
                        self.profile,
                    )
                    self.profile_changed_pending = True
                except FinanceProfileError as exc:
                    self.set_status(self.describe_error(exc), "error")
            kind = "success" if row.status == "Готово" else "warning"
            display_name = str(
                row.details.get("original_source_name")
                or row.source_path.name
            )
            self.set_status(
                f"Последний результат: {row.status} · {display_name}",
                kind,
            )
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
            self.reports[active_id].row.comment = (
                "Остановка активного процесса…"
            )
            self._update_report_row(self.reports[active_id].row)
        if not silent:
            self.set_status(
                "Очередь остановлена. Активный процесс завершается безопасно.",
                "warning",
            )
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
            self.set_status(
                "Quantum завершает активный процесс…",
                "warning",
            )
            return
        self.root_widget.destroy()

    def repeat_selected(self) -> None:
        row = self._selected_report()
        if row is None:
            return
        if self.import_queue.is_busy:
            messagebox.showwarning(
                APP_TITLE,
                "Повторный запуск заблокирован до завершения текущей очереди.",
            )
            return
        if not row.source_path.is_file():
            messagebox.showwarning(
                APP_TITLE,
                "Сохранённый исходник отчёта недоступен. Выберите файл заново.",
            )
            return
        if not self._confirm_authority(1):
            self.set_status(
                "Повторный запуск отменён: полномочия не подтверждены.",
                "warning",
            )
            return
        preview = self._review_source(
            row.source_path,
            authority_attested=True,
        )
        if preview is None:
            self.set_status(
                "Повторный запуск отменён на этапе проверки схемы.",
                "warning",
            )
            return
        if not self.import_queue.enqueue_existing(
            row.row_id,
            row.source_path,
        ):
            messagebox.showwarning(
                APP_TITLE,
                "Этот отчёт уже находится в обработке или очереди.",
            )
            return
        row.details.update(
            {
                "selected_file_sha256": preview.file_sha256,
                "authority_attested": True,
                "schema_reviewed": preview.requires_schema_review,
                "schema_preview": preview.to_dict(),
            }
        )
        row.status = "В очереди"
        row.progress = "0%"
        row.comment = (
            "Полномочия и схема повторно подтверждены; ожидает обработки."
        )
        row.error = None
        self._update_report_row(row)
        self._start_next_if_idle()
