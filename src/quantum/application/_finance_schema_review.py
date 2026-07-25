from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from quantum.application.finance_profile import FinanceProfileError
from quantum.pilot.universal_intake import classify_payload
from quantum.pilot.universal_tables import extract_tables
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
    inspection_status: str = "COMPLETE"
    diagnostic_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def confirmation_text(self) -> str:
        headers = " | ".join(self.headers)
        period = (
            f"{self.reporting_period_start or 'не задан'} — "
            f"{self.reporting_period_end or 'не задан'}"
        )
        details = ""
        if self.sheet_name is not None:
            details = (
                f"Лист: {self.sheet_name}\n"
                f"Строка заголовка: {self.header_row_index}\n"
                f"Столбцов: {self.column_count}\n"
                f"Строк данных: {self.data_row_count}\n"
                f"Период профиля: {period}\n"
                f"Заголовки: {headers}\n"
            )
        diagnostics = ""
        if self.diagnostic_codes:
            diagnostics = (
                "Диагностика строгой схемы: "
                + ", ".join(self.diagnostic_codes)
                + "\n"
            )
        if not self.requires_schema_review:
            return (
                f"Файл: {self.file_name}\n"
                f"Формат: {self.detected_format}\n"
                f"Размер: {self.file_size_bytes} байт\n"
                f"SHA-256: {self.file_sha256}\n"
                f"{details}{diagnostics}\n"
                "Файл передан в универсальную обработку. Неизвестные "
                "особенности формата фиксируются как диагностика и не "
                "блокируют доступные данные; значения не додумываются."
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


def _period(config: dict[str, Any], key: str) -> str | None:
    return str(config.get(key) or "") or None


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
    period_start = _period(config, "reporting_period_start")
    period_end = _period(config, "reporting_period_end")
    is_xlsx = detected in {"XLSX", "XLSM"}
    if not is_xlsx and decision.status != "ROUTE_XLSX":
        return SchemaReviewPreview(
            file_name=source_path.name,
            file_sha256=digest,
            file_size_bytes=len(payload),
            detected_format=detected,
            requires_schema_review=False,
            reporting_period_start=period_start,
            reporting_period_end=period_end,
            inspection_status="UNIVERSAL_INTAKE",
            diagnostic_codes=tuple(decision.reason_codes),
        )
    try:
        schema = discover_schema(payload=payload, limits=_limits(config))
    except Exception as exc:
        code = str(getattr(exc, "code", "SCHEMA_DISCOVERY_FAILED"))
        extraction = extract_tables(payload, source_name=source_path.name)
        if extraction.status.startswith("QUARANTINED"):
            raise FinanceProfileError(
                extraction.reason_codes[0] if extraction.reason_codes else code,
                tuple(extraction.reason_codes[1:]),
            ) from exc
        if not extraction.tables:
            raise FinanceProfileError(
                code,
                tuple(extraction.reason_codes) or (type(exc).__name__,),
            ) from exc
        table = extraction.tables[0]
        sheet_name = (
            table.member_path.rsplit("#", 1)[1]
            if "#" in table.member_path
            else None
        )
        diagnostics = tuple(
            dict.fromkeys(
                (
                    "STRICT_SCHEMA_PREVIEW_BYPASSED",
                    code,
                    *extraction.reason_codes,
                    *table.reason_codes,
                )
            )
        )
        return SchemaReviewPreview(
            file_name=source_path.name,
            file_sha256=digest,
            file_size_bytes=len(payload),
            detected_format=extraction.detected_format,
            requires_schema_review=False,
            sheet_name=sheet_name,
            header_row_index=1,
            headers=table.headers,
            column_count=table.column_count,
            data_row_count=table.row_count,
            formula_count=None,
            reporting_period_start=period_start,
            reporting_period_end=period_end,
            inspection_status="UNIVERSAL_FALLBACK",
            diagnostic_codes=diagnostics,
        )
    return SchemaReviewPreview(
        file_name=source_path.name,
        file_sha256=digest,
        file_size_bytes=len(payload),
        detected_format=detected,
        requires_schema_review=False,
        sheet_name=schema.sheet_name,
        header_row_index=schema.header_row_index,
        headers=schema.headers,
        column_count=schema.column_count,
        data_row_count=schema.data_row_count,
        formula_count=schema.formula_count,
        reporting_period_start=period_start,
        reporting_period_end=period_end,
        inspection_status="STRICT_SCHEMA_COMPLETE",
    )


__all__ = ["SchemaReviewPreview", "build_schema_review_preview"]
