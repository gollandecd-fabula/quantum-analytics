from __future__ import annotations

from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

from quantum.application._finance_center_queue import SequentialImportQueue
from quantum.application._single_instance import SingleInstanceLock
from quantum.application import _finance_center_import as import_runtime


class SequentialImportQueueTests(unittest.TestCase):
    def test_only_one_item_can_be_active_and_duplicates_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            first = root / "first.xlsx"
            second = root / "second.xlsx"
            first.write_bytes(b"1")
            second.write_bytes(b"2")
            queue = SequentialImportQueue()
            self.assertTrue(queue.add("r1", first))
            self.assertFalse(queue.add("dup", first))
            self.assertTrue(queue.add("r2", second))
            self.assertEqual(queue.start_next(), "r1")
            self.assertIsNone(queue.start_next())
            self.assertEqual(queue.active, "r1")
            self.assertEqual(queue.pending_count, 1)
            queue.complete("r1")
            self.assertEqual(queue.start_next(), "r2")
            queue.complete("r2")
            self.assertFalse(queue.is_busy)

    def test_cancel_pending_does_not_start_cancelled_rows(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            paths = []
            for index in range(3):
                path = root / f"{index}.xlsx"
                path.write_bytes(str(index).encode())
                paths.append(path)
            queue = SequentialImportQueue()
            for index, path in enumerate(paths):
                self.assertTrue(queue.add(f"r{index}", path))
            self.assertEqual(queue.start_next(), "r0")
            self.assertEqual(queue.cancel_pending(), ("r1", "r2"))
            queue.complete("r0")
            self.assertIsNone(queue.start_next())
            self.assertFalse(queue.is_busy)

    def test_repeat_is_blocked_while_row_is_active_or_pending(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "report.xlsx"
            path.write_bytes(b"x")
            queue = SequentialImportQueue()
            self.assertTrue(queue.add("r1", path))
            self.assertFalse(queue.requeue("r1"))
            self.assertEqual(queue.start_next(), "r1")
            self.assertFalse(queue.requeue("r1"))
            queue.complete("r1")
            self.assertTrue(queue.requeue("r1"))


class SingleInstanceLockTests(unittest.TestCase):
    def test_second_instance_is_rejected_until_first_releases(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "data" / "finance-center.lock"
            first = SingleInstanceLock(path)
            second = SingleInstanceLock(path)
            self.assertTrue(first.acquire())
            self.assertFalse(second.acquire())
            first.release()
            self.assertTrue(second.acquire())
            second.release()


class RunImportCancellationTests(unittest.TestCase):
    class FakeProcess:
        pid = 4242

        def __init__(self) -> None:
            self.returncode = None
            self.terminated = False

        def poll(self):
            return 1 if self.terminated else None

        def wait(self, timeout=None):
            self.returncode = 1 if self.terminated else 0
            return self.returncode

        def terminate(self):
            self.terminated = True

        def kill(self):
            self.terminated = True

    class CompletedProcess(FakeProcess):
        def poll(self):
            return 0

        def wait(self, timeout=None):
            self.returncode = 0
            return 0

    def test_hidden_batch_import_uses_one_click_attestations_and_keeps_defender(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "scripts").mkdir()
            (root / "scripts" / "import_source.ps1").write_text("# test", encoding="utf-8")
            source = root / "report.xlsx"
            source.write_bytes(b"xlsx")
            fake = self.CompletedProcess()
            with mock.patch.object(import_runtime.subprocess, "Popen", return_value=fake) as popen, mock.patch.object(
                import_runtime, "_safe_json_load", return_value={"status": "ADMISSION_COMPLETE"}
            ), mock.patch.object(
                import_runtime, "summarize_report", return_value=("Готово", "WB_XLSX", "ADMISSION_COMPLETE", "Импорт завершён.")
            ):
                row = import_runtime.run_import(source, root)

            command = popen.call_args.args[0]
            for flag in ("-NonInteractive", "-AuthorityAttested", "-SchemaReviewed"):
                self.assertIn(flag, command)
            self.assertNotIn("-SkipDefenderScan", command)
            self.assertEqual(
                popen.call_args.kwargs["creationflags"],
                getattr(import_runtime.subprocess, "CREATE_NO_WINDOW", 0),
            )
            self.assertEqual(popen.call_args.kwargs["stdout"], import_runtime.subprocess.DEVNULL)
            self.assertEqual(popen.call_args.kwargs["stderr"], import_runtime.subprocess.DEVNULL)
            self.assertEqual(row.status, "Готово")
            self.assertTrue(row.details["batch_authority_attested"])
            self.assertTrue(row.details["batch_schema_reviewed"])
            self.assertFalse(row.details["interactive_prompts"])
            self.assertFalse(row.details["defender_scan_skipped"])

    def test_cancelled_import_returns_cancelled_row_and_clears_callback(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "scripts").mkdir()
            (root / "scripts" / "import_source.ps1").write_text("# test", encoding="utf-8")
            source = root / "report.xlsx"
            source.write_bytes(b"xlsx")
            event = threading.Event()
            event.set()
            fake = self.FakeProcess()
            seen = []
            with mock.patch.object(import_runtime.subprocess, "Popen", return_value=fake) as popen, mock.patch.object(
                import_runtime, "_terminate_process_tree", side_effect=lambda process: process.terminate()
            ):
                row = import_runtime.run_import(
                    source,
                    root,
                    cancel_event=event,
                    process_callback=seen.append,
                )
            self.assertEqual(row.status, "Отменено")
            self.assertEqual(row.error, "CANCELLED_BY_USER")
            self.assertEqual(seen, [fake, None])
            command = popen.call_args.args[0]
            for flag in ("-NonInteractive", "-AuthorityAttested", "-SchemaReviewed"):
                self.assertIn(flag, command)
            self.assertNotIn("-SkipDefenderScan", command)
            self.assertEqual(
                popen.call_args.kwargs["creationflags"],
                getattr(import_runtime.subprocess, "CREATE_NO_WINDOW", 0),
            )
            self.assertEqual(popen.call_args.kwargs["stdout"], import_runtime.subprocess.DEVNULL)
            self.assertEqual(popen.call_args.kwargs["stderr"], import_runtime.subprocess.DEVNULL)


class RuntimeRoutingTests(unittest.TestCase):
    def test_finance_center_uses_queue_runtime_before_legacy_reports_mixin(self) -> None:
        from quantum.application.finance_center import QuantumFinanceCenter
        from quantum.application._finance_center_queue_runtime import FinanceCenterQueueRuntimeMixin

        self.assertLess(
            QuantumFinanceCenter.__mro__.index(FinanceCenterQueueRuntimeMixin),
            QuantumFinanceCenter.__mro__.index(
                __import__("quantum.application._finance_center_reports", fromlist=["FinanceCenterReportsMixin"]).FinanceCenterReportsMixin
            ),
        )

    def test_ui_source_has_queue_cancel_and_busy_guards(self) -> None:
        root = Path(import_runtime.__file__).resolve().parent
        queue_runtime = (root / "_finance_center_queue_runtime.py").read_text(encoding="utf-8")
        pages = (root / "_finance_center_pages.py").read_text(encoding="utf-8")
        self.assertIn("if self.import_queue.is_busy", queue_runtime)
        self.assertIn("def cancel_queue", queue_runtime)
        self.assertIn("self.import_queue.start_next()", queue_runtime)
        self.assertIn("Остановить очередь", pages)
        self.assertIn("Выбрать и запустить отчёты", pages)
        self.assertIn("Партия подтверждена выбором файлов", queue_runtime)


if __name__ == "__main__":
    unittest.main()
