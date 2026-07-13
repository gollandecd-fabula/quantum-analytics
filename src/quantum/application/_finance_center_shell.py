from __future__ import annotations

from quantum.application._finance_center_shared import *

class FinanceCenterShellMixin:
        def __init__(self, root_widget: tk.Tk, project_root: Path, config_path: Path) -> None:
            self.root_widget = root_widget
            self.project_root = project_root.resolve()
            self.config_path = config_path.resolve()
            self.profile_path = self.project_root / PROFILE_RELATIVE_PATH
            self.profile = load_profile(self.profile_path) or FinanceProfile()
            self.reports: dict[str, ReportState] = {}
            self.products: dict[str, ProductRecord] = {}
            self.events: queue.Queue[tuple[str, str, Any]] = queue.Queue()
            self.counter = 0
            self.pages: dict[str, ttk.Frame] = {}
            self.nav_buttons: dict[str, tk.Button] = {}
            self.current_result: FinanceRunResult | None = None
            self.current_outputs: dict[str, Path] = {}
            self.root_widget.title(APP_TITLE)
            self.root_widget.geometry("1360x820")
            self.root_widget.minsize(1080, 680)
            self._configure_style()
            self._build_shell()
            self.show_page("decision")
            self.refresh_finance_summary()
            self.root_widget.after(150, self._drain_events)

        def _configure_style(self) -> None:
            style = ttk.Style(self.root_widget)
            if "clam" in style.theme_names():
                style.theme_use("clam")
            style.configure("TFrame", background=PALETTE["background"])
            style.configure("TLabel", background=PALETTE["background"], foreground=PALETTE["text"], font=("Segoe UI", 10))
            style.configure("TLabelframe", background=PALETTE["background"], foreground=PALETTE["text"])
            style.configure("TLabelframe.Label", background=PALETTE["background"], foreground=PALETTE["text"], font=("Segoe UI", 10, "bold"))
            style.configure("TButton", font=("Segoe UI", 10), padding=(11, 7))
            style.configure("Primary.TButton", background=PALETTE["blue"], foreground="white", font=("Segoe UI", 10, "bold"))
            style.map("Primary.TButton", background=[("active", PALETTE["cyan"])])
            style.configure("Success.TButton", background=PALETTE["green"], foreground="white", font=("Segoe UI", 10, "bold"))
            style.map("Success.TButton", background=[("active", "#0F6D59")])
            style.configure("Treeview", rowheight=29, background="white", fieldbackground="white", foreground=PALETTE["text"])
            style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"), background="#DCEAF5", foreground=PALETTE["navy"])
            style.configure("TNotebook", background=PALETTE["background"])
            style.configure("TNotebook.Tab", padding=(12, 7), font=("Segoe UI", 9, "bold"))

        def _build_shell(self) -> None:
            shell = tk.Frame(self.root_widget, bg=PALETTE["background"])
            shell.pack(fill=tk.BOTH, expand=True)
            sidebar = tk.Frame(shell, bg=PALETTE["navy"], width=245)
            sidebar.pack(side=tk.LEFT, fill=tk.Y)
            sidebar.pack_propagate(False)
            tk.Label(sidebar, text="QUANTUM", font=("Segoe UI", 22, "bold"), fg="white", bg=PALETTE["navy"]).pack(anchor=tk.W, padx=20, pady=(22, 0))
            tk.Label(sidebar, text="WB · HOME_LOCAL", font=("Segoe UI", 9, "bold"), fg="#8FD9EA", bg=PALETTE["navy"]).pack(anchor=tk.W, padx=21, pady=(0, 22))
            for key, label in NAV_ITEMS:
                button = tk.Button(
                    sidebar,
                    text=label,
                    anchor="w",
                    relief=tk.FLAT,
                    bd=0,
                    padx=18,
                    pady=10,
                    font=("Segoe UI", 10, "bold"),
                    fg="#D9EAF7",
                    bg=PALETTE["navy"],
                    activeforeground="white",
                    activebackground=PALETTE["blue"],
                    command=lambda page=key: self.show_page(page),
                )
                button.pack(fill=tk.X, padx=8, pady=2)
                self.nav_buttons[key] = button
            tk.Label(
                sidebar,
                text="ТОЛЬКО ЧТЕНИЕ\nЗапись на маркетплейс: отключена",
                justify=tk.LEFT,
                font=("Segoe UI", 9),
                fg="#A9C5D8",
                bg=PALETTE["navy"],
            ).pack(side=tk.BOTTOM, anchor=tk.W, padx=20, pady=18)

            content = tk.Frame(shell, bg=PALETTE["background"])
            content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            self.header = tk.Frame(content, bg=PALETTE["surface"], height=74, highlightbackground=PALETTE["line"], highlightthickness=1)
            self.header.pack(fill=tk.X)
            self.page_title = tk.Label(self.header, text="", font=("Segoe UI", 19, "bold"), fg=PALETTE["navy"], bg=PALETTE["surface"])
            self.page_title.pack(side=tk.LEFT, padx=24, pady=18)
            self.status_badge = tk.Label(self.header, text="ГОТОВО", font=("Segoe UI", 9, "bold"), fg="white", bg=PALETTE["green"], padx=12, pady=6)
            self.status_badge.pack(side=tk.RIGHT, padx=24)

            self.page_host = ttk.Frame(content, padding=18)
            self.page_host.pack(fill=tk.BOTH, expand=True)
            self._build_decision_page()
            self._build_reports_page()
            self._build_finance_page()
            self._build_analytics_page()
            self._build_recommendations_page()
            self._build_export_page()
            self._build_quality_page()

            footer = tk.Frame(content, bg=PALETTE["surface"], height=38, highlightbackground=PALETTE["line"], highlightthickness=1)
            footer.pack(fill=tk.X)
            self.status_text = tk.Label(footer, text="Готово. Файлы обрабатываются локально.", font=("Segoe UI", 9), fg=PALETTE["muted"], bg=PALETTE["surface"])
            self.status_text.pack(side=tk.LEFT, padx=18, pady=8)
__all__ = [name for name in globals() if not name.startswith("__")]
