from __future__ import annotations

from quantum.application._finance_center_shared import *


class FinanceProfileDialog:
    def __init__(
        self,
        owner: "QuantumFinanceCenter",
        profile: FinanceProfile,
        products: dict[str, ProductRecord],
    ) -> None:
        self.owner = owner
        self.profile = profile
        self.products = products
        self.window = tk.Toplevel(owner.root_widget)
        self.window.title(
            "Финансовый профиль — группы, себестоимость и расходы"
        )
        self.window.geometry("1120x760")
        self.window.minsize(900, 640)
        self.window.transient(owner.root_widget)
        self.window.grab_set()
        self.cost_vars: dict[str, tk.StringVar] = {}
        self.advanced_vars: dict[tuple[str, str], tk.StringVar] = {}
        self.tax_var = tk.StringVar(value=profile.tax_rate_percent or "")
        self.tax_base_labels = {
            label: metric_id
            for metric_id, label in TAX_BASE_OPTIONS.items()
        }
        self.tax_base_var = tk.StringVar(
            value=TAX_BASE_OPTIONS.get(
                profile.tax_base_metric_id or "",
                "",
            )
        )
        self.other_var = tk.StringVar(
            value=profile.other_expense_per_unit or ""
        )
        self.group_var = tk.StringVar()
        self.product_var = tk.StringVar()
        self.target_group_var = tk.StringVar()
        self._build()

    def _build(self) -> None:
        header = tk.Frame(self.window, bg=PALETTE["navy"], height=88)
        header.pack(fill=tk.X)
        tk.Label(
            header,
            text="Финансовый профиль",
            font=("Segoe UI", 20, "bold"),
            fg="white",
            bg=PALETTE["navy"],
        ).pack(anchor=tk.W, padx=24, pady=(16, 0))
        tk.Label(
            header,
            text=(
                "Автоматические группы можно исправить до расчёта. "
                "Пустые обязательные значения блокируют прибыль."
            ),
            font=("Segoe UI", 10),
            fg="#D9EAF7",
            bg=PALETTE["navy"],
        ).pack(anchor=tk.W, padx=24, pady=(2, 14))

        notebook = ttk.Notebook(self.window)
        notebook.pack(fill=tk.BOTH, expand=True, padx=18, pady=14)
        groups_tab = ttk.Frame(notebook, padding=12)
        advanced_tab = ttk.Frame(notebook, padding=12)
        notebook.add(groups_tab, text="Группы и себестоимость")
        notebook.add(advanced_tab, text="Недостающие финансовые данные")
        self._build_groups_tab(groups_tab)
        self._build_advanced_tab(advanced_tab)

        footer = ttk.Frame(self.window, padding=(18, 0, 18, 16))
        footer.pack(fill=tk.X)
        ttk.Button(
            footer,
            text="Скачать шаблон Excel",
            command=self._export_template,
        ).pack(side=tk.LEFT)
        ttk.Button(
            footer,
            text="Загрузить себестоимость из Excel",
            command=self._import_costs,
        ).pack(side=tk.LEFT, padx=8)
        ttk.Button(
            footer,
            text="Отмена",
            command=self.window.destroy,
        ).pack(side=tk.RIGHT)
        ttk.Button(
            footer,
            text="Сохранить профиль",
            style="Primary.TButton",
            command=self._save,
        ).pack(side=tk.RIGHT, padx=8)

    def _scrollable(
        self,
        parent: tk.Widget,
    ) -> tuple[tk.Canvas, ttk.Frame]:
        canvas = tk.Canvas(
            parent,
            bg=PALETTE["surface"],
            highlightthickness=0,
        )
        scrollbar = ttk.Scrollbar(
            parent,
            orient=tk.VERTICAL,
            command=canvas.yview,
        )
        body = ttk.Frame(canvas)
        window_id = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind(
            "<Configure>",
            lambda _event: canvas.configure(
                scrollregion=canvas.bbox("all")
            ),
        )
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(
                window_id,
                width=event.width,
            ),
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        return canvas, body

    def _build_groups_tab(self, parent: ttk.Frame) -> None:
        top = ttk.Frame(parent)
        top.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(
            top,
            text="Налоговая ставка, %",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Entry(
            top,
            textvariable=self.tax_var,
            width=16,
        ).grid(row=1, column=0, sticky="w", padx=(0, 20))
        ttk.Label(
            top,
            text="Налоговая база",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=1, sticky="w")
        ttk.Combobox(
            top,
            textvariable=self.tax_base_var,
            values=list(self.tax_base_labels),
            state="readonly",
            width=42,
        ).grid(row=1, column=1, sticky="w", padx=(0, 20))
        ttk.Label(
            top,
            text="Прочие расходы на проданную единицу, ₽",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=2, sticky="w")
        ttk.Entry(
            top,
            textvariable=self.other_var,
            width=20,
        ).grid(row=1, column=2, sticky="w")
        ttk.Label(
            top,
            text="Ноль принимается только при явном вводе 0.",
            foreground=PALETTE["orange"],
        ).grid(
            row=2,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(5, 0),
        )

        separator = ttk.Separator(parent)
        separator.pack(fill=tk.X, pady=(0, 10))
        _canvas, body = self._scrollable(parent)
        for row_index, group_name in enumerate(sorted(self.profile.groups)):
            group = self.profile.groups[group_name]
            card = tk.Frame(
                body,
                bg=PALETTE["surface"],
                highlightbackground=PALETTE["line"],
                highlightthickness=1,
            )
            card.grid(
                row=row_index,
                column=0,
                sticky="ew",
                pady=5,
                padx=2,
            )
            body.columnconfigure(0, weight=1)
            tk.Label(
                card,
                text=group_name,
                font=("Segoe UI", 12, "bold"),
                fg=PALETTE["text"],
                bg=PALETTE["surface"],
            ).grid(
                row=0,
                column=0,
                sticky="w",
                padx=14,
                pady=(10, 2),
            )
            tk.Label(
                card,
                text=f"Товаров: {len(group.product_ids)}",
                fg=PALETTE["muted"],
                bg=PALETTE["surface"],
            ).grid(
                row=1,
                column=0,
                sticky="w",
                padx=14,
                pady=(0, 10),
            )
            variable = tk.StringVar(value=group.cost_per_unit or "")
            self.cost_vars[group_name] = variable
            tk.Label(
                card,
                text="Себестоимость группы, ₽",
                fg=PALETTE["text"],
                bg=PALETTE["surface"],
            ).grid(row=0, column=1, sticky="w", padx=10)
            ttk.Entry(
                card,
                textvariable=variable,
                width=18,
            ).grid(
                row=1,
                column=1,
                sticky="w",
                padx=10,
                pady=(0, 10),
            )
            ttk.Button(
                card,
                text="Переименовать",
                command=lambda name=group_name: self._rename(name),
            ).grid(row=0, column=2, rowspan=2, padx=10)
            card.columnconfigure(0, weight=1)

        editor = ttk.LabelFrame(
            body,
            text="Ручная корректировка состава группы",
            padding=10,
        )
        editor.grid(
            row=len(self.profile.groups) + 1,
            column=0,
            sticky="ew",
            pady=12,
            padx=2,
        )
        ttk.Label(editor, text="Товар").grid(
            row=0,
            column=0,
            sticky="w",
        )
        product_values = [
            f"{pid} — "
            f"{self.products.get(pid).name if pid in self.products else pid}"
            for pid in sorted(self.profile.product_to_group)
        ]
        product_box = ttk.Combobox(
            editor,
            textvariable=self.product_var,
            values=product_values,
            state="readonly",
            width=54,
        )
        product_box.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=(0, 10),
        )
        ttk.Label(editor, text="Новая группа").grid(
            row=0,
            column=1,
            sticky="w",
        )
        target_box = ttk.Combobox(
            editor,
            textvariable=self.target_group_var,
            values=sorted(self.profile.groups),
            width=34,
        )
        target_box.grid(
            row=1,
            column=1,
            sticky="ew",
            padx=(0, 10),
        )
        ttk.Button(
            editor,
            text="Перенести",
            command=self._move_product,
        ).grid(row=1, column=2)
        editor.columnconfigure(0, weight=2)
        editor.columnconfigure(1, weight=1)

    def _build_advanced_tab(self, parent: ttk.Frame) -> None:
        ttk.Label(
            parent,
            text=(
                "Эти значения заполняются только тогда, когда "
                "соответствующая сумма отсутствует в отчёте WB. Для "
                "подтверждения отсутствия значения введите 0. Quantum "
                "не подставляет нули автоматически."
            ),
            wraplength=950,
            foreground=PALETTE["muted"],
        ).pack(anchor=tk.W, pady=(0, 10))
        _canvas, body = self._scrollable(parent)
        for group_index, group_name in enumerate(sorted(self.profile.groups)):
            group = self.profile.groups[group_name]
            block = ttk.LabelFrame(body, text=group_name, padding=10)
            block.grid(row=group_index, column=0, sticky="ew", pady=6)
            body.columnconfigure(0, weight=1)
            for field_index, (field_name, label) in enumerate(
                _ADVANCED_FIELDS
            ):
                ttk.Label(block, text=label).grid(
                    row=field_index,
                    column=0,
                    sticky="w",
                    pady=3,
                )
                current = getattr(group, field_name)
                variable = tk.StringVar(value=current or "")
                self.advanced_vars[(group_name, field_name)] = variable
                ttk.Entry(
                    block,
                    textvariable=variable,
                    width=22,
                ).grid(
                    row=field_index,
                    column=1,
                    sticky="w",
                    padx=10,
                    pady=3,
                )
            block.columnconfigure(0, weight=1)

    def _sync_profile_from_vars(self) -> None:
        self.profile.tax_rate_percent = self.tax_var.get().strip() or None
        self.profile.tax_base_metric_id = self.tax_base_labels.get(
            self.tax_base_var.get().strip()
        )
        self.profile.other_expense_per_unit = (
            self.other_var.get().strip() or None
        )
        for group_name, variable in self.cost_vars.items():
            if group_name in self.profile.groups:
                self.profile.groups[group_name].cost_per_unit = (
                    variable.get().strip() or None
                )
        for (group_name, field_name), variable in self.advanced_vars.items():
            if group_name in self.profile.groups:
                setattr(
                    self.profile.groups[group_name],
                    field_name,
                    variable.get().strip() or None,
                )
        self.profile.confirmed = False

    def _rename(self, old_name: str) -> None:
        new_name = simpledialog.askstring(
            APP_TITLE,
            "Новое название группы:",
            initialvalue=old_name,
            parent=self.window,
        )
        if not new_name:
            return
        self._sync_profile_from_vars()
        try:
            rename_group(self.profile, old_name, new_name)
        except FinanceProfileError as exc:
            messagebox.showerror(
                APP_TITLE,
                self.owner.describe_error(exc),
                parent=self.window,
            )
            return
        self.window.destroy()
        self.owner.open_finance_profile()

    def _move_product(self) -> None:
        selected = self.product_var.get().strip()
        target = self.target_group_var.get().strip()
        if not selected or not target:
            messagebox.showwarning(
                APP_TITLE,
                "Выберите товар и укажите новую группу.",
                parent=self.window,
            )
            return
        product_id = selected.split(" — ", 1)[0].strip()
        self._sync_profile_from_vars()
        try:
            reassign_product(self.profile, product_id, target)
        except FinanceProfileError as exc:
            messagebox.showerror(
                APP_TITLE,
                self.owner.describe_error(exc),
                parent=self.window,
            )
            return
        self.window.destroy()
        self.owner.open_finance_profile()

    def _export_template(self) -> None:
        target = filedialog.asksaveasfilename(
            parent=self.window,
            title="Сохранить шаблон себестоимости",
            defaultextension=".xlsx",
            initialfile="Quantum_Себестоимость.xlsx",
            filetypes=[("Excel", "*.xlsx")],
        )
        if not target:
            return
        try:
            write_cost_template(Path(target), list(self.profile.groups))
        except FinanceProfileError as exc:
            messagebox.showerror(
                APP_TITLE,
                self.owner.describe_error(exc),
                parent=self.window,
            )
            return
        messagebox.showinfo(
            APP_TITLE,
            "Шаблон Excel сохранён.",
            parent=self.window,
        )

    def _import_costs(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self.window,
            title="Выберите Excel с себестоимостью",
            filetypes=[
                ("Excel", "*.xlsx *.xlsm *.zip"),
                ("Все файлы", "*.*"),
            ],
        )
        if not selected:
            return
        self._sync_profile_from_vars()
        try:
            costs = parse_cost_workbook(Path(selected))
            unknown = apply_costs(self.profile, costs)
        except FinanceProfileError as exc:
            messagebox.showerror(
                APP_TITLE,
                self.owner.describe_error(exc),
                parent=self.window,
            )
            return
        if unknown:
            messagebox.showwarning(
                APP_TITLE,
                "В Excel найдены неизвестные группы:\n" + "\n".join(unknown),
                parent=self.window,
            )
        self.window.destroy()
        self.owner.open_finance_profile()

    def _save(self) -> None:
        self._sync_profile_from_vars()
        try:
            save_profile(self.owner.profile_path, self.profile)
        except FinanceProfileError as exc:
            messagebox.showerror(
                APP_TITLE,
                self.owner.describe_error(exc),
                parent=self.window,
            )
            return
        self.owner.profile = self.profile
        self.owner.refresh_finance_summary()
        self.owner.set_status(
            "Финансовый профиль сохранён. Можно запускать расчёт.",
            "success",
        )
        self.window.destroy()


__all__ = [name for name in globals() if not name.startswith("__")]
