from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


desktop_path = "src/quantum/application/desktop_center.py"
desktop = read(desktop_path)
if "class ApplicationAlreadyRunning" not in desktop:
    desktop = desktop.replace(
        "import argparse\nimport json\nfrom pathlib import Path\n",
        "import argparse\nimport json\nimport os\nfrom pathlib import Path\nimport sys\nfrom typing import BinaryIO\n",
        1,
    )
    marker = "\n\ndef self_test(root: Path, config: Path) -> dict[str, object]:\n"
    block = r'''

class ApplicationAlreadyRunning(RuntimeError):
    pass


class ApplicationLock:
    """Hold one cross-platform process lock for the local desktop runtime."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle: BinaryIO | None = None

    def __enter__(self) -> "ApplicationLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        try:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
                os.fsync(handle.fileno())
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise ApplicationAlreadyRunning(str(self.path)) from exc
        self.handle = handle
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        handle = self.handle
        self.handle = None
        if handle is None:
            return
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def application_lock(root: Path) -> ApplicationLock:
    return ApplicationLock(
        root.resolve() / "data" / "runtime" / "quantum-desktop.lock"
    )


def _notify_already_running() -> None:
    message = (
        "Центр решений Quantum уже запущен. "
        "Закройте существующее окно перед повторным запуском."
    )
    try:
        import tkinter as tk
        from tkinter import messagebox

        owner = tk.Tk()
        owner.withdraw()
        try:
            messagebox.showinfo("Quantum", message, parent=owner)
        finally:
            owner.destroy()
    except Exception:
        print(message, file=sys.stderr)
'''
    if marker not in desktop:
        raise SystemExit("DESKTOP_SELF_TEST_MARKER_NOT_FOUND")
    desktop = desktop.replace(marker, block + marker, 1)
    old = '''    repair_legacy_shortcuts(args.root)
    return finance_center_main(root=args.root, config=args.config)
'''
    new = '''    try:
        with application_lock(args.root):
            repair_legacy_shortcuts(args.root)
            return finance_center_main(root=args.root, config=args.config)
    except ApplicationAlreadyRunning:
        _notify_already_running()
        return 3
'''
    if old not in desktop:
        raise SystemExit("DESKTOP_MAIN_MARKER_NOT_FOUND")
    desktop = desktop.replace(old, new, 1)
write(desktop_path, desktop)

test_path = "tests/test_full_project_redteam_r1.py"
tests = read(test_path)
insertion = r'''
    def test_desktop_process_lock_blocks_second_instance_and_releases(self) -> None:
        from quantum.application.desktop_center import (
            ApplicationAlreadyRunning,
            application_lock,
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with application_lock(root):
                with self.assertRaises(ApplicationAlreadyRunning):
                    with application_lock(root):
                        pass
            with application_lock(root):
                pass

    def test_desktop_main_wraps_runtime_in_process_lock(self) -> None:
        source = (APP / "desktop_center.py").read_text(encoding="utf-8")
        self.assertIn("with application_lock(args.root):", source)
        self.assertIn("except ApplicationAlreadyRunning:", source)
        self.assertIn("return 3", source)
'''
sentinel = "\n\nif __name__ == \"__main__\":\n"
if sentinel not in tests:
    raise SystemExit("TEST_SENTINEL_NOT_FOUND")
if "test_desktop_process_lock_blocks_second_instance_and_releases" not in tests:
    tests = tests.replace(sentinel, "\n" + insertion + sentinel, 1)
write(test_path, tests)

defect_path = ROOT / "docs/evidence/FULL_PROJECT_REDTEAM_R1_DEFECT_REGISTER.json"
defects = json.loads(defect_path.read_text(encoding="utf-8"))
defects["summary"]["p2_found"] = 7
defects["summary"]["candidate_fixes"] = 10
if not any(row.get("id") == "FR1-010" for row in defects["defects"]):
    defects["defects"].append(
        {
            "id": "FR1-010",
            "severity": "P2",
            "area": "DESKTOP_PROCESS_SINGLE_INSTANCE",
            "finding": "Two concurrently launched Quantum desktop processes could independently edit the finance profile and local report state, allowing stale cross-process writes.",
            "repair": "The desktop entry point now holds one non-blocking cross-platform OS file lock for the full GUI runtime. A second process shows a user-facing message and exits without opening another mutable runtime.",
            "evidence": [
                "tests.test_full_project_redteam_r1.test_desktop_process_lock_blocks_second_instance_and_releases",
                "tests.test_full_project_redteam_r1.test_desktop_main_wraps_runtime_in_process_lock",
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
