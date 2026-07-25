from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from quantum.application.finance_profile import FinanceProfileError
from quantum.pilot.universal_intake import classify_payload
from quantum.pilot.windows_runner import discover_schema, _limits


@dataclass(frozen=True, slots=True)
class SchemaReviewPreview:
    file_name: str
    file_sha256: str
    file_size_bytes: int
    detected_format: str
    requires_schema_review: bool
    sheet_name: str | None = None
    header_row_index: int | None = None
    headers: tuple[str, ...] = ()
    column_count: int | None = None
    data_row_count: int | None = None
    formula_count: int | None = None
    reporting_period_start: str | None = None
    reporting_period_end: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def confirmation_text(self) -> str:
        if not self.requires_schema_review:
            return (
                f"Файл: {self.file_name}\n"
                f"Формат: {self.detected_format}\n"
                f"Размер: {self.file_size_bytes} байт\n"
                f"SHA-256: {self.file_sha256}\n\n"
                "Для этого формата проверка табличной схемы не требуется."
            )
        headers = " | ".join(self.headers)
        period = (
            f"{self.reporting_period_start or 'не задан'} — "
            f"{self.reporting_period_end or 'не задан'}"
        )
        return (
            f"Файл: {self.file_name}\n"
            f"Формат: {self.detected_format}\n"
            f"Лист: {self.sheet_name}\n"
            f"Строка заголовка: {self.header_row_index}\n"
            f"Столбцов: {self.column_count}\n"
            f"Строк данных: {self.data_row_count}\n"
            f"Формул: {self.formula_count}\n"
            f"Период профиля: {period}\n"
            f"SHA-256: {self.file_sha256}\n\n"
            f"Заголовки:\n{headers}\n\n"
            "Подтвердите, что лист, заголовки и период соответствуют "
            "выбранному отчёту."
        )


def _config(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FinanceProfileError(
            "SCHEMA_REVIEW_CONFIG_READ_FAILED",
            (type(exc).__name__,),
        ) from exc
    if not isinstance(value, dict):
        raise FinanceProfileError("SCHEMA_REVIEW_CONFIG_INVALID")
    return value


def build_schema_review_preview(
    source_path: Path,
    config_path: Path,
) -> SchemaReviewPreview:
    if not isinstance(source_path, Path) or not source_path.is_file():
        raise FinanceProfileError("SCHEMA_REVIEW_FILE_NOT_FOUND")
    try:
        payload = source_path.read_bytes()
    except OSError as exc:
        raise FinanceProfileError(
            "SCHEMA_REVIEW_FILE_READ_FAILED",
            (type(exc).__name__,),
        ) from exc
    if not payload:
        raise FinanceProfileError("SCHEMA_REVIEW_FILE_EMPTY")
    digest = sha256(payload).hexdigest()
    decision = classify_payload(payload, source_path.suffix)
    detected = str(decision.detected_format or "UNKNOWN")
    config = _config(config_path)
    if decision.status != "ROUTE_XLSX":
        return SchemaReviewPreview(
            file_name=source_path.name,
            file_sha256=digest,
            file_size_bytes=len(payload),
            detected_format=detected,
            requires_schema_review=False,
            reporting_period_start=str(
                config.get("reporting_period_start") or ""
            )
            or None,
            reporting_period_end=str(
                config.get("reporting_period_end") or ""
            )
            or None,
        )
    try:
        schema = discover_schema(
            payload=payload,
            limits=_limits(config),
        )
    except Exception as exc:
        code = getattr(exc, "code", "SCHEMA_DISCOVERY_FAILED")
        raise FinanceProfileError(str(code), (type(exc).__name__,)) from exc
    return SchemaReviewPreview(
        file_name=source_path.name,
        file_sha256=digest,
        file_size_bytes=len(payload),
        detected_format="XLSX",
        requires_schema_review=True,
        sheet_name=schema.sheet_name,
        header_row_index=schema.header_row_index,
        headers=schema.headers,
        column_count=schema.column_count,
        data_row_count=schema.data_row_count,
        formula_count=schema.formula_count,
        reporting_period_start=str(
            config.get("reporting_period_start") or ""
        )
        or None,
        reporting_period_end=str(
            config.get("reporting_period_end") or ""
        )
        or None,
    )


__all__ = ["SchemaReviewPreview", "build_schema_review_preview"]
