from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import queue
import tempfile
import threading
import unittest
from unittest import mock

from quantum.application._finance_schema_review import (
    build_schema_review_preview,
)
from quantum.application import _finance_center_queue_runtime as runtime
from quantum.application.local_app import ImportRow
from tests.test_finance_center_profile import _workbook


class _WorkerHarness(runtime.FinanceCenterQueueRuntimeMixin):
    def __init__(self, root: Path) -> None:
        self.project_root = root
        self.config_path = root / "config.json"
        self.cancel_event = threading.Event()
        self.process_lock = threading.Lock()
        self.active_process = None
        self.events: queue.Queue[tuple[str, str, object]] = queue.Queue()


class PlateauM4SchemaReviewTests(unittest.TestCase):
    def _config(self, path: Path) -> None:
        path.write_text(
            json.dumps(
                {
                    "reporting_period_start": "2026-07-01",
                    "reporting_period_end": "2026-07-07",
                    "inspection_policy": {
                        "limits": {
                            "max_file_bytes": 10485760,
                            "max_archive_entries": 1000,
                            "max_total_uncompressed_bytes": 52428800,
                            "max_entry_uncompressed_bytes": 10485760,
                            "max_compression_ratio": 100,
                            "max_xml_bytes": 10485760,
                            "max_rows": 10000,
                            "max_columns": 256,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

    def test_xlsx_preview_binds_visible_schema_period_and_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config.json"
            self._config(config)
            source = root / "report.xlsx"
            _workbook(
                source,
                [
                    "Артикул продавца",
                    "Обоснование",
                    "Кол-во",
                    "Продажи/возвраты, ₽",
                    "К перечислению продавцу, ₽",
                ],
                [["SKU-1", "Продажа", "1", "1000", "800"]],
            )
            preview = build_schema_review_preview(source, config)
            self.assertTrue(preview.requires_schema_review)
            self.assertEqual("Sheet1", preview.sheet_name)
            self.assertEqual(2, preview.header_row_index)
            self.assertEqual(5, preview.column_count)
            self.assertEqual(1, preview.data_row_count)
            self.assertEqual(
                sha256(source.read_bytes()).hexdigest(),
                preview.file_sha256,
            )
            text = preview.confirmation_text()
            self.assertIn("Артикул продавца", text)
            self.assertIn("2026-07-01 — 2026-07-07", text)
            self.assertIn(preview.file_sha256, text)

    def test_non_xlsx_file_never_receives_schema_attestation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config.json"
            self._config(config)
            source = root / "report.txt"
            source.write_text("plain text", encoding="utf-8")
            preview = build_schema_review_preview(source, config)
            self.assertFalse(preview.requires_schema_review)
            self.assertIsNone(preview.sheet_name)
            self.assertEqual((), preview.headers)

    def test_worker_forwards_only_row_bound_attestations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "selected.xlsx"
            managed = root / "data" / "managed.xlsx"
            source.write_bytes(b"selected-source")
            managed.parent.mkdir(parents=True)
            managed.write_bytes(source.read_bytes())
            digest = sha256(source.read_bytes()).hexdigest()
            row = ImportRow(
                row_id="report-1",
                source_path=source,
                size_text=str(source.stat().st_size),
                details={
                    "original_source_name": source.name,
                    "selected_file_sha256": digest,
                    "authority_attested": True,
                    "schema_reviewed": True,
                    "schema_preview": {"file_sha256": digest},
                },
            )
            imported = ImportRow(
                row_id="runtime",
                source_path=source,
                size_text=row.size_text,
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
            ) as run, mock.patch.object(
                runtime,
                "managed_source_path",
                return_value=managed,
            ), mock.patch.object(
                runtime,
                "detect_products_from_xlsx",
                return_value=(),
            ):
                harness._worker(row)
            self.assertTrue(run.call_args.kwargs["authority_attested"])
            self.assertTrue(run.call_args.kwargs["schema_reviewed"])


if __name__ == "__main__":
    unittest.main()
