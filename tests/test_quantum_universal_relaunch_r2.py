from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
import unittest

from quantum.application._finance_center_auto_inbox import (
    AutoInboxController,
    _SUPPORTED_SUFFIXES,
)
from quantum.pilot.universal_intake import classify_payload, register_file
from quantum.pilot.universal_tables import extract_tables


ROOT = Path(__file__).resolve().parents[1]
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


class _FakeCell:
    def __init__(self, value: object, cell_type: int) -> None:
        self.value = value
        self.ctype = cell_type


class _FakeSheet:
    def __init__(self, name: str, rows: list[list[_FakeCell]]) -> None:
        self.name = name
        self._rows = rows
        self.nrows = len(rows)
        self.ncols = max((len(row) for row in rows), default=0)

    def cell(self, row: int, column: int) -> _FakeCell:
        if column >= len(self._rows[row]):
            return _FakeCell("", 0)
        return self._rows[row][column]


class _FakeWorkbook:
    def __init__(self, sheets: list[_FakeSheet]) -> None:
        self._sheets = sheets
        self.nsheets = len(sheets)
        self.datemode = 0
        self.released = False

    def sheet_by_index(self, index: int) -> _FakeSheet:
        return self._sheets[index]

    def release_resources(self) -> None:
        self.released = True


@contextmanager
def _fake_xlrd(*, failure: Exception | None = None):
    module = ModuleType("xlrd")
    module.XL_CELL_EMPTY = 0
    module.XL_CELL_TEXT = 1
    module.XL_CELL_NUMBER = 2
    module.XL_CELL_DATE = 3
    module.XL_CELL_BOOLEAN = 4
    module.XL_CELL_ERROR = 5
    module.XL_CELL_BLANK = 6
    module.xldate_as_datetime = lambda value, datemode: datetime(2026, 7, int(value))
    rows = [
        [_FakeCell("Артикул", 1), _FakeCell("Продажи", 1)],
        [_FakeCell("IZ001", 1), _FakeCell(12.0, 2)],
        [_FakeCell("IZ002", 1), _FakeCell(7.5, 2)],
    ]
    workbook = _FakeWorkbook(
        [
            _FakeSheet("Продажи", rows),
            _FakeSheet("Пусто", [[_FakeCell("one", 1)]]),
        ]
    )

    def open_workbook(**kwargs):
        if failure is not None:
            raise failure
        if kwargs.get("formatting_info") is not False:
            raise AssertionError("formatting_info must be disabled")
        if kwargs.get("on_demand") is not True:
            raise AssertionError("on_demand must be enabled")
        return workbook

    module.open_workbook = open_workbook
    previous = sys.modules.get("xlrd")
    sys.modules["xlrd"] = module
    try:
        yield workbook
    finally:
        if previous is None:
            sys.modules.pop("xlrd", None)
        else:
            sys.modules["xlrd"] = previous


class QuantumUniversalRelaunchR2Tests(unittest.TestCase):
    def test_content_first_xls_extracts_passive_biff_rows(self) -> None:
        payload = OLE_MAGIC + b"passive-biff-workbook"
        with _fake_xlrd() as workbook:
            result = extract_tables(payload, source_name="renamed.bin")
        self.assertEqual(result.status, "COMPLETE")
        self.assertEqual(result.detected_format, "XLS")
        self.assertEqual(len(result.tables), 1)
        table = result.tables[0]
        self.assertEqual(table.member_path, "renamed.bin#Продажи")
        self.assertEqual(table.rows[0]["Артикул"], "IZ001")
        self.assertEqual(table.rows[0]["Продажи"], "12")
        self.assertIn("XLS_PASSIVE_BIFF_PARSE", table.reason_codes)
        self.assertTrue(workbook.released)

    def test_xls_classification_and_registration_do_not_depend_on_suffix(self) -> None:
        payload = OLE_MAGIC + b"passive-biff-workbook"
        with _fake_xlrd():
            decision = classify_payload(payload, ".dat")
        self.assertEqual(decision.status, "ACCEPTED_PARTIAL")
        self.assertEqual(decision.detected_format, "XLS")
        self.assertEqual(decision.route, "UNIVERSAL_TABLES")
        with TemporaryDirectory() as directory, _fake_xlrd():
            root = Path(directory)
            source = root / "sales.dat"
            source.write_bytes(payload)
            report = register_file(file_path=source, storage_root=root / "storage")
        self.assertEqual(report["status"], "ACCEPTED_PARTIAL")
        self.assertEqual(report["detected_format"], "XLS")
        self.assertEqual(report["universal_extraction"]["table_count"], 1)
        self.assertFalse(report["marketplace_write_enabled"])

    def test_encrypted_xls_is_quarantined(self) -> None:
        with _fake_xlrd(failure=RuntimeError("Workbook is encrypted")):
            decision = classify_payload(OLE_MAGIC + b"encrypted", ".xls")
        self.assertEqual(decision.status, "QUARANTINED_SECURITY")
        self.assertIn("XLS_ENCRYPTED", decision.reason_codes)

    def test_auto_inbox_admits_all_declared_safe_front_door_suffixes(self) -> None:
        for suffix in (
            ".xls", ".xlsx", ".xlsm", ".csv", ".tsv", ".json", ".xml",
            ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
        ):
            self.assertIn(suffix, _SUPPORTED_SUFFIXES)
        with TemporaryDirectory() as directory:
            controller = AutoInboxController(
                Path(directory), minimum_age_seconds=0, stable_scans_required=2
            )
            path = controller.incoming_dir / "report.xls"
            path.write_bytes(b"data")
            now = path.stat().st_mtime_ns + 1
            self.assertEqual(controller.scan(now_ns=now), ())
            ready = controller.scan(now_ns=now + 1)
        self.assertEqual([item.path.name for item in ready], ["report.xls"])

    def test_package_launcher_self_detects_and_forwards_arguments(self) -> None:
        builder = (ROOT / "scripts/windows/build_local_production.ps1").read_text()
        self.assertNotIn('-PackageRoot "%~dp0"', builder)
        self.assertIn('one_click_home_local.ps1" %*', builder)
        self.assertIn('for %%I in ("%~dp0.") do set "QUANTUM_ROOT=%%~fI"', builder)

    def test_installed_launcher_remains_explicit_and_repeatable(self) -> None:
        installer = (ROOT / "scripts/windows/install_home_local.ps1").read_text()
        self.assertIn('-InstalledRoot "%QUANTUM_ROOT%" -SkipInstall %*', installer)
        self.assertIn('Quantum Decision Center.lnk', installer)
        self.assertIn('$candidateNames = @($primaryName, $fallbackName)', installer)
        self.assertIn('SHORTCUT_VERIFICATION_FAILED', installer)

    def test_default_output_names_are_collision_resistant(self) -> None:
        for relative in (
            "scripts/windows/import_source.ps1",
            "src/quantum/pilot/import_xlsx_source.ps1",
        ):
            script = (ROOT / relative).read_text()
            self.assertIn('yyyyMMdd_HHmmss_fff', script, relative)
            self.assertIn('[guid]::NewGuid()', script, relative)
            self.assertNotIn('Get-Date -Format "yyyyMMdd_HHmmss"))', script, relative)

    def test_windows_requirements_pin_xlrd_with_hash(self) -> None:
        requirements = (ROOT / "requirements/windows-home-local.txt").read_text()
        self.assertIn("xlrd==2.0.2", requirements)
        self.assertIn(
            "sha256:ea762c3d29f4cca48d82df517b6d89fbce4db3107f9d78713e48cd321d5c9aa9",
            requirements,
        )


if __name__ == "__main__":
    unittest.main()
