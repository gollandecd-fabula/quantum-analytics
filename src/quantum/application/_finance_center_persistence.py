from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable, Mapping

from quantum.application.finance_profile import (
    FinanceProfileError,
    ProductRecord,
    detect_products_from_xlsx,
)
from quantum.application.local_app import ImportRow, _human_size, summarize_report


REPORT_INDEX_SCHEMA_VERSION = "quantum-finance-center-report-index-v1"
REPORT_INDEX_RELATIVE_PATH = Path("data") / "finance-center-reports.json"


@dataclass(frozen=True, slots=True)
class RestoredReport:
    row: ImportRow
    product_records: tuple[ProductRecord, ...]


def _safe_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _digest(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        return None
    return normalized


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _verified_file(path: Path, digest: str | None) -> Path | None:
    try:
        if not path.is_file():
            return None
        if digest is not None and sha256(path.read_bytes()).hexdigest() != digest:
            return None
        return path.resolve()
    except OSError:
        return None


def _candidate_managed_sources(
    project_root: Path,
    config_path: Path,
    report: Mapping[str, Any],
) -> Iterable[Path]:
    digest = _digest(report.get("file_sha256"))
    dataset_id = report.get("dataset_id")
    if digest is None or not isinstance(dataset_id, str) or not dataset_id.strip():
        return ()

    data_root = project_root / "data"
    tokens: list[str] = []
    config = _safe_json(config_path)
    tenant_id = config.get("tenant_id")
    if isinstance(tenant_id, str) and tenant_id.strip():
        tokens.append(sha256(tenant_id.strip().encode("utf-8")).hexdigest())
    try:
        tokens.extend(
            path.name
            for path in (data_root / "pilot-zones").iterdir()
            if path.is_dir() and path.name not in tokens
        )
    except OSError:
        pass

    candidates: list[Path] = []
    for token in tokens:
        candidates.append(
            data_root
            / "pilot-zones"
            / token
            / "admitted"
            / dataset_id.strip()
            / digest
        )
        candidates.append(data_root / "tenants" / token / "raw" / digest)
    return tuple(candidates)


def managed_source_path(
    project_root: Path,
    config_path: Path,
    report: Mapping[str, Any],
    original_source: Path | None = None,
) -> Path | None:
    root = project_root.resolve()
    digest = _digest(report.get("file_sha256"))

    for candidate in _candidate_managed_sources(root, config_path, report):
        verified = _verified_file(candidate, digest)
        if verified is not None and _inside(verified, root):
            return verified

    stored_path = report.get("stored_path")
    if isinstance(stored_path, str) and stored_path.strip():
        verified = _verified_file(Path(stored_path.strip()), digest)
        if verified is not None and _inside(verified, root):
            return verified

    if original_source is not None:
        verified = _verified_file(original_source, digest)
        if verified is not None:
            return verified
    return None


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
        os.replace(temporary, path)
        temporary = None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save_report_index(
    project_root: Path,
    rows: Iterable[ImportRow],
) -> Path:
    root = project_root.resolve()
    reports: list[dict[str, Any]] = []
    for row in rows:
        report = row.report if isinstance(row.report, dict) else {}
        output_path = row.output_path.resolve() if row.output_path is not None else None
        source_path = row.source_path.resolve()
        reports.append(
            {
                "file_sha256": _digest(report.get("file_sha256")),
                "output_path": (
                    str(output_path.relative_to(root))
                    if output_path is not None and _inside(output_path, root)
                    else str(output_path) if output_path is not None else None
                ),
                "source_path": (
                    str(source_path.relative_to(root))
                    if _inside(source_path, root)
                    else str(source_path)
                ),
                "source_name": str(
                    row.details.get("original_source_name")
                    or report.get("sanitized_filename")
                    or row.source_path.name
                ),
            }
        )
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
    if not isinstance(raw, str) or not raw.strip():
        return None
    path = Path(raw.strip())
    return path if path.is_absolute() else root / path


def _index_entries(project_root: Path) -> tuple[dict[str, Any], ...]:
    payload = _safe_json(project_root / REPORT_INDEX_RELATIVE_PATH)
    if payload.get("schema_version") != REPORT_INDEX_SCHEMA_VERSION:
        return ()
    entries = payload.get("reports")
    if not isinstance(entries, list):
        return ()
    return tuple(item for item in entries if isinstance(item, dict))


def _output_candidates(project_root: Path) -> tuple[Path, ...]:
    output_root = project_root / "output"
    paths: set[Path] = set()
    for pattern in ("pilot_gui_*.json", "pilot_*.json"):
        try:
            paths.update(path.resolve() for path in output_root.glob(pattern) if path.is_file())
        except OSError:
            continue
    return tuple(sorted(paths, key=lambda path: (path.stat().st_mtime_ns, path.name)))


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
            index_by_output[str(output.resolve())] = entry
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
        entry = index_by_output.get(str(output_path.resolve())) or index_by_digest.get(digest) or {}
        indexed_source = _resolve_index_path(root, entry.get("source_path"))
        source_path = managed_source_path(
            root,
            config_path,
            report,
            indexed_source,
        )
        source_name = str(
            entry.get("source_name")
            or report.get("sanitized_filename")
            or (indexed_source.name if indexed_source is not None else digest)
        )
        display_path = source_path or indexed_source or (root / "data" / "missing" / source_name)
        status, detected_format, raw_status, comment = summarize_report(report, 0)
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
                "Результат импорта найден, но сохранённый исходный файл отсутствует "
                "или не прошёл проверку целостности."
            )
        else:
            try:
                products = detect_products_from_xlsx(source_path)
            except Exception as exc:  # defensive restore boundary
                products = ()
                row.details["product_restore_error"] = type(exc).__name__
        restored.append(RestoredReport(row=row, product_records=products))
    return tuple(restored)


__all__ = [
    "REPORT_INDEX_RELATIVE_PATH",
    "REPORT_INDEX_SCHEMA_VERSION",
    "RestoredReport",
    "managed_source_path",
    "restore_reports",
    "save_report_index",
]
