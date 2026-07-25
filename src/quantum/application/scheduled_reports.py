from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Iterable, Mapping, Sequence

from quantum.adapters.wildberries.detailed_financial import _ALIASES
from quantum.application._finance_center_calculation import (
    _read_finance_source,
    _write_finance_output_bundle,
)
from quantum.application._finance_center_persistence import restore_reports
from quantum.application._finance_profile_financial_rows import (
    read_detailed_financial_rows_payload,
)
from quantum.application.finance_profile import (
    FinanceProfile,
    FinanceProfileError,
    FinanceRunResult,
    calculate_by_group,
    load_profile,
    validate_profile,
)


SCHEDULED_REPORT_SCHEMA_VERSION = "quantum-scheduled-report-v1"
SCHEDULED_REPORT_STATE_SCHEMA_VERSION = "quantum-scheduled-report-state-v1"
SCHEDULED_REPORT_POINTER_SCHEMA_VERSION = "quantum-scheduled-report-pointer-v1"
SUPPORTED_REPORT_KINDS = frozenset({"weekly", "monthly"})
_MAX_STATE_BYTES = 2 * 1024 * 1024
_MAX_EVENTS = 200
_MAX_MANIFEST_BYTES = 2 * 1024 * 1024
_LOCK_STALE_SECONDS = 4 * 60 * 60
_HASH = re.compile(r"^[0-9a-f]{64}$")
_TIME = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
_WINDOWS_DRIVE_PATH = re.compile(r"^[A-Za-z]:[\\/]")


def _unsafe_relative_path(raw: str) -> bool:
    if not isinstance(raw, str) or not raw:
        return True
    normalized = raw.replace("\\", "/")
    path = Path(normalized)
    return (
        path.is_absolute()
        or bool(_WINDOWS_DRIVE_PATH.match(raw))
        or raw.startswith("\\\\")
        or raw.startswith("//")
        or ".." in path.parts
    )


class ScheduledReportError(RuntimeError):
    def __init__(self, code: str, details: Sequence[str] = ()) -> None:
        super().__init__(code)
        self.code = code
        self.details = tuple(str(item) for item in details)


@dataclass(frozen=True, slots=True)
class ScheduledPeriod:
    kind: str
    start: date
    end: date

    @property
    def key(self) -> str:
        if self.kind == "weekly":
            year, week, _weekday = self.start.isocalendar()
            return f"{year}-W{week:02d}"
        return self.start.strftime("%Y-%m")

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "period_key": self.key,
            "period_start": self.start.isoformat(),
            "period_end": self.end.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class ReportInterval:
    report_id: str
    start: date
    end: date


@dataclass(frozen=True, slots=True)
class SelectedSource:
    path: Path
    source_name: str
    file_sha256: str
    report: Mapping[str, Any]
    intervals: tuple[ReportInterval, ...]


@dataclass(frozen=True, slots=True)
class ScheduledReportOutcome:
    status: str
    kind: str
    period_key: str
    period_start: str
    period_end: str
    package_path: Path | None
    input_identity: str | None
    calculation_status: str | None
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "kind": self.kind,
            "period_key": self.period_key,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "package_path": (
                str(self.package_path) if self.package_path is not None else None
            ),
            "input_identity": self.input_identity,
            "calculation_status": self.calculation_status,
            "reason_codes": list(self.reason_codes),
            "release_scope": "WB_ONLY",
            "marketplace_write_enabled": False,
            "physical_user_path_verified": False,
            "release_state": "RELEASE_BLOCKED",
        }


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _hash_payload(value: Any) -> str:
    return sha256(_canonical_json_bytes(value)).hexdigest()


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _safe_relative(path: Path, root: Path) -> str:
    resolved = path.resolve()
    if not _inside(resolved, root.resolve()):
        raise ScheduledReportError("SCHEDULED_REPORT_PATH_OUTSIDE_ROOT")
    return resolved.relative_to(root.resolve()).as_posix()


def _read_json(path: Path, *, max_bytes: int, code: str) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            payload = handle.read(max_bytes + 1)
        if len(payload) > max_bytes:
            raise ScheduledReportError(code + "_TOO_LARGE")
        value = json.loads(payload.decode("utf-8"))
    except ScheduledReportError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScheduledReportError(code, (type(exc).__name__,)) from exc
    if not isinstance(value, dict):
        raise ScheduledReportError(code)
    return value


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = _canonical_json_bytes(dict(payload)) + b"\n"
    descriptor: int | None = None
    temporary: Path | None = None
    try:
        descriptor, raw = tempfile.mkstemp(
            dir=path.parent,
            prefix="." + path.name + ".",
            suffix=".tmp",
        )
        temporary = Path(raw)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
        _fsync_directory(path.parent)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def completed_period(kind: str, as_of: date | None = None) -> ScheduledPeriod:
    normalized = str(kind).strip().lower()
    if normalized not in SUPPORTED_REPORT_KINDS:
        raise ScheduledReportError("SCHEDULED_REPORT_KIND_UNSUPPORTED", (kind,))
    current = as_of or date.today()
    if not isinstance(current, date):
        raise ScheduledReportError("SCHEDULED_REPORT_AS_OF_INVALID")
    if normalized == "weekly":
        current_week_start = current - timedelta(days=current.weekday())
        end = current_week_start - timedelta(days=1)
        start = end - timedelta(days=6)
    else:
        current_month_start = current.replace(day=1)
        end = current_month_start - timedelta(days=1)
        start = end.replace(day=1)
    return ScheduledPeriod(normalized, start, end)


def _parse_iso_date(value: object, code: str) -> date:
    if not isinstance(value, str) or not value.strip():
        raise ScheduledReportError(code)
    try:
        parsed = date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ScheduledReportError(code, (value,)) from exc
    return parsed


def _report_bridge(report: Mapping[str, Any]) -> Mapping[str, Any]:
    bridge = report.get("source_bridge")
    return bridge if isinstance(bridge, Mapping) else report


def _is_detailed_financial(report: Mapping[str, Any]) -> bool:
    bridge = _report_bridge(report)
    return str(
        bridge.get("source_type") or report.get("source_type") or ""
    ).strip() == "WB_DETAILED_FINANCIAL"


def _report_intervals(report: Mapping[str, Any]) -> tuple[ReportInterval, ...]:
    bridge = _report_bridge(report)
    periods = bridge.get("report_periods")
    if not isinstance(periods, Mapping) or not periods:
        raise ScheduledReportError("SCHEDULED_REPORT_PERIODS_MISSING")
    intervals: list[ReportInterval] = []
    for raw_id, raw_period in sorted(periods.items(), key=lambda item: str(item[0])):
        report_id = str(raw_id).strip()
        if not report_id or not isinstance(raw_period, Mapping):
            raise ScheduledReportError("SCHEDULED_REPORT_PERIOD_INVALID")
        start = _parse_iso_date(
            raw_period.get("date_from"),
            "SCHEDULED_REPORT_DATE_FROM_INVALID",
        )
        end = _parse_iso_date(
            raw_period.get("date_to"),
            "SCHEDULED_REPORT_DATE_TO_INVALID",
        )
        if end < start:
            raise ScheduledReportError(
                "SCHEDULED_REPORT_PERIOD_INVALID",
                (report_id, start.isoformat(), end.isoformat()),
            )
        intervals.append(ReportInterval(report_id, start, end))
    return tuple(intervals)


def _interval_overlaps(interval: ReportInterval, period: ScheduledPeriod) -> bool:
    return interval.start <= period.end and interval.end >= period.start


def _interval_inside(interval: ReportInterval, period: ScheduledPeriod) -> bool:
    return interval.start >= period.start and interval.end <= period.end


def _validate_exact_coverage(
    intervals: Sequence[ReportInterval],
    period: ScheduledPeriod,
) -> None:
    if not intervals:
        raise ScheduledReportError(
            "SCHEDULED_REPORT_SOURCE_COVERAGE_MISSING",
            (period.start.isoformat(), period.end.isoformat()),
        )
    ordered = sorted(intervals, key=lambda item: (item.start, item.end, item.report_id))
    cursor = period.start
    previous: ReportInterval | None = None
    for interval in ordered:
        if interval.start < cursor:
            details = (
                previous.report_id if previous else "",
                interval.report_id,
                interval.start.isoformat(),
                interval.end.isoformat(),
            )
            raise ScheduledReportError("SCHEDULED_REPORT_PERIOD_OVERLAP", details)
        if interval.start > cursor:
            raise ScheduledReportError(
                "SCHEDULED_REPORT_PERIOD_GAP",
                (cursor.isoformat(), (interval.start - timedelta(days=1)).isoformat()),
            )
        cursor = interval.end + timedelta(days=1)
        previous = interval
    if cursor != period.end + timedelta(days=1):
        raise ScheduledReportError(
            "SCHEDULED_REPORT_PERIOD_GAP",
            (cursor.isoformat(), period.end.isoformat()),
        )


def select_sources(
    restored: Iterable[Any],
    period: ScheduledPeriod,
) -> tuple[SelectedSource, ...]:
    selected: list[SelectedSource] = []
    coverage: list[ReportInterval] = []
    for item in restored:
        row = getattr(item, "row", None)
        if row is None or getattr(row, "status", "") in {
            "Ошибка",
            "Недоступен",
            "Отменено",
        }:
            continue
        report = getattr(row, "report", None)
        source_path = getattr(row, "source_path", None)
        if not isinstance(report, Mapping) or not isinstance(source_path, Path):
            continue
        if not _is_detailed_financial(report):
            continue
        if source_path.is_symlink() or not source_path.is_file():
            continue
        digest = str(report.get("file_sha256") or "").strip().lower()
        if _HASH.fullmatch(digest) is None:
            raise ScheduledReportError("SCHEDULED_REPORT_SOURCE_HASH_INVALID")
        all_intervals = _report_intervals(report)
        included: list[ReportInterval] = []
        for interval in all_intervals:
            if not _interval_overlaps(interval, period):
                continue
            if not _interval_inside(interval, period):
                raise ScheduledReportError(
                    "SCHEDULED_REPORT_PARTIAL_SOURCE_PERIOD",
                    (
                        interval.report_id,
                        interval.start.isoformat(),
                        interval.end.isoformat(),
                        period.start.isoformat(),
                        period.end.isoformat(),
                    ),
                )
            included.append(interval)
        if not included:
            continue
        details = getattr(row, "details", None)
        raw_source_name = (
            details.get("original_source_name")
            if isinstance(details, Mapping)
            else None
        )
        source_name = Path(str(raw_source_name or source_path.name)).name
        selected.append(
            SelectedSource(
                path=source_path.resolve(),
                source_name=source_name,
                file_sha256=digest,
                report=report,
                intervals=tuple(included),
            )
        )
        coverage.extend(included)
    _validate_exact_coverage(coverage, period)
    return tuple(
        sorted(
            selected,
            key=lambda item: (
                item.intervals[0].start,
                item.intervals[-1].end,
                item.file_sha256,
            ),
        )
    )


def _row_text(row: Mapping[str, Any], field_name: str) -> str:
    for alias in _ALIASES[field_name]:
        if alias in row and str(row[alias]).strip():
            return str(row[alias]).strip()
    return ""


def _selected_rows(
    source: SelectedSource,
    payload: bytes,
) -> list[dict[str, Any]]:
    rows = read_detailed_financial_rows_payload(payload, source.report)
    allowed = {
        (
            item.report_id,
            item.start.isoformat(),
            item.end.isoformat(),
        )
        for item in source.intervals
    }
    selected: list[dict[str, Any]] = []
    for row in rows:
        identity = (
            _row_text(row, "report_id"),
            _row_text(row, "date_from"),
            _row_text(row, "date_to"),
        )
        if identity in allowed:
            selected.append(dict(row))
    if not selected:
        raise ScheduledReportError(
            "SCHEDULED_REPORT_ROWS_MISSING",
            tuple(item.report_id for item in source.intervals),
        )
    return selected


def _profile_hash(profile: FinanceProfile) -> str:
    return _hash_payload(profile.to_dict())


def _source_bundle(
    period: ScheduledPeriod,
    sources: Sequence[SelectedSource],
) -> dict[str, Any]:
    return {
        "kind": period.kind,
        "period_start": period.start.isoformat(),
        "period_end": period.end.isoformat(),
        "sources": [
            {
                "source_name": item.source_name,
                "file_sha256": item.file_sha256,
                "report_periods": [
                    {
                        "report_id": interval.report_id,
                        "date_from": interval.start.isoformat(),
                        "date_to": interval.end.isoformat(),
                    }
                    for interval in item.intervals
                ],
            }
            for item in sources
        ],
    }


def _summary_text(period: ScheduledPeriod, result: FinanceRunResult) -> str:
    lines = [
        "QUANTUM — АВТОМАТИЧЕСКИЙ ОТЧЁТ",
        f"Тип: {'Недельный' if period.kind == 'weekly' else 'Месячный'}",
        f"Период: {period.start.isoformat()} — {period.end.isoformat()}",
        f"Статус расчёта: {result.status}",
        "",
    ]
    labels = (
        ("net_sold_units", "Продано единиц"),
        ("net_marketplace_income_amount", "Чистый доход WB, ₽"),
        ("product_cost_amount", "Себестоимость, ₽"),
        ("other_expense_amount", "Прочие расходы, ₽"),
        ("tax_amount", "Налог, ₽"),
        ("net_profit_amount", "Чистая прибыль, ₽"),
        ("profit_per_sold_unit", "Прибыль на единицу, ₽"),
    )
    if result.status == "CALCULATED":
        for metric_id, label in labels:
            lines.append(f"{label}: {result.totals.get(metric_id, '—')}")
    else:
        lines.append("Расчёт заблокирован.")
        lines.extend(f"• {item}" for item in result.missing_inputs)
    lines.extend(
        (
            "",
            "Запись в Wildberries отключена. Отчёт носит аналитический характер.",
        )
    )
    return "\n".join(lines) + "\n"


def _file_record(path: Path, root: Path) -> dict[str, Any]:
    payload = path.read_bytes()
    return {
        "path": path.relative_to(root).as_posix(),
        "size_bytes": len(payload),
        "sha256": sha256(payload).hexdigest(),
    }


def _manifest_hash(manifest: Mapping[str, Any]) -> str:
    return _hash_payload(
        {key: value for key, value in manifest.items() if key != "manifest_hash"}
    )


def validate_package(package: Path) -> dict[str, Any]:
    if package.is_symlink() or not package.is_dir():
        raise ScheduledReportError("SCHEDULED_REPORT_PACKAGE_INVALID")
    manifest_path = package / "scheduled_report.json"
    manifest = _read_json(
        manifest_path,
        max_bytes=_MAX_MANIFEST_BYTES,
        code="SCHEDULED_REPORT_MANIFEST_INVALID",
    )
    required = {
        "schema_version",
        "kind",
        "period_key",
        "period_start",
        "period_end",
        "input_identity",
        "generated_at",
        "calculation_status",
        "source_bundle_sha256",
        "profile_sha256",
        "source_count",
        "report_ids",
        "source_files",
        "artifact_count",
        "artifacts",
        "marketplace_write_enabled",
        "release_scope",
        "release_state",
        "physical_user_path_verified",
        "manifest_hash",
    }
    if set(manifest) != required:
        raise ScheduledReportError("SCHEDULED_REPORT_MANIFEST_FIELDS_INVALID")
    if manifest.get("schema_version") != SCHEDULED_REPORT_SCHEMA_VERSION:
        raise ScheduledReportError("SCHEDULED_REPORT_MANIFEST_SCHEMA_INVALID")
    if manifest.get("kind") not in SUPPORTED_REPORT_KINDS:
        raise ScheduledReportError("SCHEDULED_REPORT_MANIFEST_KIND_INVALID")
    if manifest.get("marketplace_write_enabled") is not False:
        raise ScheduledReportError("SCHEDULED_REPORT_WRITES_ENABLED")
    if manifest.get("release_scope") != "WB_ONLY":
        raise ScheduledReportError("SCHEDULED_REPORT_SCOPE_INVALID")
    if manifest.get("release_state") != "RELEASE_BLOCKED":
        raise ScheduledReportError("SCHEDULED_REPORT_RELEASE_STATE_INVALID")
    if manifest.get("physical_user_path_verified") is not False:
        raise ScheduledReportError("SCHEDULED_REPORT_EVIDENCE_BOUNDARY_INVALID")
    if manifest.get("manifest_hash") != _manifest_hash(manifest):
        raise ScheduledReportError("SCHEDULED_REPORT_MANIFEST_HASH_MISMATCH")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or manifest.get("artifact_count") != len(artifacts):
        raise ScheduledReportError("SCHEDULED_REPORT_ARTIFACTS_INVALID")
    seen: set[str] = set()
    for item in artifacts:
        if not isinstance(item, Mapping) or set(item) != {
            "path",
            "size_bytes",
            "sha256",
        }:
            raise ScheduledReportError("SCHEDULED_REPORT_ARTIFACT_INVALID")
        raw = item.get("path")
        if not isinstance(raw, str) or not raw or raw in seen:
            raise ScheduledReportError("SCHEDULED_REPORT_ARTIFACT_INVALID")
        if _unsafe_relative_path(raw):
            raise ScheduledReportError("SCHEDULED_REPORT_ARTIFACT_PATH_INVALID")
        relative = Path(raw.replace("\\", "/"))
        target = (package / relative).resolve()
        if not _inside(target, package.resolve()) or target.is_symlink() or not target.is_file():
            raise ScheduledReportError("SCHEDULED_REPORT_ARTIFACT_MISSING", (raw,))
        payload = target.read_bytes()
        if len(payload) != item.get("size_bytes") or sha256(payload).hexdigest() != item.get("sha256"):
            raise ScheduledReportError("SCHEDULED_REPORT_ARTIFACT_HASH_MISMATCH", (raw,))
        seen.add(raw)
    return manifest


def _cleanup_staging(root: Path) -> None:
    cutoff = time.time() - 3600
    if not root.is_dir():
        return
    for path in root.glob(".scheduled-*.tmp"):
        try:
            if path.is_symlink() or not path.is_dir() or path.stat().st_mtime > cutoff:
                continue
            shutil.rmtree(path)
        except OSError:
            continue


@contextmanager
def _report_lock(project_root: Path):
    lock_path = project_root / "data" / "scheduled-reports.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor: int | None = None
    for attempt in range(2):
        try:
            descriptor = os.open(
                lock_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
            break
        except FileExistsError:
            try:
                stale = time.time() - lock_path.stat().st_mtime > _LOCK_STALE_SECONDS
            except OSError:
                stale = False
            if attempt == 0 and stale and not lock_path.is_symlink():
                lock_path.unlink(missing_ok=True)
                continue
            raise ScheduledReportError("SCHEDULED_REPORT_RUN_BUSY")
    if descriptor is None:
        raise ScheduledReportError("SCHEDULED_REPORT_LOCK_FAILED")
    try:
        payload = _canonical_json_bytes(
            {"pid": os.getpid(), "created_at": datetime.now(UTC).isoformat()}
        )
        os.write(descriptor, payload)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
        lock_path.unlink(missing_ok=True)


def _state_path(project_root: Path) -> Path:
    return project_root / "data" / "scheduled-reports-state.json"


def _load_state(project_root: Path) -> dict[str, Any]:
    path = _state_path(project_root)
    if not path.exists():
        return {
            "schema_version": SCHEDULED_REPORT_STATE_SCHEMA_VERSION,
            "events": [],
        }
    payload = _read_json(
        path,
        max_bytes=_MAX_STATE_BYTES,
        code="SCHEDULED_REPORT_STATE_INVALID",
    )
    if set(payload) != {"schema_version", "events"}:
        raise ScheduledReportError("SCHEDULED_REPORT_STATE_FIELDS_INVALID")
    if payload.get("schema_version") != SCHEDULED_REPORT_STATE_SCHEMA_VERSION:
        raise ScheduledReportError("SCHEDULED_REPORT_STATE_SCHEMA_INVALID")
    events = payload.get("events")
    if not isinstance(events, list) or len(events) > _MAX_EVENTS:
        raise ScheduledReportError("SCHEDULED_REPORT_STATE_EVENTS_INVALID")
    for event in events:
        if not isinstance(event, Mapping):
            raise ScheduledReportError("SCHEDULED_REPORT_STATE_EVENT_INVALID")
        package = event.get("package_relative")
        if package is not None and _unsafe_relative_path(package):
            raise ScheduledReportError("SCHEDULED_REPORT_STATE_PATH_INVALID")
    return payload


def _record_event(project_root: Path, outcome: ScheduledReportOutcome) -> None:
    state = _load_state(project_root)
    package_relative = (
        _safe_relative(outcome.package_path, project_root)
        if outcome.package_path is not None
        else None
    )
    event = {
        "attempted_at": datetime.now(UTC).isoformat(),
        "kind": outcome.kind,
        "period_key": outcome.period_key,
        "status": outcome.status,
        "input_identity": outcome.input_identity,
        "calculation_status": outcome.calculation_status,
        "package_relative": package_relative,
        "reason_codes": list(outcome.reason_codes),
    }
    events = [*state["events"], event][-_MAX_EVENTS:]
    _atomic_json(
        _state_path(project_root),
        {
            "schema_version": SCHEDULED_REPORT_STATE_SCHEMA_VERSION,
            "events": events,
        },
    )


def _load_config(config_path: Path) -> dict[str, Any]:
    payload = _read_json(
        config_path,
        max_bytes=1024 * 1024,
        code="SCHEDULED_REPORT_CONFIG_INVALID",
    )
    if str(payload.get("release_scope") or "") != "WB_ONLY":
        raise ScheduledReportError("SCHEDULED_REPORT_SCOPE_INVALID")
    if payload.get("marketplace_write_enabled") is True:
        raise ScheduledReportError("SCHEDULED_REPORT_WRITES_ENABLED")
    marketplace = str(payload.get("marketplace") or "WILDBERRIES").upper()
    if marketplace not in {"WB", "WILDBERRIES"}:
        raise ScheduledReportError("SCHEDULED_REPORT_MARKETPLACE_UNSUPPORTED")
    return payload


def _build_package(
    *,
    project_root: Path,
    period: ScheduledPeriod,
    result: FinanceRunResult,
    sources: Sequence[SelectedSource],
    source_bundle_sha256: str,
    profile_sha256: str,
    input_identity: str,
) -> Path:
    period_root = (
        project_root
        / "output"
        / "scheduled"
        / period.kind
        / period.key
    )
    period_root.mkdir(parents=True, exist_ok=True)
    _cleanup_staging(period_root)
    final = period_root / input_identity
    if final.exists():
        validate_package(final)
        return final
    stage: Path | None = Path(
        tempfile.mkdtemp(
            dir=period_root,
            prefix=f".scheduled-{input_identity[:12]}-",
            suffix=".tmp",
        )
    )
    try:
        if stage is None:
            raise ScheduledReportError("SCHEDULED_REPORT_STAGE_INVALID")
        outputs, _recommendations, _recommendation_errors = (
            _write_finance_output_bundle(stage / "bundle", result)
        )
        summary_path = stage / "Quantum_Summary.txt"
        summary_path.write_text(_summary_text(period, result), encoding="utf-8")
        for path in [summary_path, *outputs.values()]:
            if not path.is_file() or path.stat().st_size <= 0:
                raise ScheduledReportError("SCHEDULED_REPORT_ARTIFACT_MISSING")
            with path.open("r+b") as handle:
                os.fsync(handle.fileno())
        artifact_paths = [summary_path, *sorted(outputs.values(), key=lambda p: p.name)]
        artifacts = [_file_record(path, stage) for path in artifact_paths]
        report_ids = sorted(
            interval.report_id
            for source in sources
            for interval in source.intervals
        )
        source_files = [
            {
                "source_name": source.source_name,
                "file_sha256": source.file_sha256,
                "report_ids": [item.report_id for item in source.intervals],
            }
            for source in sources
        ]
        manifest: dict[str, Any] = {
            "schema_version": SCHEDULED_REPORT_SCHEMA_VERSION,
            "kind": period.kind,
            "period_key": period.key,
            "period_start": period.start.isoformat(),
            "period_end": period.end.isoformat(),
            "input_identity": input_identity,
            "generated_at": datetime.now(UTC).isoformat(),
            "calculation_status": result.status,
            "source_bundle_sha256": source_bundle_sha256,
            "profile_sha256": profile_sha256,
            "source_count": len(sources),
            "report_ids": report_ids,
            "source_files": source_files,
            "artifact_count": len(artifacts),
            "artifacts": artifacts,
            "marketplace_write_enabled": False,
            "release_scope": "WB_ONLY",
            "release_state": "RELEASE_BLOCKED",
            "physical_user_path_verified": False,
            "manifest_hash": "",
        }
        manifest["manifest_hash"] = _manifest_hash(manifest)
        _atomic_json(stage / "scheduled_report.json", manifest)
        _fsync_directory(stage)
        try:
            os.replace(stage, final)
            stage = None
        except OSError:
            if final.exists():
                validate_package(final)
                shutil.rmtree(stage, ignore_errors=True)
                stage = None
            else:
                raise
        _fsync_directory(period_root)
        validate_package(final)
        pointer = {
            "schema_version": SCHEDULED_REPORT_POINTER_SCHEMA_VERSION,
            "kind": period.kind,
            "period_key": period.key,
            "input_identity": input_identity,
            "package_relative": final.relative_to(project_root).as_posix(),
            "manifest_hash": manifest["manifest_hash"],
            "updated_at": datetime.now(UTC).isoformat(),
        }
        _atomic_json(period_root / "latest.json", pointer)
        return final
    finally:
        if stage is not None and stage.exists():
            shutil.rmtree(stage, ignore_errors=True)


def run_scheduled_report(
    *,
    project_root: Path,
    config_path: Path,
    kind: str,
    as_of: date | None = None,
) -> ScheduledReportOutcome:
    root = project_root.resolve()
    config = config_path.resolve()
    if not root.is_dir() or config.is_symlink() or not config.is_file():
        raise ScheduledReportError("SCHEDULED_REPORT_ROOT_OR_CONFIG_INVALID")
    if not _inside(config, root):
        raise ScheduledReportError("SCHEDULED_REPORT_CONFIG_OUTSIDE_ROOT")
    period = completed_period(kind, as_of)
    with _report_lock(root):
        try:
            _load_state(root)
            config_payload = _load_config(config)
            organization_id = str(config_payload.get("tenant_id") or "").strip()
            if not organization_id:
                raise ScheduledReportError("SCHEDULED_REPORT_TENANT_REQUIRED")
            profile_path = root / "config" / "finance-profile.json"
            profile = load_profile(profile_path)
            if profile is None:
                raise ScheduledReportError("FINANCE_PROFILE_REQUIRED")
            missing = validate_profile(profile)
            if missing:
                raise ScheduledReportError("FINANCE_PROFILE_INCOMPLETE", missing)
            restored = restore_reports(root, config)
            sources = select_sources(restored, period)
            source_bundle = _source_bundle(period, sources)
            source_bundle_sha256 = _hash_payload(source_bundle)
            profile_sha256 = _profile_hash(profile)
            input_identity = _hash_payload(
                {
                    "schema_version": SCHEDULED_REPORT_SCHEMA_VERSION,
                    "period": period.to_dict(),
                    "organization_id": organization_id,
                    "profile_sha256": profile_sha256,
                    "source_bundle_sha256": source_bundle_sha256,
                }
            )
            existing = (
                root
                / "output"
                / "scheduled"
                / period.kind
                / period.key
                / input_identity
            )
            if existing.exists():
                manifest = validate_package(existing)
                outcome = ScheduledReportOutcome(
                    status="REUSED",
                    kind=period.kind,
                    period_key=period.key,
                    period_start=period.start.isoformat(),
                    period_end=period.end.isoformat(),
                    package_path=existing,
                    input_identity=input_identity,
                    calculation_status=str(manifest.get("calculation_status")),
                )
                _record_event(root, outcome)
                return outcome
            detailed_rows: list[dict[str, Any]] = []
            for source in sources:
                payload = _read_finance_source(source.path)
                actual = sha256(payload).hexdigest()
                if actual != source.file_sha256:
                    raise ScheduledReportError(
                        "SCHEDULED_REPORT_SOURCE_HASH_MISMATCH",
                        (source.source_name,),
                    )
                detailed_rows.extend(_selected_rows(source, payload))
            if not detailed_rows:
                raise ScheduledReportError("SCHEDULED_REPORT_ROWS_MISSING")
            result = calculate_by_group(
                detailed_rows=detailed_rows,
                profile=profile,
                organization_id=organization_id,
                source_id=(
                    f"scheduled:{period.kind}:{period.key}:"
                    f"{source_bundle_sha256[:20]}"
                ),
                source_sha256=source_bundle_sha256,
            )
            package = _build_package(
                project_root=root,
                period=period,
                result=result,
                sources=sources,
                source_bundle_sha256=source_bundle_sha256,
                profile_sha256=profile_sha256,
                input_identity=input_identity,
            )
            reason_codes = tuple(result.missing_inputs)
            outcome = ScheduledReportOutcome(
                status="GENERATED",
                kind=period.kind,
                period_key=period.key,
                period_start=period.start.isoformat(),
                period_end=period.end.isoformat(),
                package_path=package,
                input_identity=input_identity,
                calculation_status=result.status,
                reason_codes=reason_codes,
            )
            _record_event(root, outcome)
            return outcome
        except (FinanceProfileError, OSError) as exc:
            if isinstance(exc, FinanceProfileError):
                error = ScheduledReportError(exc.code, exc.details)
            else:
                error = ScheduledReportError(
                    "SCHEDULED_REPORT_IO_FAILED",
                    (type(exc).__name__,),
                )
            outcome = ScheduledReportOutcome(
                status="FAILED",
                kind=period.kind,
                period_key=period.key,
                period_start=period.start.isoformat(),
                period_end=period.end.isoformat(),
                package_path=None,
                input_identity=None,
                calculation_status=None,
                reason_codes=(error.code, *error.details),
            )
            _record_event(root, outcome)
            raise error from exc
        except ScheduledReportError as exc:
            outcome = ScheduledReportOutcome(
                status="FAILED",
                kind=period.kind,
                period_key=period.key,
                period_start=period.start.isoformat(),
                period_end=period.end.isoformat(),
                package_path=None,
                input_identity=None,
                calculation_status=None,
                reason_codes=(exc.code, *exc.details),
            )
            _record_event(root, outcome)
            raise


def run_due_reports(
    *,
    project_root: Path,
    config_path: Path,
    as_of: date | None = None,
) -> tuple[ScheduledReportOutcome, ...]:
    outcomes: list[ScheduledReportOutcome] = []
    errors: list[str] = []
    for kind in ("weekly", "monthly"):
        try:
            outcomes.append(
                run_scheduled_report(
                    project_root=project_root,
                    config_path=config_path,
                    kind=kind,
                    as_of=as_of,
                )
            )
        except ScheduledReportError as exc:
            errors.append(kind + ":" + exc.code)
    if errors:
        raise ScheduledReportError("SCHEDULED_REPORT_DUE_FAILED", errors)
    return tuple(outcomes)


def _task_name(project_root: Path) -> str:
    digest = sha256(str(project_root.resolve()).casefold().encode("utf-8")).hexdigest()
    return "Quantum Scheduled Reports " + digest[:12]


def _encoded_task_command(
    *,
    project_root: Path,
    config_path: Path,
    python_executable: Path,
) -> str:
    root = project_root.resolve()
    config = config_path.resolve()
    python = python_executable.resolve()
    if not python.is_file() or not config.is_file() or not _inside(config, root):
        raise ScheduledReportError("SCHEDULED_REPORT_TASK_PATH_INVALID")

    def quote(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    command = (
        f"$env:PYTHONPATH={quote(str(root / 'src'))}; "
        f"& {quote(str(python))} -m quantum.application.scheduled_reports "
        f"--root {quote(str(root))} --config {quote(str(config))} --kind due"
    )
    encoded = base64.b64encode(command.encode("utf-16le")).decode("ascii")
    return (
        "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass "
        "-EncodedCommand " + encoded
    )


def register_windows_task(
    *,
    project_root: Path,
    config_path: Path,
    time_of_day: str = "08:00",
    python_executable: Path | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    platform_name: str | None = None,
) -> str:
    platform = os.name if platform_name is None else platform_name
    if platform != "nt":
        raise ScheduledReportError("WINDOWS_TASK_SCHEDULER_REQUIRED")
    if _TIME.fullmatch(time_of_day) is None:
        raise ScheduledReportError("SCHEDULED_REPORT_TASK_TIME_INVALID")
    root = project_root.resolve()
    config = config_path.resolve()
    python = (python_executable or Path(sys.executable)).resolve()
    task_name = _task_name(root)
    action = _encoded_task_command(
        project_root=root,
        config_path=config,
        python_executable=python,
    )
    create = [
        "schtasks.exe",
        "/Create",
        "/TN",
        task_name,
        "/TR",
        action,
        "/SC",
        "DAILY",
        "/ST",
        time_of_day,
        "/RL",
        "LIMITED",
        "/F",
    ]
    result = runner(
        create,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise ScheduledReportError(
            "SCHEDULED_REPORT_TASK_CREATE_FAILED",
            (str(result.returncode), (result.stderr or result.stdout or "").strip()),
        )
    query = runner(
        ["schtasks.exe", "/Query", "/TN", task_name, "/FO", "LIST"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if query.returncode != 0:
        raise ScheduledReportError(
            "SCHEDULED_REPORT_TASK_VERIFY_FAILED",
            (str(query.returncode),),
        )
    return task_name


def unregister_windows_task(
    *,
    project_root: Path,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    platform_name: str | None = None,
) -> str:
    platform = os.name if platform_name is None else platform_name
    if platform != "nt":
        raise ScheduledReportError("WINDOWS_TASK_SCHEDULER_REQUIRED")
    task_name = _task_name(project_root)
    result = runner(
        ["schtasks.exe", "/Delete", "/TN", task_name, "/F"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise ScheduledReportError(
            "SCHEDULED_REPORT_TASK_DELETE_FAILED",
            (str(result.returncode), (result.stderr or result.stdout or "").strip()),
        )
    return task_name


def _parse_as_of(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ScheduledReportError("SCHEDULED_REPORT_AS_OF_INVALID", (value,)) from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quantum-scheduled-reports")
    parser.add_argument("--root", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument(
        "--kind",
        choices=("weekly", "monthly", "due"),
        default="due",
    )
    parser.add_argument("--as-of")
    parser.add_argument("--register-task", action="store_true")
    parser.add_argument("--unregister-task", action="store_true")
    parser.add_argument("--task-time", default="08:00")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    config = Path(args.config).resolve()
    try:
        if args.register_task and args.unregister_task:
            raise ScheduledReportError("SCHEDULED_REPORT_TASK_ACTION_CONFLICT")
        if args.register_task:
            payload: Any = {
                "status": "TASK_REGISTERED",
                "task_name": register_windows_task(
                    project_root=root,
                    config_path=config,
                    time_of_day=args.task_time,
                ),
                "marketplace_write_enabled": False,
                "release_state": "RELEASE_BLOCKED",
            }
        elif args.unregister_task:
            payload = {
                "status": "TASK_UNREGISTERED",
                "task_name": unregister_windows_task(project_root=root),
                "marketplace_write_enabled": False,
                "release_state": "RELEASE_BLOCKED",
            }
        elif args.kind == "due":
            payload = {
                "status": "DUE_CHECK_COMPLETE",
                "outcomes": [
                    item.to_dict()
                    for item in run_due_reports(
                        project_root=root,
                        config_path=config,
                        as_of=_parse_as_of(args.as_of),
                    )
                ],
                "marketplace_write_enabled": False,
                "release_state": "RELEASE_BLOCKED",
            }
        else:
            payload = run_scheduled_report(
                project_root=root,
                config_path=config,
                kind=args.kind,
                as_of=_parse_as_of(args.as_of),
            ).to_dict()
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0
    except ScheduledReportError as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "reason_code": exc.code,
                    "details": list(exc.details),
                    "marketplace_write_enabled": False,
                    "release_state": "RELEASE_BLOCKED",
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
