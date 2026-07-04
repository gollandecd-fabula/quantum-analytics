from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import re
from typing import Any, Mapping
from uuid import uuid4

from quantum.ingestion._xlsx_contracts import XlsxInspectionError, XlsxInspectionLimits
from . import local_runner as _strict_engine
from .any_file_common import (
    AnyFileError,
    atomic_json,
    safe_filename,
    store_original,
)
from .any_file_detection import detect, text_structure
from .windows_runner import (
    WindowsRunnerError,
    apply_discovered_schema,
    discover_schema,
    install_windows_compatibility,
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _xlsx_limits(config: Mapping[str, Any]) -> XlsxInspectionLimits:
    try:
        policy = config["inspection_policy"]
        limits = policy["limits"]
        return XlsxInspectionLimits(**dict(limits))
    except (KeyError, TypeError, XlsxInspectionError) as exc:
        raise AnyFileError("ANY_FILE_XLSX_LIMITS_INVALID") from exc


def _diagnostic_class(codes: list[str]) -> str:
    if codes and all(
        code.startswith("XLSX_") and code.endswith("_UNMODELED")
        for code in codes
    ):
        return "MODEL_LIMITATION"
    security_tokens = (
        "ACTIVE_CONTENT", "EXTERNAL", "PATH", "SYMLINK", "ENCRYPTED",
        "ENTITY", "POLYGLOT", "MACRO", "DDE", "HYPERLINK", "FORMULA",
    )
    if any(any(token in code for token in security_tokens) for code in codes):
        return "SECURITY"
    corruption_tokens = (
        "CORRUPT", "INVALID", "MISSING", "MISMATCH", "READ_FAILED",
        "DUPLICATE", "TRUNCATED",
    )
    if any(any(token in code for token in corruption_tokens) for code in codes):
        return "CORRUPTED"
    return "MODEL_LIMITATION"


def _base_report(file_path: Path, payload: bytes, digest: str) -> dict[str, Any]:
    return {
        "runner_version": "ANY_FILE_GATEWAY_R1",
        "intake_id": str(uuid4()),
        "runtime_profile": "HOME_LOCAL",
        "sanitized_filename": safe_filename(file_path.name),
        "file_sha256": digest,
        "file_size_bytes": len(payload),
        "marketplace_write_enabled": False,
        "raw_rows_in_report": False,
        "calculation": None,
        "diagnostics": [],
        "limitations": [
            "PILOT_READY_NOT_ASSERTED",
            "FINANCE_CALCULATION_NOT_REQUESTED",
            "HOME_LOCAL_UNENCRYPTED_STORAGE",
            "PHYSICAL_ACCESS_RISK_ACCEPTED",
        ],
    }


def intake_file(
    *,
    file_path: Path,
    config: Mapping[str, Any],
    storage_root: Path,
    authority_attested: bool,
    schema_reviewed: bool,
    expected_file_sha256: str | None = None,
) -> dict[str, Any]:
    if not authority_attested:
        raise AnyFileError("ANY_FILE_AUTHORITY_ATTESTATION_REQUIRED")
    if not isinstance(file_path, Path) or not file_path.is_file():
        raise AnyFileError("ANY_FILE_NOT_FOUND")
    payload = file_path.read_bytes()
    digest = sha256(payload).hexdigest()
    if expected_file_sha256 is not None:
        expected = expected_file_sha256.strip().lower()
        if _SHA256.fullmatch(expected) is None:
            raise AnyFileError("ANY_FILE_EXPECTED_SHA256_INVALID")
        if digest != expected:
            raise AnyFileError("ANY_FILE_SOURCE_HASH_MISMATCH")

    base = _base_report(file_path, payload, digest)
    try:
        detection = detect(payload, file_path.name)
    except AnyFileError as exc:
        corrupted = any(
            token in exc.code for token in ("CORRUPT", "EMPTY", "SIZE_EXCEEDED")
        )
        zone = "quarantine-corrupted" if corrupted else "quarantine-security"
        relative, duplicate = store_original(
            storage_root=storage_root, payload=payload, digest=digest, zone=zone
        )
        base.update(
            {
                "status": (
                    "QUARANTINED_CORRUPTED" if corrupted
                    else "QUARANTINED_SECURITY"
                ),
                "detected_format": "UNKNOWN",
                "media_type": "application/octet-stream",
                "storage_relative_path": relative,
                "duplicate_upload": duplicate,
                "diagnostics": [exc.code],
                "strict_admission": None,
                "parse": None,
            }
        )
        return base

    base.update(
        {
            "detected_format": detection.kind,
            "media_type": detection.media_type,
            "archive_entries": detection.archive_entries,
        }
    )

    if detection.kind in {"XLSX", "ZIP_XLSX"}:
        if not schema_reviewed:
            raise AnyFileError("ANY_FILE_SCHEMA_REVIEW_REQUIRED")
        install_windows_compatibility()
        try:
            candidate = discover_schema(
                payload=payload, limits=_xlsx_limits(config)
            )
            parse_summary = candidate.report()
            strict_config = apply_discovered_schema(config, candidate)
            strict_config["lawful_authority_attested"] = True
            strict_config["execution_mode"] = "ADMISSION_ONLY"
            strict_config["finance_request"] = None
            strict_report = _strict_engine.run_local_pilot(
                file_path=file_path,
                config=strict_config,
                storage_root=storage_root / "strict-admission",
            )
            if strict_report.get("status") == "ADMISSION_COMPLETE":
                relative, duplicate = store_original(
                    storage_root=storage_root,
                    payload=payload,
                    digest=digest,
                    zone="originals",
                )
                base.update(
                    {
                        "status": "ACCEPTED_PARSED",
                        "storage_relative_path": relative,
                        "duplicate_upload": duplicate,
                        "parse": parse_summary,
                        "strict_admission": strict_report,
                    }
                )
                return base
            codes = list(strict_report.get("admission_diagnostics", []))
            category = _diagnostic_class(codes)
        except (XlsxInspectionError, WindowsRunnerError) as exc:
            parse_summary = None
            codes = [getattr(exc, "code", "XLSX_INSPECTION_FAILED")]
            category = _diagnostic_class(codes)

        if category == "MODEL_LIMITATION":
            relative, duplicate = store_original(
                storage_root=storage_root,
                payload=payload,
                digest=digest,
                zone="originals",
            )
            base.update(
                {
                    "status": "ACCEPTED_PARTIAL",
                    "storage_relative_path": relative,
                    "duplicate_upload": duplicate,
                    "parse": parse_summary,
                    "strict_admission": None,
                    "diagnostics": codes,
                    "limitations": base["limitations"] + [
                        "STRICT_XLSX_MODEL_LIMITATION",
                        "BUSINESS_ADAPTER_REQUIRED",
                    ],
                }
            )
            return base

        zone = (
            "quarantine-security" if category == "SECURITY"
            else "quarantine-corrupted"
        )
        relative, duplicate = store_original(
            storage_root=storage_root, payload=payload, digest=digest, zone=zone
        )
        base.update(
            {
                "status": (
                    "QUARANTINED_SECURITY" if category == "SECURITY"
                    else "QUARANTINED_CORRUPTED"
                ),
                "storage_relative_path": relative,
                "duplicate_upload": duplicate,
                "parse": parse_summary,
                "strict_admission": None,
                "diagnostics": codes,
            }
        )
        return base

    relative, duplicate = store_original(
        storage_root=storage_root,
        payload=payload,
        digest=digest,
        zone="originals",
    )
    base["storage_relative_path"] = relative
    base["duplicate_upload"] = duplicate

    if detection.kind in {"JSON", "XML", "DELIMITED_TEXT", "TEXT"}:
        base.update(
            {
                "status": "ACCEPTED_PARTIAL",
                "parse": text_structure(payload, detection),
                "strict_admission": None,
                "limitations": base["limitations"] + [
                    "BUSINESS_ADAPTER_REQUIRED"
                ],
            }
        )
        return base

    base.update(
        {
            "status": "ACCEPTED_UNPARSED",
            "parse": None,
            "strict_admission": None,
            "limitations": base["limitations"] + [
                "FORMAT_ADAPTER_NOT_AVAILABLE"
            ],
        }
    )
    return base


__all__ = ["AnyFileError", "atomic_json", "intake_file"]
