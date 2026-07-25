from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    if text.count(old) != 1:
        raise SystemExit(f"REPLACE_COUNT_MISMATCH:{path}:{text.count(old)}")
    write(path, text.replace(old, new, 1))


shell_path = "src/quantum/application/_finance_center_shell.py"
replace_once(
    shell_path,
    "        self.profile_save_blocked = False\n",
    "        self.profile_save_blocked = False\n"
    "        self.finance_profile_dialog: Any | None = None\n",
)

dialog_path = "src/quantum/application/_finance_center_dialog.py"
replace_once(
    dialog_path,
    "        self.window.grab_set()\n",
    "        self.window.grab_set()\n"
    "        self.owner.finance_profile_dialog = self\n",
)
dialog = read(dialog_path)
cancel_start = dialog.index("    def _cancel(")
static_start = dialog.index("    @staticmethod\n", cancel_start)
replacement = '''    def _release_owner_reference(self) -> None:
        if getattr(self.owner, "finance_profile_dialog", None) is self:
            self.owner.finance_profile_dialog = None

    def _close_window(self) -> None:
        self._release_owner_reference()
        self.window.destroy()

    def _cancel(self, _event: object | None = None) -> None:
        self._close_window()

    def _reopen_staged(self) -> None:
        staged = FinanceProfile.from_dict(self.profile.to_dict())
        self._close_window()
        FinanceProfileDialog(self.owner, staged, self.products)

'''
dialog = dialog[:cancel_start] + replacement + dialog[static_start:]
marker = "        self.window.destroy()\n\n\n__all__"
if marker not in dialog:
    raise SystemExit("SAVE_CLOSE_MARKER_NOT_FOUND")
dialog = dialog.replace(
    marker,
    "        self._close_window()\n\n\n__all__",
    1,
)
write(dialog_path, dialog)

reports_path = "src/quantum/application/_finance_center_reports.py"
reports = read(reports_path)
start = reports.index("    def open_finance_profile(self) -> None:\n")
end = reports.index("\n    def refresh_finance_summary", start)
open_block = '''    def open_finance_profile(self) -> None:
        existing = getattr(self, "finance_profile_dialog", None)
        if existing is not None:
            try:
                existing.window.deiconify()
                existing.window.lift()
                existing.window.focus_force()
                return
            except tk.TclError:
                self.finance_profile_dialog = None
        if self.profile_save_blocked:
            messagebox.showerror(
                APP_TITLE,
                "Финансовый профиль повреждён, а резервную копию создать "
                "не удалось. Сохраните заблокированный файл, чтобы не потерять "
                "исходный файл.",
            )
            return
        if not self.profile.groups:
            messagebox.showwarning(
                APP_TITLE,
                "Сначала загрузите отчёт WB, содержащий товары и артикулы.",
            )
            return
        FinanceProfileDialog(self, self.profile, self.products)
'''
write(reports_path, reports[:start] + open_block + reports[end:])

test_path = "tests/test_full_project_redteam_r1.py"
tests = read(test_path)
insertion = '''
    def test_finance_profile_dialog_is_single_instance(self) -> None:
        shell = (APP / "_finance_center_shell.py").read_text(encoding="utf-8")
        reports = (APP / "_finance_center_reports.py").read_text(encoding="utf-8")
        self.assertIn("self.finance_profile_dialog: Any | None = None", shell)
        self.assertIn('existing = getattr(self, "finance_profile_dialog", None)', reports)
        self.assertIn("existing.window.lift()", reports)
        self.assertIn("existing.window.focus_force()", reports)
        self.assertIn("self.finance_profile_dialog = None", reports)

    def test_dialog_close_releases_single_instance_reference(self) -> None:
        source = (APP / "_finance_center_dialog.py").read_text(encoding="utf-8")
        self.assertIn("self.owner.finance_profile_dialog = self", source)
        self.assertIn("def _release_owner_reference", source)
        self.assertIn("self.owner.finance_profile_dialog = None", source)
        self.assertIn("self._close_window()", source)
'''
sentinel = "\n\nif __name__ == \"__main__\":\n"
if sentinel not in tests:
    raise SystemExit("TEST_SENTINEL_NOT_FOUND")
if "test_finance_profile_dialog_is_single_instance" not in tests:
    tests = tests.replace(sentinel, "\n" + insertion + sentinel, 1)
write(test_path, tests)

defect_path = ROOT / "docs/evidence/FULL_PROJECT_REDTEAM_R1_DEFECT_REGISTER.json"
defects = json.loads(defect_path.read_text(encoding="utf-8"))
defects["summary"]["p2_found"] = 6
defects["summary"]["candidate_fixes"] = 9
if not any(row.get("id") == "FR1-009" for row in defects["defects"]):
    defects["defects"].append(
        {
            "id": "FR1-009",
            "severity": "P2",
            "area": "FINANCE_UI_SINGLE_INSTANCE",
            "finding": "Repeated activation of the Finance Profile action could open parallel staged editors. A later Save from an older editor could overwrite values saved from a newer editor.",
            "repair": "The shell owns one finance-profile dialog reference. Repeated activation raises and focuses the existing dialog; every Cancel, reopen and successful Save releases the reference before closing.",
            "evidence": [
                "tests.test_full_project_redteam_r1.test_finance_profile_dialog_is_single_instance",
                "tests.test_full_project_redteam_r1.test_dialog_close_releases_single_instance_reference",
            ],
            "status": "FIXED_IN_CANDIDATE_AWAITING_EXACT_HEAD_VALIDATION",
        }
    )
defect_path.write_text(
    json.dumps(defects, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)

overlay_path = ROOT / "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_FULL_PROJECT_REDTEAM_R1.json"
overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
rebuilt = []
for path, _digest, _size in overlay["entries"]:
    data = (ROOT / path).read_bytes()
    rebuilt.append([path, hashlib.sha256(data).hexdigest(), len(data)])
overlay["entries"] = rebuilt
overlay_path.write_text(
    json.dumps(overlay, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
