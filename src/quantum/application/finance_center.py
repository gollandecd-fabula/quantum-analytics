from __future__ import annotations

from quantum.application._finance_center_shared import *
from quantum.application._finance_center_dialog import FinanceProfileDialog
from quantum.application._finance_center_shell import FinanceCenterShellMixin
from quantum.application._finance_center_pages import FinanceCenterPagesMixin
from quantum.application._finance_center_reports import FinanceCenterReportsMixin
from quantum.application._finance_center_queue_runtime import FinanceCenterQueueRuntimeMixin
from quantum.application._finance_center_calculation import FinanceCenterCalculationMixin
from quantum.application._single_instance import SingleInstanceLock


class QuantumFinanceCenter(
    FinanceCenterCalculationMixin,
    FinanceCenterQueueRuntimeMixin,
    FinanceCenterReportsMixin,
    FinanceCenterPagesMixin,
    FinanceCenterShellMixin,
):
    pass


def main(root: Path | None = None, config: Path | None = None) -> int:
    if tk is None:
        print(json.dumps({"status": "ERROR", "reason_code": "TKINTER_NOT_AVAILABLE"}, ensure_ascii=False))
        return 2
    project_root = (root or Path(os.environ.get("QUANTUM_HOME_LOCAL_ROOT", Path.cwd()))).resolve()
    config_path = (config or Path(os.environ.get("QUANTUM_HOME_LOCAL_CONFIG", project_root / "config" / "default-home-local.json"))).resolve()
    instance_lock = SingleInstanceLock(project_root / "data" / "finance-center.lock")
    if not instance_lock.acquire():
        notice = tk.Tk()
        notice.withdraw()
        messagebox.showwarning(APP_TITLE, "Центр решений Quantum уже запущен. Повторный экземпляр не открыт.")
        notice.destroy()
        return 3
    try:
        root_widget = tk.Tk()
        QuantumFinanceCenter(root_widget, project_root, config_path)
        root_widget.mainloop()
        return 0
    finally:
        instance_lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
