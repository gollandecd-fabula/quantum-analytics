from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path
from typing import Any

from quantum.application.finance_profile import (
    FinanceProfileError,
    read_detailed_financial_rows_payload,
)


def _expected_digest(report: Mapping[str, Any] | None) -> str | None:
    if not isinstance(report, Mapping):
        return None
    value = report.get("file_sha256")
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef"
        for character in normalized
    ):
        return None
    return normalized


def read_detailed_financial_rows(
    path: Path,
    report: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(path, Path) or not path.is_file():
        raise FinanceProfileError("XLSX_FILE_NOT_FOUND")
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise FinanceProfileError("XLSX_FILE_READ_FAILED") from exc
    actual = sha256(payload).hexdigest()
    expected = _expected_digest(report)
    if expected is not None and actual != expected:
        raise FinanceProfileError(
            "SOURCE_FILE_HASH_MISMATCH",
            (str(path),),
        )
    return read_detailed_financial_rows_payload(payload, report)


__all__ = ["read_detailed_financial_rows"]
