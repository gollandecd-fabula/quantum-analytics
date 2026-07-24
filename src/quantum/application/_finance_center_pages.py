from __future__ import annotations

from decimal import Decimal, InvalidOperation

from quantum.application._finance_center_shared import *
from quantum.application._finance_profile_financial_rows import (
    PERIOD_TAX_GROUP,
    UNALLOCATED_SERVICE_GROUP,
)


class FinanceCenterPagesMixin:
    def _page(self, key: str) -> ttk.Frame:
        frame = ttk.Frame(self.page_host)
        self.pages[key] = frame
        return frame

    def _surface(
        self,
        parent: tk.Misc,
        *,
        border: str | None = None,
    ) -> tk.Frame:
        return tk.Frame(
            parent,
            bg=PALETTE["surface"],
            highlightbackground=border or PALETTE["line"],
            highlightthickness=1,
        )

    def _build_decision_page(self) -> None:
        page = self._page("decision")
        actions = tk.Frame(page, bg=PALETTE["background"])
        actions.pack(fill=tk.X, pady=(0, 12))
        self.decision_add_button = ttk.Button(
            actions,
            text="Загрузить отчёты WB",
            style="Success.TButton",
            command=self.add_reports,
        )
        self.decision_add_button.pack(side=tk.LEFT)
        self.decision_cancel_button = ttk.Button(
            actions,
            text="Остановить очередь",
            command=self.cancel_queue,
            state=tk.DISABLED,
        )
        self.decision_cancel_button.pack(side=tk.LEFT, padx=8)
        ttk.Button(
            actions,
            text="Финансовый профиль",
            command=self.open_finance_profile,
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(
            actions,
            text="Рассчитать",
            style="Primary.TButton",
            command=self.calculate_finance,
        ).pack(side=tk.LEFT)

        decision_grid = tk.Frame(page, bg=PALETTE["background"])
        decision_grid.pack(fill=tk.X)
        self.decision_cards: dict[str, dict[str, tk.Label]] = {}
        definitions = (
            ("problem", "ПРОБЛЕМА", PALETTE["red"]),
            ("risk", "РИСК", PALETTE["orange"]),
            ("opportunity", "ВОЗМОЖНОСТЬ", PALETTE["green"]),
            ("anomaly", "АНОМАЛИЯ", PALETTE["cyan"]),
        )
        for index, (key, category, accent) in enumerate(definitions):
            card = self._surface(decision_grid, border=accent)
            card.grid(
                row=0,
                column=index,
                sticky="nsew",
                padx=(0 if index == 0 else 5, 0 if index == 3 else 5),
            )
            decision_grid.columnconfigure(index, weight=1, uniform="decision")
            tk.Frame(card, bg=accent, height=5).pack(fill=tk.X)
            badge = tk.Label(
                card,
                text=category,
                font=("Segoe UI", 8, "bold"),
                fg=accent,
                bg=PALETTE["surface"],
            )
            badge.pack(anchor=tk.W, padx=13, pady=(10, 2))
            title = tk.Label(
                card,
                text="Ожидает данные",
                font=("Segoe UI", 11, "bold"),
                fg=PALETTE["navy"],
                bg=PALETTE["surface"],
                justify=tk.LEFT,
                anchor="w",
                wraplength=240,
            )
            title.pack(fill=tk.X, padx=13, pady=(0, 5))
            detail_labels: dict[str, tk.Label] = {"title": title}
            for field, caption in (
                ("impact", "Влияние"),
                ("cause", "Причина"),
                ("action", "Действие"),
                ("effect", "Эффект"),
                ("confidence", "Уверенность"),
            ):
                label = tk.Label(
                    card,
                    text=f"{caption}: —",
                    font=("Segoe UI", 8),
                    fg=PALETTE["text"],
                    bg=PALETTE["surface"],
                    justify=tk.LEFT,
                    anchor="w",
                    wraplength=240,
                )
                label.pack(fill=tk.X, padx=13, pady=1)
                detail_labels[field] = label
            tk.Button(
                card,
                text="Открыть",
                relief=tk.FLAT,
                bd=0,
                font=("Segoe UI", 8, "bold"),
                fg=PALETTE["blue"],
                bg=PALETTE["surface"],
                activeforeground=PALETTE["cyan"],
                activebackground=PALETTE["surface"],
                command=lambda page_key=(
                    "finance" if key in {"problem", "risk"} else "analytics"
                ): self.show_page(page_key),
            ).pack(anchor=tk.E, padx=10, pady=(6, 9))
            self.decision_cards[key] = detail_labels

        kpi_grid = tk.Frame(page, bg=PALETTE["background"])
        kpi_grid.pack(fill=tk.X, pady=(12, 0))
        self.kpi_cards: dict[str, tk.Label] = {}
        for index, (key, label, unit) in enumerate(
            (
                ("revenue", "Доход WB", "₽"),
                ("profit", "Чистая прибыль", "₽"),
                ("margin", "Маржинальность", "%"),
                ("orders", "Продано", "шт."),
            )
        ):
            card = self._surface(kpi_grid)
            card.grid(
                row=0,
                column=index,
                sticky="nsew",
                padx=(0 if index == 0 else 5, 0 if index == 3 else 5),
            )
            kpi_grid.columnconfigure(index, weight=1, uniform="kpi")
            tk.Label(
                card,
                text=label,
                font=("Segoe UI", 9, "bold"),
                fg=PALETTE["muted"],
                bg=PALETTE["surface"],
            ).pack(anchor=tk.W, padx=14, pady=(10, 2))
            value = tk.Label(
                card,
                text="—",
                font=("Segoe UI", 19, "bold"),
                fg=PALETTE["navy"],
                bg=PALETTE["surface"],
            )
            value.pack(anchor=tk.W, padx=14, pady=(0, 2))
            tk.Label(
                card,
                text=unit,
                font=("Segoe UI", 8),
                fg=PALETTE["muted"],
                bg=PALETTE["surface"],
            ).pack(anchor=tk.W, padx=14, pady=(0, 10))
            self.kpi_cards[key] = value

        lower = tk.Frame(page, bg=PALETTE["background"])
        lower.pack(fill=tk.BOTH, expand=True, pady=(12, 0))
        lower.columnconfigure(0, weight=3)
        lower.columnconfigure(1, weight=2)
        lower.rowconfigure(0, weight=1)
        lower.rowconfigure(1, weight=1)

        top_products = self._surface(lower)
        top_products.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(0, 6))
        tk.Label(
            top_products,
            text="Топ товарных групп",
            font=("Segoe UI", 11, "bold"),
            fg=PALETTE["navy"],
            bg=PALETTE["surface"],
        ).pack(anchor=tk.W, padx=14, pady=(11, 4))
        self.top_products_text = tk.Text(
            top_products,
            height=5,
            wrap=tk.WORD,
            bd=0,
            bg=PALETTE["surface"],
            fg=PALETTE["text"],
            font=("Segoe UI", 9),
            padx=14,
            pady=5,
        )
        self.top_products_text.pack(fill=tk.BOTH, expand=True)

        forecast = self._surface(lower)
        forecast.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=(0, 6))
        tk.Label(
            forecast,
            text="Прогноз спроса",
            font=("Segoe UI", 11, "bold"),
            fg=PALETTE["navy"],
            bg=PALETTE["surface"],
        ).pack(anchor=tk.W, padx=14, pady=(11, 4))
        self.forecast_text = tk.Text(
            forecast,
            height=5,
            wrap=tk.WORD,
            bd=0,
            bg=PALETTE["surface"],
            fg=PALETTE["text"],
            font=("Segoe UI", 9),
            padx=14,
            pady=5,
        )
        self.forecast_text.pack(fill=tk.BOTH, expand=True)

        feed = self._surface(lower)
        feed.grid(row=1, column=0, sticky="nsew", padx=(0, 6), pady=(6, 0))
        tk.Label(
            feed,
            text="Лента решений",
            font=("Segoe UI", 11, "bold"),
            fg=PALETTE["navy"],
            bg=PALETTE["surface"],
        ).pack(anchor=tk.W, padx=14, pady=(11, 4))
        self.decision_text = tk.Text(
            feed,
            height=5,
            wrap=tk.WORD,
            bd=0,
            bg=PALETTE["surface"],
            fg=PALETTE["text"],
            font=("Segoe UI", 9),
            padx=14,
            pady=5,
        )
        self.decision_text.pack(fill=tk.BOTH, expand=True)

        alerts = self._surface(lower)
        alerts.grid(row=1, column=1, sticky="nsew", padx=(6, 0), pady=(6, 0))
        tk.Label(
            alerts,
            text="Предупреждения",
            font=("Segoe UI", 11, "bold"),
            fg=PALETTE["navy"],
            bg=PALETTE["surface"],
        ).pack(anchor=tk.W, padx=14, pady=(11, 4))
        self.alerts_text = tk.Text(
            alerts,
            height=5,
            wrap=tk.WORD,
            bd=0,
            bg=PALETTE["surface"],
            fg=PALETTE["text"],
            font=("Segoe UI", 9),
            padx=14,
            pady=5,
        )
        self.alerts_text.pack(fill=tk.BOTH, expand=True)

        self._set_text(
            self.decision_text,
            "Quantum ожидает отчёты Wildberries. Решения не формируются без обязательных данных.",
        )
        self._set_text(self.top_products_text, "Нет подтверждённых данных.")
        self._set_text(
            self.forecast_text,
            "Прогноз заблокирован: требуется временной ряд за несколько периодов.",
        )
        self._set_text(self.alerts_text, "• Финансовый расчёт ещё не выполнен.")

    def _build_reports_page(self) -> None:
        page = self._page("reports")
        controls = ttk.Frame(page)
        controls.pack(fill=tk.X, pady=(0, 10))
        self.reports_add_button = ttk.Button(
            controls,
            text="Выбрать и запустить отчёты",
            style="Success.TButton",
            command=self.add_reports,
        )
        self.reports_add_button.pack(side=tk.LEFT)
        self.reports_repeat_button = ttk.Button(
            controls,
            text="Повторить выбранный",
            command=self.repeat_selected,
        )
        self.reports_repeat_button.pack(side=tk.LEFT, padx=7)
        self.reports_cancel_button = ttk.Button(
            controls,
            text="Остановить очередь",
            command=self.cancel_queue,
            state=tk.DISABLED,
        )
        self.reports_cancel_button.pack(side=tk.LEFT, padx=(0, 7))
        ttk.Button(
            controls,
            text="Открыть результат",
            command=self.open_selected_result,
        ).pack(side=tk.LEFT)
        ttk.Button(
            controls,
            text="Подробности",
            command=self.show_selected_details,
        ).pack(side=tk.LEFT, padx=7)
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
        yscroll = ttk.Scrollbar(
            page,
            orient=tk.VERTICAL,
            command=self.report_tree.yview,
        )
        self.report_tree.configure(yscrollcommand=yscroll.set)
        self.report_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.report_tree.bind(
            "<Double-1>",
            lambda _event: self.show_selected_details(),
        )

    def _build_finance_page(self) -> None:
        page = self._page("finance")
        actions = ttk.Frame(page)
        actions.pack(fill=tk.X, pady=(0, 12))
        ttk.Button(
            actions,
            text="Открыть финансовый профиль",
            style="Primary.TButton",
            command=self.open_finance_profile,
        ).pack(side=tk.LEFT)
        ttk.Button(
            actions,
            text="Рассчитать прибыль",
            style="Success.TButton",
            command=self.calculate_finance,
        ).pack(side=tk.LEFT, padx=8)
        self.finance_summary = tk.Text(
            page,
            wrap=tk.WORD,
            bd=0,
            bg=PALETTE["surface"],
            fg=PALETTE["text"],
            font=("Segoe UI", 10),
            padx=18,
            pady=16,
        )
        self.finance_summary.pack(fill=tk.BOTH, expand=True)

    def _build_analytics_page(self) -> None:
        page = self._page("analytics")
        self.analytics_text = tk.Text(
            page,
            wrap=tk.WORD,
            bd=0,
            bg=PALETTE["surface"],
            fg=PALETTE["text"],
            font=("Consolas", 10),
            padx=18,
            pady=16,
        )
        self.analytics_text.pack(fill=tk.BOTH, expand=True)
        self._set_text(
            self.analytics_text,
            "Аналитика появится после подтверждённого финансового расчёта.",
        )

    def _text_page(self, key: str, title: str) -> tk.Text:
        page = self._page(key)
        surface = self._surface(page)
        surface.pack(fill=tk.BOTH, expand=True)
        tk.Label(
            surface,
            text=title,
            font=("Segoe UI", 14, "bold"),
            fg=PALETTE["navy"],
            bg=PALETTE["surface"],
        ).pack(anchor=tk.W, padx=18, pady=(16, 6))
        text = tk.Text(
            surface,
            wrap=tk.WORD,
            bd=0,
            bg=PALETTE["surface"],
            fg=PALETTE["text"],
            font=("Segoe UI", 10),
            padx=18,
            pady=10,
        )
        text.pack(fill=tk.BOTH, expand=True)
        return text

    def _build_products_page(self) -> None:
        self.products_text = self._text_page("products", "Товары и группы")

    def _build_advertising_page(self) -> None:
        self.advertising_text = self._text_page(
            "advertising",
            "Реклама и её влияние на прибыль",
        )

    def _build_supply_page(self) -> None:
        self.supply_text = self._text_page(
            "supply",
            "Склад и поставки",
        )

    def _build_competitors_page(self) -> None:
        self.competitors_text = self._text_page(
            "competitors",
            "Конкуренты",
        )

    def _build_seo_page(self) -> None:
        self.seo_text = self._text_page("seo", "SEO")

    def _build_ai_page(self) -> None:
        page = self._page("ai")
        self.recommendations_text = tk.Text(
            page,
            wrap=tk.WORD,
            bd=0,
            bg=PALETTE["surface"],
            fg=PALETTE["text"],
            font=("Segoe UI", 10),
            padx=18,
            pady=16,
        )
        self.recommendations_text.pack(fill=tk.BOTH, expand=True)
        self._set_text(
            self.recommendations_text,
            "Аналитик AI работает только с подтверждёнными локальными расчётами. "
            "Рекомендации не выполняются автоматически.",
        )

    def _build_settings_page(self) -> None:
        page = self._page("settings")
        controls = self._surface(page)
        controls.pack(fill=tk.X, pady=(0, 12))
        tk.Label(
            controls,
            text="Локальные настройки Quantum",
            font=("Segoe UI", 14, "bold"),
            fg=PALETTE["navy"],
            bg=PALETTE["surface"],
        ).pack(anchor=tk.W, padx=18, pady=(16, 8))
        buttons = tk.Frame(controls, bg=PALETTE["surface"])
        buttons.pack(anchor=tk.W, padx=18, pady=(0, 16))
        ttk.Button(
            buttons,
            text="Финансовый профиль",
            command=self.open_finance_profile,
        ).pack(side=tk.LEFT)
        ttk.Button(
            buttons,
            text="Контроль данных",
            command=lambda: self.show_page("quality"),
        ).pack(side=tk.LEFT, padx=8)
        ttk.Button(
            buttons,
            text="Экспорт",
            command=lambda: self.show_page("export"),
        ).pack(side=tk.LEFT)
        self.settings_text = self._text_page_body(page)

    def _text_page_body(self, page: ttk.Frame) -> tk.Text:
        text = tk.Text(
            page,
            wrap=tk.WORD,
            bd=0,
            bg=PALETTE["surface"],
            fg=PALETTE["text"],
            font=("Segoe UI", 10),
            padx=18,
            pady=16,
        )
        text.pack(fill=tk.BOTH, expand=True)
        return text

    def _build_export_page(self) -> None:
        page = self._page("export")
        ttk.Label(
            page,
            text="Файлы последнего расчёта",
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor=tk.W, pady=(0, 10))
        self.export_list = tk.Listbox(
            page,
            font=("Segoe UI", 10),
            bg=PALETTE["surface"],
            fg=PALETTE["text"],
            bd=0,
            highlightthickness=1,
            highlightbackground=PALETTE["line"],
        )
        self.export_list.pack(fill=tk.BOTH, expand=True)
        ttk.Button(
            page,
            text="Открыть выбранный файл",
            command=self.open_export,
        ).pack(anchor=tk.E, pady=10)

    def _build_quality_page(self) -> None:
        page = self._page("quality")
        self.quality_text = tk.Text(
            page,
            wrap=tk.WORD,
            bd=0,
            bg=PALETTE["surface"],
            fg=PALETTE["text"],
            font=("Segoe UI", 10),
            padx=18,
            pady=16,
        )
        self.quality_text.pack(fill=tk.BOTH, expand=True)
        self.refresh_quality()

    @staticmethod
    def _decimal_metric(value: object) -> Decimal | None:
        try:
            result = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
        return result if result.is_finite() else None

    def _group_profit_rows(self) -> list[tuple[str, Decimal]]:
        rows: list[tuple[str, Decimal]] = []
        if self.current_result is None:
            return rows
        for item in self.current_result.group_results:
            if (
                item.state != "VALID"
                or not item.calculation
                or item.group_name in {PERIOD_TAX_GROUP, UNALLOCATED_SERVICE_GROUP}
            ):
                continue
            metrics = item.calculation.get("results")
            metric = (
                metrics.get("net_profit_amount")
                if isinstance(metrics, dict)
                else None
            )
            value = (
                self._decimal_metric(metric.get("value"))
                if isinstance(metric, dict)
                else None
            )
            if value is not None:
                rows.append((item.group_name, value))
        return rows

    def _set_decision_card(
        self,
        key: str,
        *,
        title: str,
        impact: str,
        cause: str,
        action: str,
        effect: str,
        confidence: str,
    ) -> None:
        fields = self.decision_cards[key]
        fields["title"].configure(text=title)
        fields["impact"].configure(text="Влияние: " + impact)
        fields["cause"].configure(text="Причина: " + cause)
        fields["action"].configure(text="Действие: " + action)
        fields["effect"].configure(text="Эффект: " + effect)
        fields["confidence"].configure(text="Уверенность: " + confidence)

    def refresh_decision_center(self) -> None:
        missing = validate_profile(self.profile)
        result = self.current_result
        profits = self._group_profit_rows()
        negative = sorted((row for row in profits if row[1] < 0), key=lambda row: row[1])
        positive = sorted((row for row in profits if row[1] > 0), key=lambda row: row[1], reverse=True)

        if result is None:
            self._set_decision_card(
                "problem",
                title="Нет финансового расчёта",
                impact="прибыль не подтверждена",
                cause="не загружен детализированный отчёт WB",
                action="загрузить отчёт и заполнить профиль",
                effect="появится проверяемый финансовый результат",
                confidence="высокая",
            )
        elif result.status != "CALCULATED":
            self._set_decision_card(
                "problem",
                title="Расчёт заблокирован",
                impact="управленческие выводы запрещены",
                cause=(result.missing_inputs[0] if result.missing_inputs else "неполные данные"),
                action="устранить первичную причину блокировки",
                effect="расчёт станет воспроизводимым",
                confidence="высокая",
            )
        elif negative:
            name, value = negative[0]
            self._set_decision_card(
                "problem",
                title=f"Убыточная группа: {name}",
                impact=f"{value:.2f} ₽ до налога",
                cause="себестоимость, логистика, возвраты или реклама выше дохода",
                action="проверить структуру расходов и цену",
                effect="минимум выйти на безубыточность",
                confidence="высокая по факту убытка",
            )
        else:
            self._set_decision_card(
                "problem",
                title="Подтверждённых убытков нет",
                impact="нет выявленного отрицательного результата",
                cause="расчёт по активным группам неотрицательный",
                action="контролировать новые периоды",
                effect="сохранить управляемость прибыли",
                confidence="средняя без временного ряда",
            )

        risk_reason = (
            missing[0]
            if missing
            else "налоговый режим и контрольные суммы требуют подтверждения пользователя"
        )
        self._set_decision_card(
            "risk",
            title="Риск неполных исходных данных" if missing else "Риск внешних допущений",
            impact="ошибочный вывод при неверной настройке",
            cause=risk_reason,
            action="подтвердить профиль и сверить контрольные показатели",
            effect="снизить риск неверной управленческой оценки",
            confidence="высокая",
        )

        if positive:
            name, value = positive[0]
            self._set_decision_card(
                "opportunity",
                title=f"Лидер прибыли: {name}",
                impact=f"{value:.2f} ₽ до налога",
                cause="лучший подтверждённый результат среди групп",
                action="проверить устойчивость на нескольких периодах",
                effect="прогноз не заявляется без временного ряда",
                confidence="средняя",
            )
        else:
            self._set_decision_card(
                "opportunity",
                title="Возможность не подтверждена",
                impact="нет доказуемого прогноза",
                cause="недостаточно активных прибыльных групп",
                action="накопить сопоставимые периоды",
                effect="появится основание для прогноза",
                confidence="низкая",
            )

        anomalies: list[str] = []
        if result is not None:
            for item in result.group_results:
                if item.group_name == UNALLOCATED_SERVICE_GROUP:
                    anomalies.append("расходы WB без артикула")
                if "ZERO_ACTIVITY" in item.reason_codes:
                    anomalies.append(f"нулевая активность: {item.group_name}")
        self._set_decision_card(
            "anomaly",
            title=("; ".join(anomalies[:2]) if anomalies else "Критических аномалий не выявлено"),
            impact=("требуется отдельная проверка" if anomalies else "нет подтверждённого отклонения"),
            cause=("ограниченная атрибуция исходных строк" if anomalies else "проверенные данные согласованы"),
            action=("проверить строки и ключи атрибуции" if anomalies else "продолжать контроль"),
            effect="не приписывать расход товару без доказательства",
            confidence="высокая",
        )

        totals = result.totals if result else {}
        revenue = self._decimal_metric(totals.get("net_marketplace_income_amount"))
        profit = self._decimal_metric(totals.get("net_profit_amount"))
        units = self._decimal_metric(totals.get("net_sold_units"))
        margin = (
            profit / revenue * Decimal("100")
            if profit is not None and revenue not in {None, Decimal("0")}
            else None
        )
        self.kpi_cards["revenue"].configure(text=f"{revenue:.2f}" if revenue is not None else "—")
        self.kpi_cards["profit"].configure(text=f"{profit:.2f}" if profit is not None else "—")
        self.kpi_cards["margin"].configure(text=f"{margin:.2f}" if margin is not None else "—")
        self.kpi_cards["orders"].configure(text=f"{units:.0f}" if units is not None else "—")

        top_lines = [
            f"{index}. {name}: {value:.2f} ₽"
            for index, (name, value) in enumerate(
                sorted(profits, key=lambda row: row[1], reverse=True)[:5],
                start=1,
            )
        ]
        self._set_text(
            self.top_products_text,
            "\n".join(top_lines) if top_lines else "Нет подтверждённых групп с активностью.",
        )
        self._set_text(
            self.forecast_text,
            "Прогноз спроса заблокирован: текущий WB-only контур не имеет "
            "достаточного временного ряда продаж и остатков. Синтетический "
            "прогноз не показывается.",
        )
        alert_lines = []
        if missing:
            alert_lines.append("• Финансовый профиль неполный.")
        if result is None:
            alert_lines.append("• Финансовый расчёт не выполнен.")
        elif result.status != "CALCULATED":
            alert_lines.extend(f"• {item}" for item in result.missing_inputs[:4])
        if anomalies:
            alert_lines.extend(f"• {item}" for item in anomalies[:3])
        if not alert_lines:
            alert_lines.append("• Подтверждённых критических предупреждений нет.")
        self._set_text(self.alerts_text, "\n".join(alert_lines))

        groups = ["Все товарные группы", *sorted(self.profile.groups)]
        self.header_group_filter.configure(values=tuple(groups))
        if self.header_group_filter.get() not in groups:
            self.header_group_filter.set("Все товарные группы")

        config = _safe_json(self.config_path)
        start = str(config.get("reporting_period_start") or "").strip()
        end = str(config.get("reporting_period_end") or "").strip()
        period = f"{start} — {end}" if start and end else "Период отчёта"
        self.header_period.configure(values=(period,))
        self.header_period.set(period)

    def refresh_domain_pages(self) -> None:
        product_lines = ["ТОВАРНЫЕ ГРУППЫ", ""]
        if not self.profile.groups:
            product_lines.append("Нет подтверждённых товаров. Загрузите отчёт WB.")
        for name, group in sorted(self.profile.groups.items()):
            product_lines.append(
                f"• {name}: {len(group.product_ids)} товаров; "
                f"себестоимость {group.cost_per_unit or 'не заполнена'} ₽"
            )
        self._set_text(self.products_text, "\n".join(product_lines))

        ad_lines = ["РЕКЛАМА", ""]
        total = Decimal("0")
        for name, group in sorted(self.profile.groups.items()):
            value = self._decimal_metric(group.advertising_amount)
            if value is None:
                ad_lines.append(f"• {name}: значение не подтверждено")
                continue
            total += value
            ad_lines.append(f"• {name}: {value:.2f} ₽ вне отчёта")
        ad_lines.append("")
        ad_lines.append(f"Итого подтверждено: {total:.2f} ₽")
        ad_lines.append("Автоматическое управление рекламой отключено.")
        self._set_text(self.advertising_text, "\n".join(ad_lines))

        self._set_text(
            self.supply_text,
            "Модуль не подменяет отсутствие данных. Текущий детализированный "
            "финансовый отчёт WB не содержит достаточного снимка остатков, "
            "поставок и сроков пополнения. Для расчёта нужен отдельный отчёт "
            "склада/поставок. До его импорта прогноз поставки заблокирован.",
        )
        self._set_text(
            self.competitors_text,
            "Данные конкурентов не загружены. Quantum не выполняет скрытый "
            "сетевой сбор и не показывает выдуманные позиции или цены. "
            "Функция остаётся недоступной в локальном WB-only контуре.",
        )
        self._set_text(
            self.seo_text,
            "SEO-анализ требует карточек, поисковых запросов и позиций. "
            "Такие источники в текущем контуре отсутствуют; синтетические "
            "ключевые слова не создаются.",
        )
        self._set_text(
            self.settings_text,
            "Режим: WB_ONLY\n"
            "Ozon: отложен\n"
            "Запись на маркетплейс: отключена\n"
            "Данные: локальное хранение\n"
            f"Конфигурация: {self.config_path}\n"
            f"Финансовый профиль: {self.profile_path}\n\n"
            "Основные параметры изменяются через финансовый профиль. "
            "Техническое редактирование JSON пользователю не требуется.",
        )
        self.refresh_decision_center()

    def show_page(self, key: str) -> None:
        if key not in self.pages:
            key = "decision"
        for frame in self.pages.values():
            frame.pack_forget()
        self.pages[key].pack(fill=tk.BOTH, expand=True)
        titles = dict(NAV_ITEMS)
        internal_titles = {
            "export": "Экспорт",
            "quality": "Контроль данных",
        }
        self.page_title.configure(text=titles.get(key, internal_titles.get(key, key)))
        for page_key, button in self.nav_buttons.items():
            button.configure(
                bg=PALETTE["blue"] if page_key == key else PALETTE["navy"],
                fg="white" if page_key == key else "#D9EAF7",
            )
        self.refresh_domain_pages()

    def set_status(self, text: str, kind: str = "info") -> None:
        colors = {
            "success": PALETTE["green"],
            "warning": PALETTE["orange"],
            "error": PALETTE["red"],
            "info": PALETTE["blue"],
        }
        labels = {
            "success": "ГОТОВО",
            "warning": "ВНИМАНИЕ",
            "error": "ОШИБКА",
            "info": "РАБОТА",
        }
        self.status_text.configure(text=text)
        self.status_badge.configure(
            text=labels.get(kind, "РАБОТА"),
            bg=colors.get(kind, PALETTE["blue"]),
        )


__all__ = [name for name in globals() if not name.startswith("__")]
