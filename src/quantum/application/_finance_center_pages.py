from __future__ import annotations

from quantum.application._finance_center_shared import *

class FinanceCenterPagesMixin:
        def _page(self, key: str) -> ttk.Frame:
            frame = ttk.Frame(self.page_host)
            self.pages[key] = frame
            return frame

        def _build_decision_page(self) -> None:
            page = self._page("decision")
            banner = tk.Frame(page, bg=PALETTE["blue"], height=145)
            banner.pack(fill=tk.X, pady=(0, 16))
            tk.Label(banner, text="Единый центр решений", font=("Segoe UI", 22, "bold"), fg="white", bg=PALETTE["blue"]).pack(anchor=tk.W, padx=24, pady=(22, 3))
            tk.Label(banner, text="Загрузите отчёты WB, подтвердите группы и финансовые параметры, затем запустите расчёт.", font=("Segoe UI", 11), fg="#E7F4FB", bg=PALETTE["blue"]).pack(anchor=tk.W, padx=24)
            action_bar = tk.Frame(banner, bg=PALETTE["blue"])
            action_bar.pack(anchor=tk.W, padx=24, pady=14)
            self.decision_add_button = ttk.Button(action_bar, text="Добавить отчёты", style="Success.TButton", command=self.add_reports)
            self.decision_add_button.pack(side=tk.LEFT)
            self.decision_cancel_button = ttk.Button(action_bar, text="Остановить очередь", command=self.cancel_queue, state=tk.DISABLED)
            self.decision_cancel_button.pack(side=tk.LEFT, padx=8)
            ttk.Button(action_bar, text="Настроить финансовый профиль", command=self.open_finance_profile).pack(side=tk.LEFT, padx=8)
            ttk.Button(action_bar, text="Рассчитать прибыль", style="Primary.TButton", command=self.calculate_finance).pack(side=tk.LEFT)
            cards = ttk.Frame(page)
            cards.pack(fill=tk.X)
            self.decision_cards: dict[str, tk.Label] = {}
            for index, (key, title, accent) in enumerate(
                (
                    ("reports", "Загружено отчётов", PALETTE["cyan"]),
                    ("groups", "Товарных групп", PALETTE["orange"]),
                    ("profile", "Финансовый профиль", PALETTE["green"]),
                    ("calculation", "Последний расчёт", PALETTE["blue"]),
                )
            ):
                card = tk.Frame(cards, bg=PALETTE["surface"], highlightbackground=PALETTE["line"], highlightthickness=1)
                card.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 6, 0 if index == 3 else 6))
                cards.columnconfigure(index, weight=1)
                tk.Frame(card, bg=accent, height=5).pack(fill=tk.X)
                tk.Label(card, text=title, font=("Segoe UI", 10, "bold"), fg=PALETTE["muted"], bg=PALETTE["surface"]).pack(anchor=tk.W, padx=15, pady=(14, 4))
                value_label = tk.Label(card, text="—", font=("Segoe UI", 20, "bold"), fg=PALETTE["navy"], bg=PALETTE["surface"])
                value_label.pack(anchor=tk.W, padx=15, pady=(0, 16))
                self.decision_cards[key] = value_label
            self.decision_text = tk.Text(page, height=14, wrap=tk.WORD, bd=0, bg=PALETTE["surface"], fg=PALETTE["text"], font=("Segoe UI", 10), padx=16, pady=14)
            self.decision_text.pack(fill=tk.BOTH, expand=True, pady=(16, 0))
            self._set_text(self.decision_text, "Quantum ожидает отчёты Wildberries. Финансовые выводы не формируются без обязательных данных.")

        def _build_reports_page(self) -> None:
            page = self._page("reports")
            controls = ttk.Frame(page)
            controls.pack(fill=tk.X, pady=(0, 10))
            self.reports_add_button = ttk.Button(controls, text="Добавить отчёты", style="Success.TButton", command=self.add_reports)
            self.reports_add_button.pack(side=tk.LEFT)
            self.reports_repeat_button = ttk.Button(controls, text="Повторить выбранный", command=self.repeat_selected)
            self.reports_repeat_button.pack(side=tk.LEFT, padx=7)
            self.reports_cancel_button = ttk.Button(controls, text="Остановить очередь", command=self.cancel_queue, state=tk.DISABLED)
            self.reports_cancel_button.pack(side=tk.LEFT, padx=(0, 7))
            ttk.Button(controls, text="Открыть результат", command=self.open_selected_result).pack(side=tk.LEFT)
            ttk.Button(controls, text="Подробности", command=self.show_selected_details).pack(side=tk.LEFT, padx=7)
            columns = ("file", "status", "format", "progress", "comment")
            self.report_tree = ttk.Treeview(page, columns=columns, show="headings")
            headings = {
                "file": ("Файл", 350),
                "status": ("Статус", 120),
                "format": ("Формат", 190),
                "progress": ("Прогресс", 90),
                "comment": ("Комментарий", 530),
            }
            for key, (label, width) in headings.items():
                self.report_tree.heading(key, text=label)
                self.report_tree.column(key, width=width, minwidth=80, stretch=True)
            yscroll = ttk.Scrollbar(page, orient=tk.VERTICAL, command=self.report_tree.yview)
            self.report_tree.configure(yscrollcommand=yscroll.set)
            self.report_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            yscroll.pack(side=tk.RIGHT, fill=tk.Y)
            self.report_tree.bind("<Double-1>", lambda _event: self.show_selected_details())

        def _build_finance_page(self) -> None:
            page = self._page("finance")
            actions = ttk.Frame(page)
            actions.pack(fill=tk.X, pady=(0, 12))
            ttk.Button(actions, text="Открыть финансовый профиль", style="Primary.TButton", command=self.open_finance_profile).pack(side=tk.LEFT)
            ttk.Button(actions, text="Рассчитать прибыль", style="Success.TButton", command=self.calculate_finance).pack(side=tk.LEFT, padx=8)
            self.finance_summary = tk.Text(page, wrap=tk.WORD, bd=0, bg=PALETTE["surface"], fg=PALETTE["text"], font=("Segoe UI", 10), padx=18, pady=16)
            self.finance_summary.pack(fill=tk.BOTH, expand=True)

        def _build_analytics_page(self) -> None:
            page = self._page("analytics")
            self.analytics_text = tk.Text(page, wrap=tk.WORD, bd=0, bg=PALETTE["surface"], fg=PALETTE["text"], font=("Consolas", 10), padx=18, pady=16)
            self.analytics_text.pack(fill=tk.BOTH, expand=True)
            self._set_text(self.analytics_text, "Аналитика появится после подтверждённого финансового расчёта.")

        def _build_recommendations_page(self) -> None:
            page = self._page("recommendations")
            self.recommendations_text = tk.Text(page, wrap=tk.WORD, bd=0, bg=PALETTE["surface"], fg=PALETTE["text"], font=("Segoe UI", 10), padx=18, pady=16)
            self.recommendations_text.pack(fill=tk.BOTH, expand=True)
            self._set_text(self.recommendations_text, "Рекомендации по прибыли заблокированы до полного расчёта. Предварительные гипотезы будут явно помечены.")

        def _build_export_page(self) -> None:
            page = self._page("export")
            ttk.Label(page, text="Файлы последнего расчёта", font=("Segoe UI", 14, "bold")).pack(anchor=tk.W, pady=(0, 10))
            self.export_list = tk.Listbox(page, font=("Segoe UI", 10), bg=PALETTE["surface"], fg=PALETTE["text"], bd=0, highlightthickness=1, highlightbackground=PALETTE["line"])
            self.export_list.pack(fill=tk.BOTH, expand=True)
            ttk.Button(page, text="Открыть выбранный файл", command=self.open_export).pack(anchor=tk.E, pady=10)

        def _build_quality_page(self) -> None:
            page = self._page("quality")
            self.quality_text = tk.Text(page, wrap=tk.WORD, bd=0, bg=PALETTE["surface"], fg=PALETTE["text"], font=("Segoe UI", 10), padx=18, pady=16)
            self.quality_text.pack(fill=tk.BOTH, expand=True)
            self.refresh_quality()

        def show_page(self, key: str) -> None:
            for frame in self.pages.values():
                frame.pack_forget()
            self.pages[key].pack(fill=tk.BOTH, expand=True)
            titles = dict(NAV_ITEMS)
            self.page_title.configure(text=titles[key])
            for page_key, button in self.nav_buttons.items():
                button.configure(bg=PALETTE["blue"] if page_key == key else PALETTE["navy"], fg="white" if page_key == key else "#D9EAF7")

        def set_status(self, text: str, kind: str = "info") -> None:
            colors = {"success": PALETTE["green"], "warning": PALETTE["orange"], "error": PALETTE["red"], "info": PALETTE["blue"]}
            labels = {"success": "ГОТОВО", "warning": "ВНИМАНИЕ", "error": "ОШИБКА", "info": "РАБОТА"}
            self.status_text.configure(text=text)
            self.status_badge.configure(text=labels.get(kind, "РАБОТА"), bg=colors.get(kind, PALETTE["blue"]))
__all__ = [name for name in globals() if not name.startswith("__")]
