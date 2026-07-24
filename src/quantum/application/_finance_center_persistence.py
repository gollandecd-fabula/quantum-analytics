from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Iterable, Mapping

from quantum.application.finance_profile import (
    FinanceProfileError,
    ProductRecord,
    detect_products_from_xlsx,
)
from quantum.application.local_app import (
    ImportRow,
    SUCCESS_STATUSES,
    _human_size,
    summarize_report,
)


LEGACY_REPORT_INDEX_SCHEMA_VERSION = (
    "quantum-finance-center-report-index-v1"
)
REPORT_INDEX_SCHEMA_VERSION = "quantum-finance-center-report-index-v2"
REPORT_INDEX_RELATIVE_PATH = Path("data") / "finance-center-reports.json"
_REPLACE_ATTEMPTS = 5
_REPLACE_INITIAL_DELAY_SECONDS = 0.05


@dataclass(frozen=True, slots=True)
class RestoredReport:
    row: ImportRow
    product_records: tuple[ProductRecord, ...]


def finance_center_summary(
    report: Mapping[str, Any] | None,
    return_code: int,
    summary: tuple[str, str, str, str] | None = None,
) -> tuple[str, str, str, str]:
    status, detected_format, raw_status, comment = summary or summarize_report(
        report if isinstance(report, dict) else None,
        return_code,
    )
    if not isinstance(report, Mapping):
        return status, detected_format, raw_status, comment
    top_status = report.get("status")
    bridge = report.get("source_bridge")
    bridge_status = (
        bridge.get("status") if isinstance(bridge, Mapping) else None
    )
    finance_state = (
        bridge.get("finance_request_state")
        if isinstance(bridge, Mapping)
        else None
    )
    if (
        isinstance(top_status, str)
        and top_status in SUCCESS_STATUSES
        and bridge_status == "SOURCE_BRIDGE_COMPLETE"
        and finance_state != "BLOCKED"
        and return_code == 0
    ):
        return "Готово", detected_format, top_status, "Импорт завершён."
    return status, detected_format, raw_status, comment


_MAX_PERSISTED_JSON_BYTES = 16 * 1024 * 1024


def _safe_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as stream:
            payload = stream.read(_MAX_PERSISTED_JSON_BYTES + 1)
        if len(payload) > _MAX_PERSISTED_JSON_BYTES:
            return {}
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _digest(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef"
        for character in normalized
    ):
        return None
    return normalized


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _file_digest(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _verified_file(
    path: Path,
    digest: str | None,
    root: Path,
) -> Path | None:
    try:
        resolved = path.resolve(strict=True)
        if not _inside(resolved, root) or not resolved.is_file():
            return None
        if digest is not None and _file_digest(resolved) != digest:
            return None
        return resolved
    except OSError:
        return None


def _candidate_managed_sources(
    project_root: Path,
    config_path: Path,
    report: Mapping[str, Any],
) -> tuple[Path, ...]:
    digest = _digest(report.get("file_sha256"))
    dataset_id = report.get("dataset_id")
    if (
        digest is None
        or not isinstance(dataset_id, str)
        or not dataset_id.strip()
    ):
        return ()

    data_root = project_root / "data"
    tokens: list[str] = []
    config = _safe_json(config_path)
    tenant_id = config.get("tenant_id")
    if isinstance(tenant_id, str) and tenant_id.strip():
        tokens.append(
            sha256(tenant_id.strip().encode("utf-8")).hexdigest()
        )
    try:
        for path in (data_root / "pilot-zones").iterdir():
            if path.is_dir() and path.name not in tokens:
                tokens.append(path.name)
    except OSError:
        pass

    candidates: list[Path] = []
    for token in tokens:
        candidates.extend(
            (
                data_root
                / "pilot-zones"
                / token
                / "admitted"
                / dataset_id.strip()
                / digest,
                data_root / "tenants" / token / "raw" / digest,
            )
        )
    return tuple(candidates)


def _internal_report_path(root: Path, raw: object) -> Path | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    candidate = Path(raw.strip())
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    return resolved if _inside(resolved, root) else None


def managed_source_path(
    project_root: Path,
    config_path: Path,
    report: Mapping[str, Any],
    original_source: Path | None = None,
) -> Path | None:
    """Return only a verified source controlled by the Quantum root.

    ``original_source`` remains in the signature for compatibility with older
    callers, but an external user path is never accepted as a durable source.
    """

    root = project_root.resolve()
    digest = _digest(report.get("file_sha256"))
    if digest is None:
        return None

    for candidate in _candidate_managed_sources(root, config_path, report):
        verified = _verified_file(candidate, digest, root)
        if verified is not None:
            return verified

    stored_path = _internal_report_path(root, report.get("stored_path"))
    if stored_path is not None:
        verified = _verified_file(stored_path, digest, root)
        if verified is not None:
            return verified

    if original_source is not None and _inside(original_source, root):
        verified = _verified_file(original_source, digest, root)
        if verified is not None:
            return verified
    return None


def _validate_index_payload(path: Path) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("REPORT_INDEX_STAGED_JSON_INVALID") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != REPORT_INDEX_SCHEMA_VERSION
        or not isinstance(payload.get("reports"), list)
    ):
        raise ValueError("REPORT_INDEX_STAGED_SCHEMA_INVALID")


def _replace_with_retry(source: Path, target: Path) -> None:
    delay = _REPLACE_INITIAL_DELAY_SECONDS
    for attempt in range(_REPLACE_ATTEMPTS):
        try:
            os.replace(source, target)
            return
        except OSError:
            if attempt + 1 >= _REPLACE_ATTEMPTS:
                raise
            time.sleep(delay)
            delay *= 2


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor: int | None = None
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary = Path(name)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        _validate_index_payload(temporary)
        _replace_with_retry(temporary, path)
        temporary = None
        _fsync_directory(path.parent)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _portable_relative(path: Path | None, root: Path) -> str | None:
    if path is None:
        return None
    try:
        resolved = path.resolve()
        if not _inside(resolved, root):
            return None
        return str(resolved.relative_to(root))
    except (OSError, ValueError):
        return None


def _source_name(row: ImportRow, report: Mapping[str, Any]) -> str:
    raw = str(
        row.details.get("original_source_name")
        or report.get("sanitized_filename")
        or row.source_path.name
    ).strip()
    name = Path(raw).name.strip()
    return name or "report.xlsx"


def save_report_index(
    project_root: Path,
    rows: Iterable[ImportRow],
) -> Path:
    root = project_root.resolve()
    by_digest: dict[str, dict[str, Any]] = {}
    for row in rows:
        report = row.report if isinstance(row.report, dict) else {}
        digest = _digest(report.get("file_sha256"))
        if digest is None:
            continue
        output_path = (
            row.output_path.resolve()
            if row.output_path is not None
            else None
        )
        managed = _verified_file(row.source_path, digest, root)
        by_digest[digest] = {
            "file_sha256": digest,
            "output_path": _portable_relative(output_path, root),
            "managed_source_path": _portable_relative(managed, root),
            "source_name": _source_name(row, report),
        }
    reports = [by_digest[digest] for digest in sorted(by_digest)]
    target = root / REPORT_INDEX_RELATIVE_PATH
    _atomic_json(
        target,
        {
            "schema_version": REPORT_INDEX_SCHEMA_VERSION,
            "reports": reports,
        },
    )
    return target


def _resolve_index_path(root: Path, raw: object) -> Path | None:
    return _internal_report_path(root, raw)


def _index_entries(project_root: Path) -> tuple[dict[str, Any], ...]:
    payload = _safe_json(project_root / REPORT_INDEX_RELATIVE_PATH)
    if payload.get("schema_version") not in {
        LEGACY_REPORT_INDEX_SCHEMA_VERSION,
        REPORT_INDEX_SCHEMA_VERSION,
    }:
        return ()
    entries = payload.get("reports")
    if not isinstance(entries, list):
        return ()
    return tuple(item for item in entries if isinstance(item, dict))


def _output_candidates(project_root: Path) -> tuple[Path, ...]:
    output_root = project_root / "output"
    candidates: dict[Path, int] = {}
    for pattern in ("pilot_gui_*.json", "pilot_*.json"):
        try:
            paths = tuple(output_root.glob(pattern))
        except OSError:
            continue
        for path in paths:
            try:
                resolved = path.resolve(strict=True)
                if not resolved.is_file() or not _inside(resolved, project_root):
                    continue
                candidates[resolved] = resolved.stat().st_mtime_ns
            except OSError:
                continue
    return tuple(
        path
        for path, _modified in sorted(
            candidates.items(),
            key=lambda item: (item[1], item[0].name),
        )
    )


def restore_reports(
    project_root: Path,
    config_path: Path,
) -> tuple[RestoredReport, ...]:
    root = project_root.resolve()
    index_entries = _index_entries(root)
    index_by_output: dict[str, dict[str, Any]] = {}
    index_by_digest: dict[str, dict[str, Any]] = {}
    for entry in index_entries:
        output = _resolve_index_path(root, entry.get("output_path"))
        if output is not None:
            index_by_output[str(output)] = entry
        digest = _digest(entry.get("file_sha256"))
        if digest is not None:
            index_by_digest[digest] = entry

    latest: dict[str, tuple[int, Path, dict[str, Any]]] = {}
    for output_path in _output_candidates(root):
        report = _safe_json(output_path)
        digest = _digest(report.get("file_sha256"))
        if digest is None:
            continue
        try:
            modified = output_path.stat().st_mtime_ns
        except OSError:
            continue
        previous = latest.get(digest)
        if previous is None or modified >= previous[0]:
            latest[digest] = (modified, output_path, report)

    restored: list[RestoredReport] = []
    used_row_ids: set[str] = set()
    for digest, (_modified, output_path, report) in sorted(
        latest.items(),
        key=lambda item: (item[1][0], item[1][1].name),
    ):
        entry = (
            index_by_output.get(str(output_path))
            or index_by_digest.get(digest)
            or {}
        )
        indexed_source = _resolve_index_path(
            root,
            entry.get("managed_source_path") or entry.get("source_path"),
        )
        source_path = managed_source_path(
            root,
            config_path,
            report,
            indexed_source,
        )
        raw_name = str(
            entry.get("source_name")
            or report.get("sanitized_filename")
            or (indexed_source.name if indexed_source is not None else digest)
        )
        source_name = Path(raw_name).name or digest
        display_path = (
            source_path
            or (root / "data" / "missing" / source_name)
        )
        status, detected_format, raw_status, comment = (
            finance_center_summary(report, 0)
        )
        size_raw = report.get("file_size_bytes")
        try:
            size_text = _human_size(int(size_raw))
        except (TypeError, ValueError):
            size_text = "—"

        row_id = "restored-" + digest[:12]
        suffix = 1
        while row_id in used_row_ids:
            suffix += 1
            row_id = f"restored-{digest[:12]}-{suffix}"
        used_row_ids.add(row_id)

        row = ImportRow(
            row_id=row_id,
            source_path=display_path,
            size_text=size_text,
            output_path=output_path,
            status=status,
            detected_format=detected_format,
            progress="100%" if status != "Ошибка" else "Сбой",
            comment=comment,
            report=report,
            raw_status=raw_status,
            details={
                "restored": True,
                "original_source_name": source_name,
                "managed_source_available": source_path is not None,
                "output_path": str(output_path),
            },
        )
        products: tuple[ProductRecord, ...] = ()
        if source_path is None:
            row.status = "Недоступен"
            row.progress = "—"
            row.comment = (
                "Результат импорта найден, но сохранённый исходный файл "
                "отсутствует или не прошёл проверку целостности."
            )
        else:
            try:
                products = detect_products_from_xlsx(source_path)
            except FinanceProfileError as exc:
                row.details["product_restore_error"] = exc.code
            except OSError as exc:
                row.details["product_restore_error"] = type(exc).__name__
        restored.append(RestoredReport(row=row, product_records=products))
    return tuple(restored)


__all__ = [
    "LEGACY_REPORT_INDEX_SCHEMA_VERSION",
    "REPORT_INDEX_RELATIVE_PATH",
    "REPORT_INDEX_SCHEMA_VERSION",
    "RestoredReport",
    "finance_center_summary",
    "managed_source_path",
    "restore_reports",
    "save_report_index",
]
