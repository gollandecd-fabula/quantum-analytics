from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from quantum.application._finance_verified_rows import (
    read_detailed_financial_rows,
)
from quantum.application.finance_profile import FinanceProfileError
from tests.test_finance_center_profile import _workbook


class PlateauM3StorageIntegrityTests(unittest.TestCase):
    def _report(self, payload: bytes) -> dict[str, object]:
        return {
            "file_sha256": sha256(payload).hexdigest(),
            "source_bridge": {
                "report_ids": ["77"],
                "report_periods": {
                    "77": {
                        "date_from": "2026-07-01",
                        "date_to": "2026-07-07",
                    }
                },
            },
        }

    def test_verified_reader_reads_path_once_and_parses_same_payload(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "detailed.xlsx"
            _workbook(
                path,
                [
                    "Обоснование",
                    "Кол-во",
                    "Продажи/возвраты, ₽",
                    "К перечислению продавцу, ₽",
                ],
                [["Продажа", "1", "1000", "800"]],
            )
            report = self._report(path.read_bytes())
            original = Path.read_bytes
            calls: list[Path] = []

            def tracked(candidate: Path) -> bytes:
                calls.append(candidate)
                return original(candidate)

            with mock.patch.object(Path, "read_bytes", tracked):
                rows = read_detailed_financial_rows(path, report)

            self.assertEqual([path], calls)
            self.assertEqual("77", rows[0]["reportId"])
            self.assertEqual("Продажа", rows[0]["Обоснование"])

    def test_verified_reader_rejects_changed_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "detailed.xlsx"
            _workbook(
                path,
                [
                    "Обоснование",
                    "Кол-во",
                    "Продажи/возвраты, ₽",
                    "К перечислению продавцу, ₽",
                ],
                [["Продажа", "1", "1000", "800"]],
            )
            report = self._report(path.read_bytes())
            path.write_bytes(path.read_bytes() + b"tampered")
            with self.assertRaises(FinanceProfileError) as raised:
                read_detailed_financial_rows(path, report)
            self.assertEqual(
                "SOURCE_FILE_HASH_MISMATCH",
                raised.exception.code,
            )


if __name__ == "__main__":
    unittest.main()
