from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import queue
import tempfile
import threading
import unittest
from unittest import mock

from quantum.application import _finance_center_queue_runtime as runtime
from quantum.application._finance_center_queue import SequentialImportQueue
from quantum.application._finance_center_reports import FinanceCenterReportsMixin
from quantum.application.finance_center import QuantumFinanceCenter
from quantum.application.local_app import ImportRow


class _WorkerHarness(runtime.FinanceCenterQueueRuntimeMixin):
    def __init__(self, root: Path) -> None:
        self.project_root = root
        self.config_path = root / "config.json"
        self.cancel_event = threading.Event()
        self.process_lock = threading.Lock()
        self.active_process = None
        self.events: queue.Queue[tuple[str, str, object]] = queue.Queue()


class PlateauM1RuntimeIntegrationTests(unittest.TestCase):
    def test_live_runtime_methods_have_single_owner(self) -> None:
        expected_module = "quantum.application._finance_center_queue_runtime"
        for name in (
            "add_reports",
            "_worker",
            "_drain_events",
            "repeat_selected",
        ):
            with self.subTest(name=name):
                self.assertEqual(
                    expected_module,
                    getattr(QuantumFinanceCenter, name).__module__,
                )
                self.assertNotIn(name, FinanceCenterReportsMixin.__dict__)

    def test_restored_report_can_be_queued_again(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "managed-source.xlsx"
            source.write_bytes(b"managed")
            import_queue = SequentialImportQueue()
            self.assertTrue(
                import_queue.enqueue_existing("restored-1", source)
            )
            self.assertEqual("restored-1", import_queue.start_next())
            import_queue.complete("restored-1")
            self.assertTrue(
                import_queue.enqueue_existing("restored-1", source)
            )

    def test_worker_switches_to_verified_managed_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "selected.xlsx"
            managed = root / "data" / "managed.xlsx"
            source.write_bytes(b"selected-source")
            managed.parent.mkdir(parents=True)
            managed.write_bytes(source.read_bytes())
            digest = sha256(source.read_bytes()).hexdigest()
            input_row = ImportRow(
                row_id="report-1",
                source_path=source,
                size_text=str(source.stat().st_size),
                details={
                    "original_source_name": source.name,
                    "selected_file_sha256": digest,
                },
            )
            imported = ImportRow(
                row_id="runtime",
                source_path=source,
                size_text=input_row.size_text,
                status="Готово",
                progress="100%",
                report={"file_sha256": digest},
                details={},
            )
            harness = _WorkerHarness(root)
            with mock.patch.object(
                runtime,
                "run_import",
                return_value=imported,
            ), mock.patch.object(
                runtime,
                "managed_source_path",
                return_value=managed,
            ) as resolve_managed, mock.patch.object(
                runtime,
                "detect_products_from_xlsx",
                return_value=(),
            ) as detect_products:
                harness._worker(input_row)

            event, row_id, payload = harness.events.get_nowait()
            result, products = payload
            self.assertEqual("done", event)
            self.assertEqual("report-1", row_id)
            self.assertEqual(managed, result.source_path)
            self.assertEqual((), products)
            self.assertEqual(
                str(managed),
                result.details["managed_source_path"],
            )
            resolve_managed.assert_called_once_with(
                root,
                root / "config.json",
                imported.report,
                None,
            )
            detect_products.assert_called_once_with(managed)

    def test_worker_rejects_source_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "selected.xlsx"
            source.write_bytes(b"selected-source")
            selected_digest = sha256(source.read_bytes()).hexdigest()
            input_row = ImportRow(
                row_id="report-1",
                source_path=source,
                size_text=str(source.stat().st_size),
                details={"selected_file_sha256": selected_digest},
            )
            imported = ImportRow(
                row_id="runtime",
                source_path=source,
                size_text=input_row.size_text,
                status="Готово",
                progress="100%",
                report={"file_sha256": "0" * 64},
                details={},
            )
            harness = _WorkerHarness(root)
            with mock.patch.object(
                runtime,
                "run_import",
                return_value=imported,
            ), mock.patch.object(
                runtime,
                "managed_source_path",
            ) as resolve_managed:
                harness._worker(input_row)

            _event, _row_id, payload = harness.events.get_nowait()
            result, _products = payload
            self.assertEqual("Ошибка", result.status)
            self.assertEqual(
                "SOURCE_FILE_CHANGED_DURING_IMPORT",
                result.error,
            )
            resolve_managed.assert_not_called()


if __name__ == "__main__":
    unittest.main()
