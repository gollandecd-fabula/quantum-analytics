from __future__ import annotations

from quantum.application._finance_center_shared import *


class FinanceCenterShellMixin:
    def __init__(
        self,
        root_widget: tk.Tk,
        project_root: Path,
        config_path: Path,
    ) -> None:
        self.root_widget = root_widget
        self.project_root = project_root.resolve()
        self.config_path = config_path.resolve()
        self.profile_path = self.project_root / PROFILE_RELATIVE_PATH
        self.profile = load_profile(self.profile_path) or FinanceProfile()
        self.reports: dict[str, ReportState] = {}
        self.products: dict[str, ProductRecord] = {}
        self.events: queue.Queue[tuple[str, str, Any]] = queue.Queue()
        self.import_queue = SequentialImportQueue()
        self.cancel_event = threading.Event()
        self.process_lock = threading.Lock()
        self.active_process: subprocess.Popen[object] | None = None
        self.profile_changed_pending = False
        self.closing = False
        self.counter = 0
        self.pages: dict[str, ttk.Frame] = {}
        self.nav_buttons: dict[str, tk.Button] = {}
        self.current_result: FinanceRunResult | None = None
        self.current_outputs: dict[str, Path] = {}
        self.current_recommendations: tuple[dict[str, Any], ...] = ()
        self.current_recommendation_errors: tuple[str, ...] = ()
        self.root_widget.title(APP_TITLE)
        self.root_widget.geometry("1440x900")
        self.root_widget.minsize(1120, 700)
        self._configure_style()
        self._build_shell()
        self.root_widget.protocol("WM_DELETE_WINDOW", self.request_close)
        self.restore_persisted_reports()
        self.show_page("decision")
        self.refresh_finance_summary()
        self._refresh_queue_controls()
        self.root_widget.after(150, self._drain_events)

    def _configure_style(self) -> None:
        style = ttk.Style(self.root_widget)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure(
            "TFrame",
            background=PALETTE["background"],
        )
        style.configure(
            "TLabel",
            background=PALETTE["background"],
            foreground=PALETTE["text"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "TLabelframe",
            background=PALETTE["background"],
            foreground=PALETTE["text"],
        )
        style.configure(
            "TLabelframe.Label",
            background=PALETTE["background"],
            foreground=PALETTE["text"],
            font=("Segoe UI", 10, "bold"),
        )
        style.configure("TButton", font=("Segoe UI", 10), padding=(11, 7))
        style.configure(
            "Primary.TButton",
            background=PALETTE["blue"],
            foreground="white",
            font=("Segoe UI", 10, "bold"),
        )
        style.map(
            "Primary.TButton",
            background=[("active", PALETTE["cyan"])],
        )
        style.configure(
            "Success.TButton",
            background=PALETTE["green"],
            foreground="white",
            font=("Segoe UI", 10, "bold"),
        )
        style.map(
            "Success.TButton",
            background=[("active", "#0F6D59")],
        )
        style.configure(
            "Treeview",
            rowheight=29,
            background="white",
            fieldbackground="white",
            foreground=PALETTE["text"],
        )
        style.configure(
            "Treeview.Heading",
            font=("Segoe UI", 10, "bold"),
            background="#DCEAF5",
            foreground=PALETTE["navy"],
        )
        style.configure("TNotebook", background=PALETTE["background"])
        style.configure(
            "TNotebook.Tab",
            padding=(12, 7),
            font=("Segoe UI", 9, "bold"),
        )
        style.configure(
            "Header.TCombobox",
            padding=(8, 5),
            font=("Segoe UI", 9),
        )

    def _build_shell(self) -> None:
        shell = tk.Frame(self.root_widget, bg=PALETTE["background"])
        shell.pack(fill=tk.BOTH, expand=True)

        sidebar = tk.Frame(shell, bg=PALETTE["navy"], width=252)
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)
        tk.Label(
            sidebar,
            text="QUANTUM",
            font=("Segoe UI", 22, "bold"),
            fg="white",
            bg=PALETTE["navy"],
        ).pack(anchor=tk.W, padx=20, pady=(20, 0))
        tk.Label(
            sidebar,
            text="Локальная аналитика · WB",
            font=("Segoe UI", 9, "bold"),
            fg="#8FD9EA",
            bg=PALETTE["navy"],
        ).pack(anchor=tk.W, padx=21, pady=(0, 14))

        nav_host = tk.Frame(sidebar, bg=PALETTE["navy"])
        nav_host.pack(fill=tk.BOTH, expand=True)
        for key, label in NAV_ITEMS:
            button = tk.Button(
                nav_host,
                text=label,
                anchor="w",
                relief=tk.FLAT,
                bd=0,
                padx=18,
                pady=7,
                font=("Segoe UI", 9, "bold"),
                fg="#D9EAF7",
                bg=PALETTE["navy"],
                activeforeground="white",
                activebackground=PALETTE["blue"],
                command=lambda page=key: self.show_page(page),
            )
            button.pack(fill=tk.X, padx=8, pady=1)
            self.nav_buttons[key] = button

        profile_box = tk.Frame(
            sidebar,
            bg="#0C2237",
            highlightbackground="#294B66",
            highlightthickness=1,
        )
        profile_box.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
        tk.Label(
            profile_box,
            text="Дмитрий · Владелец",
            font=("Segoe UI", 9, "bold"),
            fg="white",
            bg="#0C2237",
        ).pack(anchor=tk.W, padx=12, pady=(10, 2))
        tk.Label(
            profile_box,
            text="ТОЛЬКО ЧТЕНИЕ · запись в WB отключена",
            font=("Segoe UI", 8),
            fg="#9FC2D9",
            bg="#0C2237",
            wraplength=210,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, padx=12, pady=(0, 10))

        content = tk.Frame(shell, bg=PALETTE["background"])
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.header = tk.Frame(
            content,
            bg=PALETTE["surface"],
            height=78,
            highlightbackground=PALETTE["line"],
            highlightthickness=1,
        )
        self.header.pack(fill=tk.X)
        self.page_title = tk.Label(
            self.header,
            text="",
            font=("Segoe UI", 19, "bold"),
            fg=PALETTE["navy"],
            bg=PALETTE["surface"],
        )
        self.page_title.pack(side=tk.LEFT, padx=(24, 16), pady=18)

        self.status_badge = tk.Label(
            self.header,
            text="ГОТОВО",
            font=("Segoe UI", 9, "bold"),
            fg="white",
            bg=PALETTE["green"],
            padx=12,
            pady=6,
        )
        self.status_badge.pack(side=tk.RIGHT, padx=(8, 24))

        header_controls = tk.Frame(self.header, bg=PALETTE["surface"])
        header_controls.pack(side=tk.RIGHT, pady=14)
        tk.Label(
            header_controls,
            text="Группа",
            font=("Segoe UI", 8),
            fg=PALETTE["muted"],
            bg=PALETTE["surface"],
        ).grid(row=0, column=0, sticky="w")
        self.header_group_filter = ttk.Combobox(
            header_controls,
            state="readonly",
            width=19,
            values=("Все товарные группы",),
            style="Header.TCombobox",
        )
        self.header_group_filter.set("Все товарные группы")
        self.header_group_filter.grid(row=1, column=0, padx=(0, 10))
        self.header_group_filter.bind(
            "<<ComboboxSelected>>",
            lambda _event: self.refresh_decision_center(),
        )
        tk.Label(
            header_controls,
            text="Период",
            font=("Segoe UI", 8),
            fg=PALETTE["muted"],
            bg=PALETTE["surface"],
        ).grid(row=0, column=1, sticky="w")
        self.header_period = ttk.Combobox(
            header_controls,
            state="readonly",
            width=23,
            values=("Период отчёта",),
            style="Header.TCombobox",
        )
        self.header_period.set("Период отчёта")
        self.header_period.grid(row=1, column=1)

        self.page_host = ttk.Frame(content, padding=18)
        self.page_host.pack(fill=tk.BOTH, expand=True)
        self._build_decision_page()
        self._build_reports_page()
        self._build_finance_page()
        self._build_analytics_page()
        self._build_products_page()
        self._build_advertising_page()
        self._build_supply_page()
        self._build_competitors_page()
        self._build_seo_page()
        self._build_ai_page()
        self._build_settings_page()
        # Internal support pages remain accessible from Settings, not the
        # primary navigation, so the approved navigation is not diluted.
        self._build_export_page()
        self._build_quality_page()

        footer = tk.Frame(
            content,
            bg=PALETTE["surface"],
            height=38,
            highlightbackground=PALETTE["line"],
            highlightthickness=1,
        )
        footer.pack(fill=tk.X)
        self.status_text = tk.Label(
            footer,
            text="Готово. Файлы обрабатываются локально.",
            font=("Segoe UI", 9),
            fg=PALETTE["muted"],
            bg=PALETTE["surface"],
        )
        self.status_text.pack(side=tk.LEFT, padx=18, pady=8)
        tk.Label(
            footer,
            text="WB_ONLY · Ozon отложен · внешняя запись отключена",
            font=("Segoe UI", 8),
            fg=PALETTE["muted"],
            bg=PALETTE["surface"],
        ).pack(side=tk.RIGHT, padx=18)


__all__ = [name for name in globals() if not name.startswith("__")]
