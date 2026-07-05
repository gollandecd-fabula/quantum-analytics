from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from io import BytesIO, StringIO
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
from typing import Any
import unicodedata
from xml.etree import ElementTree
from zipfile import BadZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo
from zlib import error as ZlibError


UNIVERSAL_IMPORT_SCHEMA_VERSION = "quantum-universal-import-v1"

_MAX_FILE_BYTES = 100 * 1024 * 1024
_MAX_STRUCTURED_TEXT_BYTES = 16 * 1024 * 1024
_MAX_ARCHIVE_ENTRIES = 10_000
_MAX_TOTAL_UNCOMPRESSED = 512 * 1024 * 1024
_MAX_ENTRY_UNCOMPRESSED = 128 * 1024 * 1024
_MAX_COMPRESSION_RATIO = 100
_MAX_MEMBER_PREFIX_BYTES = 4096
_MAX_SAMPLE_TEXT_CHARS = 256_000
_ALLOWED_ZIP_METHODS = frozenset({ZIP_STORED, ZIP_DEFLATED})

_BLOCKED_SUFFIXES = (
    ".exe",
    ".dll",
    ".com",
    ".scr",
    ".js",
    ".jse",
    ".vbs",
    ".vbe",
    ".ps1",
    ".bat",
    ".cmd",
    ".sh",
    ".py",
    ".jar",
    ".msi",
)
_BLOCKED_OFFICE_PATH_MARKERS = (
    "xl/activex/",
    "xl/embeddings/",
    "xl/externallinks/",
    "customui/",
    "vbaproject.bin",
)
_EXECUTABLE_MAGIC = (
    b"MZ",
    b"\x7fELF",
    b"\xfe\xed\xfa\xce",
    b"\xce\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf",
    b"\xcf\xfa\xed\xfe",
)
_XLSX_REQUIRED_PARTS = frozenset(
    {
        "[content_types].xml",
        "_rels/.rels",
        "xl/workbook.xml",
        "xl/_rels/workbook.xml.rels",
    }
)
_SAFE_NAME = re.compile(r"[^A-Za-zА-Яа-яЁё0-9._() +\-]+")
_URI_SCHEME = re.compile(rb"(?:https?|ftp|file|mailto|mhtml):", re.IGNORECASE)


class UniversalImportError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class IntakeDecision:
    status: str
    detected_format: str
    route: str | None
    metadata: dict[str, Any]
    reason_codes: tuple[str, ...] = ()


def _safe_filename(name: str) -> str:
    normalized = _SAFE_NAME.sub("_", Path(name).name).strip(" .")
    return normalized[:240] or "file.bin"


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path = path.resolve()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    ).encode("utf-8")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def _atomic_store(source: Path, destination: Path) -> None:
    destination = destination.resolve()
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if destination.exists():
        return
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
            temporary = Path(handle.name)
            with source.open("rb") as source_handle:
                shutil.copyfileobj(source_handle, handle, length=1024 * 1024)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        try:
            destination.chmod(0o600)
        except OSError:
            pass
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def _read_source(path: Path) -> tuple[bytes, str]:
    if not path.is_file():
        raise UniversalImportError("FILE_NOT_FOUND")
    size = path.stat().st_size
    if size < 1:
        raise UniversalImportError("FILE_EMPTY")
    if size > _MAX_FILE_BYTES:
        raise UniversalImportError("FILE_SIZE_EXCEEDED")
    digest = sha256()
    chunks: list[bytes] = []
    total = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > _MAX_FILE_BYTES:
                raise UniversalImportError("FILE_SIZE_EXCEEDED")
            digest.update(chunk)
            chunks.append(chunk)
    payload = b"".join(chunks)
    if len(payload) != size:
        raise UniversalImportError("FILE_READ_MISMATCH")
    return payload, digest.hexdigest()


def _looks_executable(payload: bytes, suffix: str) -> bool:
    return (
        suffix.casefold() in _BLOCKED_SUFFIXES
        or any(payload.startswith(marker) for marker in _EXECUTABLE_MAGIC)
        or payload.startswith(b"#!")
    )


def _is_symlink(info: ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(mode)


def _safe_member_name(name: str) -> str:
    if not isinstance(name, str) or not name or "\x00" in name:
        raise UniversalImportError("ARCHIVE_PATH_INVALID")
    normalized = name.replace("\\", "/")
    if normalized.startswith("//") or re.match(r"^[A-Za-z]:", normalized):
        raise UniversalImportError("ARCHIVE_PATH_INVALID")
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise UniversalImportError("ARCHIVE_PATH_INVALID")
    canonical = unicodedata.normalize("NFC", str(path))
    if any(":" in part for part in PurePosixPath(canonical).parts):
        raise UniversalImportError("ARCHIVE_PATH_INVALID")
    return canonical


def _member_prefix(archive: ZipFile, info: ZipInfo) -> bytes:
    try:
        with archive.open(info, "r") as stream:
            return stream.read(_MAX_MEMBER_PREFIX_BYTES)
    except (
        BadZipFile,
        RuntimeError,
        NotImplementedError,
        OSError,
        EOFError,
        ZlibError,
    ) as exc:
        raise UniversalImportError("ARCHIVE_READ_FAILED") from exc


def _validate_relationship_payload(name: str, prefix: bytes) -> None:
    lowered = prefix.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise UniversalImportError("ARCHIVE_XML_ENTITY_DECLARATION_FORBIDDEN")
    if name.casefold().endswith(".rels"):
        if b'targetmode="external"' in lowered or b"targetmode='external'" in lowered:
            raise UniversalImportError("ARCHIVE_EXTERNAL_RELATIONSHIP_FORBIDDEN")
        if _URI_SCHEME.search(lowered):
            raise UniversalImportError("ARCHIVE_EXTERNAL_RELATIONSHIP_FORBIDDEN")


def _zip_summary(payload: bytes, *, allow_single_xlsx_wrapper: bool = True) -> dict[str, Any]:
    try:
        with ZipFile(BytesIO(payload)) as archive:
            infos = archive.infolist()
            if not infos:
                raise UniversalImportError("ARCHIVE_EMPTY")
            if len(infos) > _MAX_ARCHIVE_ENTRIES:
                raise UniversalImportError("ARCHIVE_ENTRY_LIMIT_EXCEEDED")
            total = 0
            files: list[str] = []
            seen: set[str] = set()
            inner_xlsx_info: ZipInfo | None = None
            for info in infos:
                name = _safe_member_name(info.filename)
                key = unicodedata.normalize("NFC", name).casefold()
                if key in seen:
                    raise UniversalImportError("ARCHIVE_DUPLICATE_PATH")
                seen.add(key)
                if info.flag_bits & 0x1:
                    raise UniversalImportError("ARCHIVE_ENCRYPTED_ENTRY")
                if info.compress_type not in _ALLOWED_ZIP_METHODS:
                    raise UniversalImportError("ARCHIVE_COMPRESSION_UNSUPPORTED")
                if _is_symlink(info):
                    raise UniversalImportError("ARCHIVE_SYMLINK_FORBIDDEN")
                if info.file_size > _MAX_ENTRY_UNCOMPRESSED:
                    raise UniversalImportError("ARCHIVE_ENTRY_SIZE_EXCEEDED")
                total += info.file_size
                if total > _MAX_TOTAL_UNCOMPRESSED:
                    raise UniversalImportError("ARCHIVE_TOTAL_SIZE_EXCEEDED")
                if info.file_size:
                    if info.compress_size == 0:
                        raise UniversalImportError("ARCHIVE_COMPRESSION_RATIO_EXCEEDED")
                    if info.file_size > info.compress_size * _MAX_COMPRESSION_RATIO:
                        raise UniversalImportError("ARCHIVE_COMPRESSION_RATIO_EXCEEDED")
                if info.is_dir():
                    continue
                lower = key
                prefix = _member_prefix(archive, info)
                if (
                    lower.endswith(_BLOCKED_SUFFIXES)
                    or any(marker in lower for marker in _BLOCKED_OFFICE_PATH_MARKERS)
                    or _looks_executable(prefix, PurePosixPath(lower).suffix)
                ):
                    raise UniversalImportError("ARCHIVE_ACTIVE_CONTENT_FORBIDDEN")
                if lower.endswith((".xml", ".rels")):
                    _validate_relationship_payload(name, prefix)
                files.append(name)
                if lower.endswith(".xlsx"):
                    if inner_xlsx_info is not None:
                        inner_xlsx_info = None
                    else:
                        inner_xlsx_info = info
            lowered_files = {item.casefold() for item in files}
            is_xlsx = _XLSX_REQUIRED_PARTS.issubset(lowered_files)
            is_single_wrapper = (
                allow_single_xlsx_wrapper
                and len(files) == 1
                and inner_xlsx_info is not None
            )
            inner_xlsx_sha256: str | None = None
            if is_single_wrapper:
                try:
                    inner_payload = archive.read(inner_xlsx_info)
                except (
                    BadZipFile,
                    RuntimeError,
                    NotImplementedError,
                    OSError,
                    EOFError,
                    ZlibError,
                ) as exc:
                    raise UniversalImportError("ARCHIVE_READ_FAILED") from exc
                if len(inner_payload) != inner_xlsx_info.file_size:
                    raise UniversalImportError("ARCHIVE_READ_MISMATCH")
                inner_summary = _zip_summary(
                    inner_payload,
                    allow_single_xlsx_wrapper=False,
                )
                if not inner_summary["is_xlsx"]:
                    raise UniversalImportError("ARCHIVE_SINGLE_XLSX_INVALID")
                inner_xlsx_sha256 = sha256(inner_payload).hexdigest()
            return {
                "entries": len(infos),
                "file_entries": len(files),
                "total_uncompressed_bytes": total,
                "is_xlsx": is_xlsx,
                "is_single_xlsx_wrapper": is_single_wrapper,
                "inner_xlsx_sha256": inner_xlsx_sha256,
            }
    except UniversalImportError:
        raise
    except BadZipFile as exc:
        raise UniversalImportError("ARCHIVE_CORRUPTED") from exc


def _decode_text(payload: bytes) -> tuple[str, str] | None:
    candidates: tuple[tuple[str, bytes], ...] = (
        ("utf-8-sig", payload),
        ("utf-16", payload),
        ("cp1251", payload),
    )
    for encoding, candidate in candidates:
        try:
            text = candidate.decode(encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
        if "\x00" in text and encoding != "utf-16":
            continue
        return text, encoding
    return None


def _classify_text(payload: bytes) -> IntakeDecision:
    decoded = _decode_text(payload)
    if decoded is None:
        return IntakeDecision(
            "ACCEPTED_UNPARSED",
            "UNKNOWN_BINARY",
            None,
            {},
            ("BINARY_FORMAT_NOT_MAPPED",),
        )
    text, encoding = decoded
    upper = text.upper()
    if "<!DOCTYPE" in upper or "<!ENTITY" in upper:
        return IntakeDecision(
            "QUARANTINED_SECURITY",
            "XML_ENTITY_DECLARATION_FORBIDDEN",
            None,
            {"encoding": encoding},
            ("XML_ENTITY_DECLARATION_FORBIDDEN",),
        )
    stripped = text.lstrip()
    if len(payload) <= _MAX_STRUCTURED_TEXT_BYTES and stripped.startswith(("{", "[")):
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            return IntakeDecision(
                "QUARANTINED_CORRUPTED",
                "JSON_INVALID",
                None,
                {"encoding": encoding},
                ("JSON_INVALID",),
            )
        metadata: dict[str, Any] = {
            "encoding": encoding,
            "root_type": type(value).__name__,
            "item_count": len(value) if isinstance(value, (dict, list)) else None,
        }
        if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
            headers = sorted({str(key) for item in value for key in item})
            metadata.update(
                {
                    "table_candidate": True,
                    "column_count": len(headers),
                    "row_count": len(value),
                    "headers": headers[:500],
                }
            )
            return IntakeDecision("ACCEPTED_PARTIAL", "JSON_TABLE", "JSON", metadata)
        return IntakeDecision("ACCEPTED_PARTIAL", "JSON", "JSON", metadata)
    if len(payload) <= _MAX_STRUCTURED_TEXT_BYTES and stripped.startswith("<"):
        try:
            root = ElementTree.fromstring(text)
        except ElementTree.ParseError:
            return IntakeDecision(
                "QUARANTINED_CORRUPTED",
                "XML_INVALID",
                None,
                {"encoding": encoding},
                ("XML_INVALID",),
            )
        return IntakeDecision(
            "ACCEPTED_PARTIAL",
            "XML",
            "XML",
            {
                "encoding": encoding,
                "root_tag": root.tag,
                "element_count": sum(1 for _ in root.iter()),
            },
        )
    sample = text[:_MAX_SAMPLE_TEXT_CHARS]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        rows = list(csv.reader(StringIO(sample), dialect))
    except (csv.Error, UnicodeError):
        rows = []
        dialect = None
    if dialect is not None and rows and len(rows[0]) > 1:
        header = [item.strip() for item in rows[0]]
        return IntakeDecision(
            "ACCEPTED_PARTIAL",
            "DELIMITED_TEXT",
            "DELIMITED_TEXT",
            {
                "encoding": encoding,
                "delimiter": dialect.delimiter,
                "sample_rows": len(rows),
                "sample_columns": len(rows[0]),
                "headers": header[:500],
            },
        )
    return IntakeDecision(
        "ACCEPTED_UNPARSED",
        "TEXT_UNCLASSIFIED",
        None,
        {"encoding": encoding, "character_count": len(text)},
        ("TEXT_SCHEMA_NOT_MAPPED",),
    )


def classify_payload(payload: bytes, suffix: str) -> IntakeDecision:
    if not isinstance(payload, bytes) or not payload:
        raise UniversalImportError("FILE_BYTES_REQUIRED")
    if _looks_executable(payload, suffix):
        return IntakeDecision(
            "QUARANTINED_SECURITY",
            "EXECUTABLE_OR_SCRIPT_CONTENT",
            None,
            {},
            ("EXECUTABLE_OR_SCRIPT_CONTENT",),
        )
    if payload.startswith(b"PK\x03\x04"):
        try:
            summary = _zip_summary(payload)
        except UniversalImportError as exc:
            status = (
                "QUARANTINED_SECURITY"
                if any(
                    token in exc.code
                    for token in (
                        "ACTIVE_CONTENT",
                        "ENCRYPTED",
                        "EXTERNAL_RELATIONSHIP",
                        "SYMLINK",
                        "PATH_INVALID",
                        "COMPRESSION_RATIO",
                    )
                )
                else "QUARANTINED_CORRUPTED"
            )
            return IntakeDecision(status, exc.code, None, {}, (exc.code,))
        if summary["is_xlsx"]:
            return IntakeDecision("ROUTE_XLSX", "XLSX", "XLSX", summary)
        if summary["is_single_xlsx_wrapper"]:
            return IntakeDecision("ROUTE_XLSX", "ZIP_XLSX", "XLSX", summary)
        return IntakeDecision(
            "ACCEPTED_UNPARSED",
            "SAFE_ARCHIVE_UNSUPPORTED",
            None,
            summary,
            ("ARCHIVE_FORMAT_NOT_MAPPED",),
        )
    if payload.startswith(b"%PDF-"):
        return IntakeDecision("ACCEPTED_PARTIAL", "PDF", "PDF", {"signature": "PDF"})
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return IntakeDecision("ACCEPTED_PARTIAL", "PNG", "IMAGE", {"signature": "PNG"})
    if payload.startswith(b"\xff\xd8\xff"):
        return IntakeDecision("ACCEPTED_PARTIAL", "JPEG", "IMAGE", {"signature": "JPEG"})
    if payload.startswith((b"GIF87a", b"GIF89a")):
        return IntakeDecision("ACCEPTED_PARTIAL", "GIF", "IMAGE", {"signature": "GIF"})
    if payload.startswith((b"II*\x00", b"MM\x00*")):
        return IntakeDecision("ACCEPTED_PARTIAL", "TIFF", "IMAGE", {"signature": "TIFF"})
    if payload.startswith(b"RIFF") and len(payload) >= 12 and payload[8:12] == b"WEBP":
        return IntakeDecision("ACCEPTED_PARTIAL", "WEBP", "IMAGE", {"signature": "WEBP"})
    if payload.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return IntakeDecision(
            "ACCEPTED_UNPARSED",
            "OLE_COMPOUND",
            None,
            {},
            ("OLE_FORMAT_REQUIRES_DEDICATED_ADAPTER",),
        )
    return _classify_text(payload)


def register_file(
    *,
    file_path: Path,
    storage_root: Path,
    malware_scan_evidence_sha256: str | None = None,
    malware_scan_outcome: str | None = None,
) -> dict[str, Any]:
    source = file_path.resolve()
    try:
        payload, digest = _read_source(source)
        decision = classify_payload(payload, source.suffix)
        destination: Path | None = None
        if decision.status != "ROUTE_XLSX":
            zone = "quarantine" if decision.status.startswith("QUARANTINED") else "inbox"
            destination = (
                storage_root.resolve()
                / "universal-files"
                / zone
                / digest
                / _safe_filename(source.name)
            )
            _atomic_store(source, destination)
        return {
            "schema_version": UNIVERSAL_IMPORT_SCHEMA_VERSION,
            "status": decision.status,
            "detected_format": decision.detected_format,
            "route": decision.route,
            "reason_codes": list(decision.reason_codes),
            "file_sha256": digest,
            "file_size_bytes": len(payload),
            "sanitized_filename": _safe_filename(source.name),
            "stored_path": str(destination) if destination is not None else None,
            "metadata": decision.metadata,
            "malware_scan_evidence_sha256": malware_scan_evidence_sha256,
            "malware_scan_outcome": malware_scan_outcome,
            "authority_attested": True,
            "runtime_profile": "HOME_LOCAL",
            "storage_encryption_required": False,
            "marketplace_write_enabled": False,
            "calculation": None,
            "raw_rows_in_report": False,
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "limitations": [
                "RELEASE_BLOCKED",
                "UNPARSED_OR_PARTIAL_FILES_EXCLUDED_FROM_FINANCE",
                "HOME_LOCAL_UNENCRYPTED_STORAGE",
            ],
        }
    except Exception as exc:
        code = getattr(exc, "code", "UNIVERSAL_IMPORT_UNEXPECTED_ERROR")
        return {
            "schema_version": UNIVERSAL_IMPORT_SCHEMA_VERSION,
            "status": "ERROR",
            "detected_format": None,
            "route": None,
            "reason_codes": [code],
            "file_sha256": None,
            "file_size_bytes": None,
            "sanitized_filename": _safe_filename(source.name),
            "stored_path": None,
            "metadata": {},
            "malware_scan_evidence_sha256": malware_scan_evidence_sha256,
            "malware_scan_outcome": malware_scan_outcome,
            "authority_attested": True,
            "runtime_profile": "HOME_LOCAL",
            "storage_encryption_required": False,
            "marketplace_write_enabled": False,
            "calculation": None,
            "raw_rows_in_report": False,
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "limitations": ["RELEASE_BLOCKED"],
        }


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
        }
        _atomic_json(args.output, report)
        print(json.dumps(report, ensure_ascii=False))
        return 2
    report = register_file(
        file_path=args.file,
        storage_root=args.storage_root,
        malware_scan_evidence_sha256=args.malware_scan_evidence_sha256,
        malware_scan_outcome=args.malware_scan_outcome,
    )
    _atomic_json(args.output, report)
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
    return 2 if report["status"] in {"ERROR", "QUARANTINED_SECURITY", "QUARANTINED_CORRUPTED"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
