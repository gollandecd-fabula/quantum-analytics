from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path

from . import universal_gateway as _gateway
from .universal_gateway import (
    IntakeDecision,
    UNIVERSAL_IMPORT_SCHEMA_VERSION,
    UniversalImportError,
)
from .universal_tables import UniversalTableError, extract_tables


_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_PDF_ACTIVE_MARKERS = (
    b"/javascript",
    b"/js",
    b"/embeddedfile",
    b"/launch",
    b"/openaction",
    b"/aa",
    b"/richmedia",
    b"/encrypt",
)


def classify_payload(payload: bytes, suffix: str) -> IntakeDecision:
    """Apply fail-closed policy around the low-level content classifier."""
    if payload.startswith(_OLE_MAGIC):
        return IntakeDecision(
            "QUARANTINED_SECURITY",
            "OLE_COMPOUND_REQUIRES_SANDBOX",
            None,
            {},
            ("OLE_COMPOUND_REQUIRES_DEDICATED_ADAPTER",),
        )
    if payload.startswith(b"%PDF-"):
        lowered = payload.lower()
        if any(marker in lowered for marker in _PDF_ACTIVE_MARKERS):
            return IntakeDecision(
                "QUARANTINED_SECURITY",
                "PDF_ACTIVE_OR_ENCRYPTED_CONTENT",
                None,
                {},
                ("PDF_REQUIRES_SANDBOX",),
            )
    decision = _gateway.classify_payload(payload, suffix)
    if decision.status.startswith("QUARANTINED"):
        return decision
    try:
        extraction = extract_tables(payload, source_name="preview" + suffix)
    except UniversalTableError:
        return decision
    if extraction.tables:
        return IntakeDecision(
            "ACCEPTED_PARTIAL",
            extraction.detected_format,
            "UNIVERSAL_TABLES",
            {**decision.metadata, "extracted_table_count": len(extraction.tables)},
            tuple(
                dict.fromkeys(
                    (
                        *decision.reason_codes,
                        *extraction.reason_codes,
                        "UNIVERSAL_TABLE_EXTRACTION",
                    )
                )
            ),
        )
    if decision.status == "ROUTE_XLSX":
        return IntakeDecision(
            "ACCEPTED_UNPARSED",
            "XLSX",
            None,
            decision.metadata,
            tuple(
                dict.fromkeys(
                    (*decision.reason_codes, "NO_USABLE_TABLE_DATA")
                )
            ),
        )
    return decision


def register_file(
    *,
    file_path: Path,
    storage_root: Path,
    malware_scan_evidence_sha256: str | None = None,
    malware_scan_outcome: str | None = None,
) -> dict[str, object]:
    source = file_path.resolve()
    try:
        payload, digest = _gateway._read_source(source)
        decision = classify_payload(payload, source.suffix)
        extraction_summary: dict[str, object] | None = None
        if not decision.status.startswith("QUARANTINED"):
            try:
                extraction = extract_tables(payload, source_name=source.name)
                extraction_summary = extraction.public_summary()
                if extraction.tables:
                    decision = IntakeDecision(
                        "ACCEPTED_PARTIAL",
                        extraction.detected_format,
                        "UNIVERSAL_TABLES",
                        {**decision.metadata, "extracted_table_count": len(extraction.tables)},
                        tuple(dict.fromkeys((*decision.reason_codes, *extraction.reason_codes))),
                    )
                elif not extraction.tables:
                    decision = IntakeDecision(
                        decision.status,
                        decision.detected_format,
                        decision.route,
                        decision.metadata,
                        tuple(dict.fromkeys((*decision.reason_codes, *extraction.reason_codes))),
                    )
            except UniversalTableError as exc:
                extraction_summary = {
                    "schema_version": "quantum-universal-tables-v1",
                    "status": "ERROR",
                    "detected_format": None,
                    "table_count": 0,
                    "tables": [],
                    "members": [],
                    "reason_codes": [exc.code],
                    "raw_rows_in_report": False,
                }
        destination: Path | None = None
        if decision.status != "ROUTE_XLSX":
            zone = (
                "quarantine"
                if decision.status.startswith("QUARANTINED")
                else "inbox"
            )
            destination = (
                storage_root.resolve()
                / "universal-files"
                / zone
                / digest
                / _gateway._safe_filename(source.name)
            )
            _gateway._atomic_store(source, destination)
        report = _gateway._base_report(
            status=decision.status,
            detected_format=decision.detected_format,
            route=decision.route,
            reason_codes=list(decision.reason_codes),
            malware_scan_evidence_sha256=malware_scan_evidence_sha256,
            malware_scan_outcome=malware_scan_outcome,
        )
        report.update(
            {
                "file_sha256": digest,
                "file_size_bytes": len(payload),
                "sanitized_filename": _gateway._safe_filename(source.name),
                "stored_path": str(destination) if destination is not None else None,
                "metadata": decision.metadata,
                "universal_extraction": extraction_summary,
                "limitations": [
                    "RELEASE_BLOCKED",
                    "UNMAPPED_SEMANTICS_ARE_NOT_GUESSED",
                    "PARTIAL_CALCULATIONS_REQUIRE_EXPLICIT_COVERAGE",
                    "HOME_LOCAL_UNENCRYPTED_STORAGE",
                ],
            }
        )
        return report
    except Exception as exc:
        code = getattr(exc, "code", "UNIVERSAL_IMPORT_UNEXPECTED_ERROR")
        report = _gateway._base_report(
            status="ERROR",
            detected_format=None,
            route=None,
            reason_codes=[code],
            malware_scan_evidence_sha256=malware_scan_evidence_sha256,
            malware_scan_outcome=malware_scan_outcome,
        )
        report.update(
            {
                "file_sha256": None,
                "file_size_bytes": None,
                "sanitized_filename": _gateway._safe_filename(source.name),
                "stored_path": None,
                "metadata": {},
                "limitations": ["RELEASE_BLOCKED"],
            }
        )
        return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safely classify and register any local file"
    )
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--storage-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--authority-attested", action="store_true")
    parser.add_argument("--malware-scan-evidence-sha256")
    parser.add_argument("--malware-scan-outcome")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if not args.authority_attested:
        report = {
            "schema_version": UNIVERSAL_IMPORT_SCHEMA_VERSION,
            "status": "ERROR",
            "detected_format": None,
            "route": None,
            "reason_codes": ["AUTHORITY_ATTESTATION_REQUIRED"],
            "marketplace_write_enabled": False,
            "calculation": None,
            "raw_rows_in_report": False,
            "generated_at_utc": datetime.now(UTC).isoformat(),
        }
        _gateway._atomic_json(args.output, report)
        print(json.dumps(report, ensure_ascii=False))
        return 2
    report = register_file(
        file_path=args.file,
        storage_root=args.storage_root,
        malware_scan_evidence_sha256=args.malware_scan_evidence_sha256,
        malware_scan_outcome=args.malware_scan_outcome,
    )
    _gateway._atomic_json(args.output, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "output": str(args.output),
                "detected_format": report["detected_format"],
                "route": report["route"],
            },
            ensure_ascii=False,
        )
    )
    return 2 if report["status"] in {
        "ERROR",
        "QUARANTINED_SECURITY",
        "QUARANTINED_CORRUPTED",
    } else 0


__all__ = [
    "IntakeDecision",
    "UNIVERSAL_IMPORT_SCHEMA_VERSION",
    "UniversalImportError",
    "classify_payload",
    "main",
    "register_file",
]


if __name__ == "__main__":
    raise SystemExit(main())
