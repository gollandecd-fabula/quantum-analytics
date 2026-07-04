import json
import os
import tempfile
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from unittest import mock

from quantum.ingestion import _xlsx_relationships_core
from quantum.ingestion._xlsx_contracts import (
    XlsxInspectionError,
    XlsxInspectionPolicy,
)
from quantum.ingestion._xlsx_inspection_v3 import XlsxPackageInspector
from quantum.pilot import local_runner as public_engine
from quantum.pilot.windows_runner import (
    _atomic_bytes,
    _workbook_target_compatible,
    apply_discovered_schema,
    discover_schema,
    install_windows_compatibility,
)
from tests.p16_fixtures import build_xlsx, policy, rewrite_xlsx_part


def _realistic_workbook() -> bytes:
    workbook = build_xlsx(
        headers=("Артикул", "Количество продаж", "Сумма продаж"),
        rows=(("SKU-1", "2", "1990.00"),),
    )
    workbook = rewrite_xlsx_part(
        workbook,
        "xl/workbook.xml",
        lambda payload: payload.replace(b'name="Sheet1"', 'name="Документы"'.encode()),
    )
    workbook = rewrite_xlsx_part(
        workbook,
        "xl/_rels/workbook.xml.rels",
        lambda payload: payload.replace(
            b'Target="worksheets/sheet1.xml"',
            b'Target="/xl/worksheets/sheet1.xml"',
        ),
    )

    def shift_rows(payload: bytes) -> bytes:
        text = payload.decode("utf-8")
        replacements = (
            ('r="2"', 'r="5"'),
            ('A2', 'A5'),
            ('B2', 'B5'),
            ('C2', 'C5'),
            ('r="1"', 'r="4"'),
            ('A1', 'A4'),
            ('B1', 'B4'),
            ('C1', 'C4'),
        )
        for old, new in replacements:
            text = text.replace(old, new)
        return text.encode("utf-8")

    return rewrite_xlsx_part(
        workbook,
        "xl/worksheets/sheet1.xml",
        shift_rows,
    )


class WindowsCompatibilityActivationTests(unittest.TestCase):
    def test_public_engine_uses_windows_atomic_write(self):
        self.assertIs(public_engine._atomic_bytes, _atomic_bytes)

    def test_ingestion_core_uses_compatible_relationship_resolver(self):
        self.assertIs(
            _xlsx_relationships_core._workbook_target,
            _workbook_target_compatible,
        )


class WindowsAtomicWriteTests(unittest.TestCase):
    def test_replace_occurs_after_temporary_handle_is_closed(self):
        original_named = tempfile.NamedTemporaryFile
        original_replace = os.replace
        state = {}

        class TrackedContext:
            def __init__(self, *args, **kwargs):
                self._context = original_named(*args, **kwargs)
                self.handle = None

            def __enter__(self):
                self.handle = self._context.__enter__()
                state["handle"] = self.handle
                return self.handle

            def __exit__(self, exc_type, exc, tb):
                return self._context.__exit__(exc_type, exc, tb)

        def checked_replace(source, destination):
            self.assertTrue(state["handle"].closed)
            return original_replace(source, destination)

        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "output.json"
            with mock.patch(
                "quantum.pilot.windows_runner.tempfile.NamedTemporaryFile",
                side_effect=lambda *args, **kwargs: TrackedContext(*args, **kwargs),
            ), mock.patch(
                "quantum.pilot.windows_runner.os.replace",
                side_effect=checked_replace,
            ):
                _atomic_bytes(target, b"payload")
            self.assertEqual(target.read_bytes(), b"payload")


class WorkbookTargetCompatibilityTests(unittest.TestCase):
    def test_package_root_targets_are_supported(self):
        self.assertEqual(
            _workbook_target_compatible("/xl/styles.xml"),
            "xl/styles.xml",
        )
        self.assertEqual(
            _workbook_target_compatible("/xl/worksheets/sheet1.xml"),
            "xl/worksheets/sheet1.xml",
        )
        self.assertEqual(
            _workbook_target_compatible("worksheets/sheet1.xml"),
            "xl/worksheets/sheet1.xml",
        )

    def test_unsafe_targets_remain_rejected(self):
        for target in (
            "../styles.xml",
            "/../styles.xml",
            "//server/share.xml",
            "https://example.invalid/report.xml",
            "C:/report.xml",
        ):
            with self.subTest(target=target):
                with self.assertRaises(XlsxInspectionError):
                    _workbook_target_compatible(target)


class HomeLocalDiscoveryTests(unittest.TestCase):
    def test_discovers_non_default_sheet_and_header_row(self):
        workbook = _realistic_workbook()
        base_policy = policy(headers=("x", "y", "z"))
        candidate = discover_schema(
            payload=workbook,
            limits=base_policy.limits,
        )
        self.assertEqual(candidate.sheet_name, "Документы")
        self.assertEqual(candidate.header_row_index, 4)
        self.assertEqual(candidate.column_count, 3)
        self.assertEqual(candidate.data_row_count, 1)
        self.assertEqual(candidate.headers[0], "Артикул")

    def test_discovered_schema_passes_strict_inspection(self):
        workbook = _realistic_workbook()
        base_policy = policy(headers=("x", "y", "z"))
        candidate = discover_schema(
            payload=workbook,
            limits=base_policy.limits,
        )
        template = base_policy.schemas[0]
        schema = replace(
            template,
            sheet_name=candidate.sheet_name,
            sheet_count=candidate.sheet_count,
            header_row_index=candidate.header_row_index,
            header_sha256=candidate.header_sha256,
            column_count=candidate.column_count,
            min_data_rows=0,
            max_data_rows=max(template.max_data_rows, candidate.data_row_count),
            max_formula_count=max(template.max_formula_count, candidate.formula_count),
        )
        discovered_policy = XlsxInspectionPolicy(
            policy_id=base_policy.policy_id,
            version=base_policy.version,
            limits=base_policy.limits,
            schemas=(schema,),
            prohibited_header_tokens=base_policy.prohibited_header_tokens,
        )
        install_windows_compatibility()
        inspection = XlsxPackageInspector().inspect(
            payload=workbook,
            policy=discovered_policy,
        )
        self.assertTrue(inspection.matched)
        self.assertEqual(inspection.sheet_name, "Документы")
        self.assertEqual(inspection.header_row_index, 4)

    def test_runtime_config_is_updated_without_mutating_source(self):
        base = {
            "inspection_policy": json.loads(json.dumps(asdict(policy()))),
            "expected_row_count": 999,
        }
        original = json.loads(json.dumps(base))
        candidate = discover_schema(
            payload=_realistic_workbook(),
            limits=policy().limits,
        )
        updated = apply_discovered_schema(base, candidate)
        self.assertEqual(base, original)
        schema = updated["inspection_policy"]["schemas"][0]
        self.assertEqual(schema["sheet_name"], "Документы")
        self.assertEqual(schema["header_row_index"], 4)
        self.assertEqual(updated["expected_row_count"], 1)


if __name__ == "__main__":
    unittest.main()
