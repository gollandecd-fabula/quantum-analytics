from __future__ import annotations

from datetime import date
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
import subprocess
import tempfile
import unittest
from unittest import mock

from quantum.application import scheduled_reports as sr


class FakeProfile:
    def __init__(self, marker: str = "v1") -> None:
        self.marker = marker

    def to_dict(self):
        return {"marker": self.marker, "confirmed": True}


class FakeResult:
    status = "CALCULATED"
    totals = {
        "net_sold_units": "2",
        "net_marketplace_income_amount": "680.00",
        "product_cost_amount": "800.00",
        "other_expense_amount": "80.00",
        "tax_amount": "120.00",
        "net_profit_amount": "-320.00",
        "profit_per_sold_unit": "-160.00",
    }
    missing_inputs = ()
    group_results = ()


def report_payload(report_id: str, start: str, end: str, digest: str):
    return {
        "file_sha256": digest,
        "source_bridge": {
            "source_type": "WB_DETAILED_FINANCIAL",
            "report_ids": [report_id],
            "report_periods": {
                report_id: {"date_from": start, "date_to": end}
            },
        },
    }


def restored(path: Path, report: dict, name: str = "source.xlsx"):
    row = SimpleNamespace(
        status="Готово",
        report=report,
        source_path=path,
        details={"original_source_name": name},
    )
    return SimpleNamespace(row=row)


class ScheduledPeriodTests(unittest.TestCase):
    def test_previous_completed_week(self):
        period = sr.completed_period("weekly", date(2026, 7, 24))
        self.assertEqual(period.start, date(2026, 7, 13))
        self.assertEqual(period.end, date(2026, 7, 19))
        self.assertEqual(period.key, "2026-W29")

    def test_previous_completed_month(self):
        period = sr.completed_period("monthly", date(2026, 7, 24))
        self.assertEqual(period.start, date(2026, 6, 1))
        self.assertEqual(period.end, date(2026, 6, 30))
        self.assertEqual(period.key, "2026-06")

    def test_unsupported_kind_fails(self):
        with self.assertRaisesRegex(sr.ScheduledReportError, "SCHEDULED_REPORT_KIND_UNSUPPORTED"):
            sr.completed_period("quarterly", date(2026, 7, 24))


class SourceSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def source(self, name: str, payload: bytes, report_id: str, start: str, end: str):
        path = self.root / name
        path.write_bytes(payload)
        digest = sha256(payload).hexdigest()
        return restored(path, report_payload(report_id, start, end, digest), name)

    def test_exact_week_coverage(self):
        period = sr.ScheduledPeriod("weekly", date(2026, 7, 13), date(2026, 7, 19))
        result = sr.select_sources(
            [self.source("week.xlsx", b"a", "r1", "2026-07-13", "2026-07-19")],
            period,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].intervals[0].report_id, "r1")

    def test_adjacent_partitions_cover_month(self):
        period = sr.ScheduledPeriod("monthly", date(2026, 6, 1), date(2026, 6, 30))
        result = sr.select_sources(
            [
                self.source("a.xlsx", b"a", "r1", "2026-06-01", "2026-06-15"),
                self.source("b.xlsx", b"b", "r2", "2026-06-16", "2026-06-30"),
            ],
            period,
        )
        self.assertEqual([item.source_name for item in result], ["a.xlsx", "b.xlsx"])

    def test_gap_fails_closed(self):
        period = sr.ScheduledPeriod("monthly", date(2026, 6, 1), date(2026, 6, 30))
        with self.assertRaisesRegex(sr.ScheduledReportError, "SCHEDULED_REPORT_PERIOD_GAP"):
            sr.select_sources(
                [
                    self.source("a.xlsx", b"a", "r1", "2026-06-01", "2026-06-14"),
                    self.source("b.xlsx", b"b", "r2", "2026-06-16", "2026-06-30"),
                ],
                period,
            )

    def test_overlap_fails_closed(self):
        period = sr.ScheduledPeriod("monthly", date(2026, 6, 1), date(2026, 6, 30))
        with self.assertRaisesRegex(sr.ScheduledReportError, "SCHEDULED_REPORT_PERIOD_OVERLAP"):
            sr.select_sources(
                [
                    self.source("a.xlsx", b"a", "r1", "2026-06-01", "2026-06-20"),
                    self.source("b.xlsx", b"b", "r2", "2026-06-20", "2026-06-30"),
                ],
                period,
            )

    def test_partial_period_fails_closed(self):
        period = sr.ScheduledPeriod("weekly", date(2026, 7, 13), date(2026, 7, 19))
        with self.assertRaisesRegex(sr.ScheduledReportError, "SCHEDULED_REPORT_PARTIAL_SOURCE_PERIOD"):
            sr.select_sources(
                [self.source("wide.xlsx", b"a", "r1", "2026-07-10", "2026-07-19")],
                period,
            )


class ScheduledRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "config").mkdir()
        self.config = self.root / "config" / "default-home-local.json"
        self.config.write_text(
            json.dumps(
                {
                    "tenant_id": "tenant-test",
                    "release_scope": "WB_ONLY",
                    "marketplace": "WILDBERRIES",
                    "marketplace_write_enabled": False,
                }
            ),
            encoding="utf-8",
        )
        self.source = self.root / "data" / "source.xlsx"
        self.source.parent.mkdir()
        self.source_bytes = b"verified-xlsx-bytes"
        self.source.write_bytes(self.source_bytes)
        self.digest = sha256(self.source_bytes).hexdigest()
        self.restored = restored(
            self.source,
            report_payload("r1", "2026-07-13", "2026-07-19", self.digest),
        )

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def fake_writer(output_dir: Path, result: FakeResult):
        run = output_dir / "Quantum_Run_test"
        run.mkdir(parents=True)
        outputs = {}
        for label, name in (
            ("JSON", "Quantum_Finance_test.json"),
            ("Recommendations", "Quantum_Recommendations_test.json"),
            ("Excel", "Quantum_Report_test.xlsx"),
            ("Dashboard", "Quantum_Dashboard_test.html"),
        ):
            path = run / name
            path.write_bytes((label + "-payload").encode("utf-8"))
            outputs[label] = path
        return outputs, (), ()

    def patches(self):
        return (
            mock.patch.object(sr, "load_profile", return_value=FakeProfile()),
            mock.patch.object(sr, "validate_profile", return_value=()),
            mock.patch.object(sr, "restore_reports", return_value=(self.restored,)),
            mock.patch.object(sr, "_read_finance_source", return_value=self.source_bytes),
            mock.patch.object(
                sr,
                "read_detailed_financial_rows_payload",
                return_value=[
                    {
                        "reportId": "r1",
                        "dateFrom": "2026-07-13",
                        "dateTo": "2026-07-19",
                    }
                ],
            ),
            mock.patch.object(sr, "calculate_by_group", return_value=FakeResult()),
            mock.patch.object(sr, "_write_finance_output_bundle", side_effect=self.fake_writer),
        )

    def test_atomic_generation_and_idempotent_reuse(self):
        patches = self.patches()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5] as calculate, patches[6]:
            first = sr.run_scheduled_report(
                project_root=self.root,
                config_path=self.config,
                kind="weekly",
                as_of=date(2026, 7, 24),
            )
            second = sr.run_scheduled_report(
                project_root=self.root,
                config_path=self.config,
                kind="weekly",
                as_of=date(2026, 7, 24),
            )
        self.assertEqual(first.status, "GENERATED")
        self.assertEqual(second.status, "REUSED")
        self.assertEqual(first.package_path, second.package_path)
        self.assertEqual(calculate.call_count, 1)
        manifest = sr.validate_package(first.package_path)
        self.assertFalse(manifest["marketplace_write_enabled"])
        self.assertEqual(manifest["release_scope"], "WB_ONLY")
        self.assertTrue((first.package_path / "Quantum_Summary.txt").is_file())

    def test_source_hash_change_fails_before_calculation(self):
        patches = list(self.patches())
        patches[3] = mock.patch.object(sr, "_read_finance_source", return_value=b"changed")
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5] as calculate, patches[6]:
            with self.assertRaisesRegex(sr.ScheduledReportError, "SCHEDULED_REPORT_SOURCE_HASH_MISMATCH"):
                sr.run_scheduled_report(
                    project_root=self.root,
                    config_path=self.config,
                    kind="weekly",
                    as_of=date(2026, 7, 24),
                )
        calculate.assert_not_called()

    def test_tampered_state_blocks_before_output(self):
        state = self.root / "data" / "scheduled-reports-state.json"
        state.write_text(
            json.dumps(
                {
                    "schema_version": sr.SCHEDULED_REPORT_STATE_SCHEMA_VERSION,
                    "events": [{"package_relative": "C:/outside"}],
                }
            ),
            encoding="utf-8",
        )
        patches = self.patches()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5] as calculate, patches[6]:
            with self.assertRaisesRegex(sr.ScheduledReportError, "SCHEDULED_REPORT_STATE_PATH_INVALID"):
                sr.run_scheduled_report(
                    project_root=self.root,
                    config_path=self.config,
                    kind="weekly",
                    as_of=date(2026, 7, 24),
                )
        calculate.assert_not_called()
        self.assertFalse((self.root / "output").exists())

    def test_portable_windows_and_unc_paths_are_rejected(self):
        for package_relative in (r"C:\\outside", r"\\\\server\share\report", "//server/share/report"):
            state = self.root / "data" / "scheduled-reports-state.json"
            state.write_text(
                json.dumps(
                    {
                        "schema_version": sr.SCHEDULED_REPORT_STATE_SCHEMA_VERSION,
                        "events": [{"package_relative": package_relative}],
                    }
                ),
                encoding="utf-8",
            )
            with self.subTest(package_relative=package_relative):
                with self.assertRaisesRegex(
                    sr.ScheduledReportError,
                    "SCHEDULED_REPORT_STATE_PATH_INVALID",
                ):
                    sr._load_state(self.root)

    def test_failed_new_revision_preserves_previous_package(self):
        patches = self.patches()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            first = sr.run_scheduled_report(
                project_root=self.root,
                config_path=self.config,
                kind="weekly",
                as_of=date(2026, 7, 24),
            )
        with (
            mock.patch.object(sr, "load_profile", return_value=FakeProfile("v2")),
            mock.patch.object(sr, "validate_profile", return_value=()),
            mock.patch.object(sr, "restore_reports", return_value=(self.restored,)),
            mock.patch.object(sr, "_read_finance_source", return_value=self.source_bytes),
            mock.patch.object(
                sr,
                "read_detailed_financial_rows_payload",
                return_value=[{"reportId": "r1", "dateFrom": "2026-07-13", "dateTo": "2026-07-19"}],
            ),
            mock.patch.object(sr, "calculate_by_group", return_value=FakeResult()),
            mock.patch.object(sr, "_write_finance_output_bundle", side_effect=OSError("disk")),
        ):
            with self.assertRaisesRegex(sr.ScheduledReportError, "SCHEDULED_REPORT_IO_FAILED"):
                sr.run_scheduled_report(
                    project_root=self.root,
                    config_path=self.config,
                    kind="weekly",
                    as_of=date(2026, 7, 24),
                )
        self.assertTrue(first.package_path.is_dir())
        sr.validate_package(first.package_path)


class WindowsTaskTests(unittest.TestCase):
    def test_registration_uses_daily_due_command_and_verifies(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "src").mkdir()
            config = root / "config.json"
            config.write_text("{}", encoding="utf-8")
            python = root / "python.exe"
            python.write_bytes(b"exe")
            calls = []

            def runner(args, **kwargs):
                calls.append((list(args), kwargs))
                return subprocess.CompletedProcess(args, 0, "ok", "")

            task = sr.register_windows_task(
                project_root=root,
                config_path=config,
                time_of_day="08:00",
                python_executable=python,
                runner=runner,
                platform_name="nt",
            )
            self.assertTrue(task.startswith("Quantum Scheduled Reports "))
            self.assertEqual(len(calls), 2)
            create = calls[0][0]
            self.assertIn("/SC", create)
            self.assertIn("DAILY", create)
            self.assertIn("/ST", create)
            self.assertIn("08:00", create)
            action = create[create.index("/TR") + 1]
            encoded = action.rsplit(" ", 1)[-1]
            decoded = __import__("base64").b64decode(encoded).decode("utf-16le")
            self.assertIn("quantum.application.scheduled_reports", decoded)
            self.assertIn("--kind due", decoded)
            self.assertIn(str(root.resolve()), decoded)
            self.assertNotIn("marketplace_write_enabled=True", decoded)
            self.assertEqual(calls[1][0][:3], ["schtasks.exe", "/Query", "/TN"])

    def test_non_windows_registration_fails(self):
        with self.assertRaisesRegex(sr.ScheduledReportError, "WINDOWS_TASK_SCHEDULER_REQUIRED"):
            sr.register_windows_task(
                project_root=Path.cwd(),
                config_path=Path(__file__),
                platform_name="posix",
            )


class UiContractTests(unittest.TestCase):
    def test_ui_keeps_exact_navigation_and_exposes_manual_schedule_actions(self):
        root = Path(__file__).resolve().parents[1]
        shared = (root / "src/quantum/application/_finance_center_shared.py").read_text(encoding="utf-8")
        pages = (root / "src/quantum/application/_finance_center_pages.py").read_text(encoding="utf-8")
        center = (root / "src/quantum/application/finance_center.py").read_text(encoding="utf-8")
        labels = [
            "Центр решений", "Аналитика", "Финансы", "Товары", "Реклама",
            "Склад и поставки", "Конкуренты", "SEO", "Аналитик AI", "Отчёты", "Настройки",
        ]
        for label in labels:
            self.assertIn(f'"{label}"', shared)
        self.assertIn("Сформировать недельный отчёт", pages)
        self.assertIn("Сформировать месячный отчёт", pages)
        self.assertIn("Включить расписание 08:00", pages)
        self.assertIn("FinanceCenterScheduledReportsMixin", center)


if __name__ == "__main__":
    unittest.main()
