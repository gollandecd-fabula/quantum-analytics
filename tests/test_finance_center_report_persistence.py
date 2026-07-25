from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from quantum.application._finance_center_calculation import (
    FinanceCenterCalculationMixin,
)
from quantum.application import _finance_center_persistence as persistence
from quantum.application._finance_center_persistence import (
    LEGACY_REPORT_INDEX_SCHEMA_VERSION,
    REPORT_INDEX_RELATIVE_PATH,
    REPORT_INDEX_SCHEMA_VERSION,
    managed_source_path,
    restore_reports,
    save_report_index,
)
from quantum.application._finance_center_shared import ReportState
from quantum.application.local_app import ImportRow


class FinanceCenterReportPersistenceTests(unittest.TestCase):
    def _config(self, root: Path) -> Path:
        path = root / "config" / "default-home-local.json"
        path.parent.mkdir(parents=True)
        path.write_text(
            json.dumps(
                {
                    "configuration_status": "READY",
                    "execution_mode": "ADMISSION_ONLY",
                    "tenant_id": "tenant-home-local",
                }
            ),
            encoding="utf-8",
        )
        return path

    def _persisted_report(
        self,
        root: Path,
        config: Path,
    ) -> tuple[Path, Path, dict[str, object]]:
        payload = b"not-a-real-xlsx-but-immutable"
        digest = sha256(payload).hexdigest()
        dataset_id = "dataset-persistence-test"
        tenant_token = sha256(b"tenant-home-local").hexdigest()
        source = (
            root
            / "data"
            / "pilot-zones"
            / tenant_token
            / "admitted"
            / dataset_id
            / digest
        )
        source.parent.mkdir(parents=True)
        source.write_bytes(payload)
        report = {
            "status": "ADMISSION_COMPLETE",
            "dataset_id": dataset_id,
            "raw_file_id": "00000000-0000-0000-0000-000000000001",
            "file_sha256": digest,
            "file_size_bytes": len(payload),
            "sanitized_filename": "wb-detailed.xlsx",
            "source_bridge": {
                "status": "SOURCE_BRIDGE_COMPLETE",
                "source_type": "WB_DETAILED_FINANCIAL",
            },
        }
        output = root / "output" / "pilot_gui_20260714_010203.json"
        output.parent.mkdir(parents=True)
        output.write_text(json.dumps(report), encoding="utf-8")
        return source, output, report

    def _row(
        self,
        source: Path,
        output: Path,
        report: dict[str, object],
    ) -> ImportRow:
        return ImportRow(
            row_id="one",
            source_path=source,
            size_text="28 Б",
            output_path=output,
            status="Готово",
            detected_format="WB_DETAILED_FINANCIAL",
            progress="100%",
            report=report,
            details={
                "original_source_name": "wb-detailed.xlsx",
                "original_source_path": "C:/Users/private/secret/report.xlsx",
            },
        )

    def test_managed_source_is_recovered_without_original_upload_path(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            source, _output, report = self._persisted_report(root, config)
            restored = managed_source_path(
                root,
                config,
                report,
                Path(directory) / "deleted-original.xlsx",
            )
            self.assertEqual(source.resolve(), restored)

    def test_external_original_path_is_never_a_durable_source(self) -> None:
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as external:
            root = Path(project)
            config = self._config(root)
            payload = b"external"
            outside = Path(external) / "private.xlsx"
            outside.write_bytes(payload)
            report = {"file_sha256": sha256(payload).hexdigest()}
            self.assertIsNone(
                managed_source_path(root, config, report, outside)
            )

    def test_report_history_is_restored_after_application_restart(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            source, output, _report = self._persisted_report(root, config)
            restored = restore_reports(root, config)
            self.assertEqual(1, len(restored))
            row = restored[0].row
            self.assertEqual(source.resolve(), row.source_path)
            self.assertEqual(output.resolve(), row.output_path)
            self.assertEqual("WB_DETAILED_FINANCIAL", row.detected_format)
            self.assertEqual("Готово", row.status)
            self.assertTrue(row.details["restored"])
            self.assertTrue(row.details["managed_source_available"])

    def test_report_index_v2_contains_only_portable_internal_paths(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            source, output, report = self._persisted_report(root, config)
            path = save_report_index(
                root,
                (self._row(source, output, report),),
            )
            payload = json.loads(path.read_text(encoding="utf-8"))
            item = payload["reports"][0]
            self.assertEqual(
                REPORT_INDEX_SCHEMA_VERSION,
                payload["schema_version"],
            )
            self.assertTrue(
                path.samefile(root / REPORT_INDEX_RELATIVE_PATH)
            )
            self.assertNotIn("source_path", item)
            self.assertNotIn("original_source_path", json.dumps(payload))
            self.assertFalse(Path(item["managed_source_path"]).is_absolute())
            self.assertFalse(Path(item["output_path"]).is_absolute())
            self.assertNotIn("private", json.dumps(payload).casefold())

    def test_legacy_absolute_source_path_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as external:
            root = Path(directory)
            config = self._config(root)
            source, output, report = self._persisted_report(root, config)
            source.unlink()
            outside = Path(external) / "legacy.xlsx"
            outside.write_bytes(b"not-a-real-xlsx-but-immutable")
            index = root / REPORT_INDEX_RELATIVE_PATH
            index.write_text(
                json.dumps(
                    {
                        "schema_version": LEGACY_REPORT_INDEX_SCHEMA_VERSION,
                        "reports": [
                            {
                                "file_sha256": report["file_sha256"],
                                "output_path": str(output.relative_to(root)),
                                "source_path": str(outside),
                                "source_name": "legacy.xlsx",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            restored = restore_reports(root, config)
            self.assertEqual(1, len(restored))
            self.assertEqual("Недоступен", restored[0].row.status)
            self.assertNotEqual(outside.resolve(), restored[0].row.source_path)

    def test_corrupt_index_falls_back_to_verified_output_scan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            source, _output, _report = self._persisted_report(root, config)
            index = root / REPORT_INDEX_RELATIVE_PATH
            index.write_text("{broken", encoding="utf-8")
            restored = restore_reports(root, config)
            self.assertEqual(1, len(restored))
            self.assertEqual(source.resolve(), restored[0].row.source_path)

    def test_transient_replace_lock_is_retried(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            source, output, report = self._persisted_report(root, config)
            real_replace = os.replace
            calls: list[tuple[object, object]] = []

            def flaky_replace(source_path, target_path):
                calls.append((source_path, target_path))
                if len(calls) == 1:
                    raise PermissionError("transient lock")
                return real_replace(source_path, target_path)

            with mock.patch.object(
                persistence.os,
                "replace",
                side_effect=flaky_replace,
            ), mock.patch.object(persistence.time, "sleep") as sleep:
                save_report_index(
                    root,
                    (self._row(source, output, report),),
                )
            self.assertEqual(2, len(calls))
            sleep.assert_called_once()

    def test_failed_replace_preserves_previous_index(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            source, output, report = self._persisted_report(root, config)
            target = root / REPORT_INDEX_RELATIVE_PATH
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('{"sentinel":"preserve"}', encoding="utf-8")
            with mock.patch.object(
                persistence.os,
                "replace",
                side_effect=PermissionError("locked"),
            ), mock.patch.object(persistence.time, "sleep"):
                with self.assertRaises(PermissionError):
                    save_report_index(
                        root,
                        (self._row(source, output, report),),
                    )
            self.assertEqual(
                {"sentinel": "preserve"},
                json.loads(target.read_text(encoding="utf-8")),
            )
            self.assertEqual([], list(target.parent.glob("*.tmp")))

    def test_detailed_report_uses_restored_managed_source_and_ignores_missing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            available = root / "available.xlsx"
            available.write_bytes(b"x")
            report = {
                "source_bridge": {
                    "source_type": "WB_DETAILED_FINANCIAL"
                }
            }
            missing_row = ImportRow(
                row_id="missing",
                source_path=root / "missing.xlsx",
                size_text="—",
                status="Недоступен",
                detected_format="WB_DETAILED_FINANCIAL",
                report=report,
            )
            available_row = ImportRow(
                row_id="available",
                source_path=available,
                size_text="1 Б",
                status="Готово",
                detected_format="WB_DETAILED_FINANCIAL",
                report=report,
            )
            harness = FinanceCenterCalculationMixin()
            harness.reports = {
                "missing": ReportState(missing_row),
                "available": ReportState(available_row),
            }
            self.assertIs(available_row, harness._detailed_report())

    def test_shell_restores_reports_before_first_finance_refresh(self) -> None:
        root = Path(__file__).resolve().parents[1]
        shell = (
            root
            / "src"
            / "quantum"
            / "application"
            / "_finance_center_shell.py"
        ).read_text(encoding="utf-8")
        restore = shell.index("self.restore_persisted_reports()")
        refresh = shell.index("self.refresh_finance_summary()")
        self.assertLess(restore, refresh)


if __name__ == "__main__":
    unittest.main()
