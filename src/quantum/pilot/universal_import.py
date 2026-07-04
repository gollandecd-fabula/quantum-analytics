from __future__ import annotations

import argparse
import csv
from hashlib import sha256
from io import BytesIO, StringIO
import json
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any
from xml.etree import ElementTree
from zipfile import BadZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile


_MAX_FILE_BYTES = 100 * 1024 * 1024
_MAX_ARCHIVE_ENTRIES = 10_000
_MAX_TOTAL_UNCOMPRESSED = 512 * 1024 * 1024
_MAX_ENTRY_UNCOMPRESSED = 128 * 1024 * 1024
_MAX_COMPRESSION_RATIO = 100
_ALLOWED_ZIP_METHODS = {ZIP_STORED, ZIP_DEFLATED}
_BLOCKED_SUFFIXES = (
    ".exe", ".dll", ".com", ".scr", ".js", ".jse", ".vbs", ".vbe",
    ".ps1", ".bat", ".cmd", ".sh", ".py", ".jar", ".msi",
)
_EXECUTABLE_MAGIC = (
    b"MZ", b"\x7fELF", b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe",
)
_XLSX_REQUIRED_PARTS = {
    "[content_types].xml",
    "_rels/.rels",
    "xl/workbook.xml",
    "xl/_rels/workbook.xml.rels",
}
_SAFE_NAME = re.compile(r"[^A-Za-zА-Яа-яЁё0-9._() +\-]+")


class UniversalImportError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _safe_filename(name: str) -> str:
    normalized = _SAFE_NAME.sub("_", Path(name).name).strip(" .")
    return normalized[:240] or "file.bin"


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, indent=2
    ).encode("utf-8")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(encoded)
            handle.flush()
        temporary.replace(path)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def _looks_executable(payload: bytes, suffix: str) -> bool:
    return (
        suffix.casefold() in _BLOCKED_SUFFIXES
        or any(payload.startswith(marker) for marker in _EXECUTABLE_MAGIC)
        or payload.startswith(b"#!")
    )


def _zip_summary(payload: bytes) -> dict[str, Any]:
    try:
        with ZipFile(BytesIO(payload)) as archive:
            infos = archive.infolist()
            if len(infos) > _MAX_ARCHIVE_ENTRIES:
                raise UniversalImportError("ARCHIVE_ENTRY_LIMIT_EXCEEDED")
            total = 0
            names: list[str] = []
            seen: set[str] = set()
            for info in infos:
                name = info.filename.replace("\\", "/")
                parts = name.split("/")
                if (
                    not name
                    or name.startswith("/")
                    or any(part in {"", ".", ".."} for part in parts)
                    or re.match(r"^[A-Za-z]:", name)
                ):
                    raise UniversalImportError("ARCHIVE_PATH_INVALID")
                key = name.casefold()
                if key in seen:
                    raise UniversalImportError("ARCHIVE_DUPLICATE_PATH")
                seen.add(key)
                if info.flag_bits & 0x1:
                    raise UniversalImportError("ARCHIVE_ENCRYPTED_ENTRY")
                if info.compress_type not in _ALLOWED_ZIP_METHODS:
                    raise UniversalImportError("ARCHIVE_COMPRESSION_UNSUPPORTED")
                if info.file_size > _MAX_ENTRY_UNCOMPRESSED:
                    raise UniversalImportError("ARCHIVE_ENTRY_SIZE_EXCEEDED")
                total += info.file_size
                if total > _MAX_TOTAL_UNCOMPRESSED:
                    raise UniversalImportError("ARCHIVE_TOTAL_SIZE_EXCEEDED")
                if info.file_size and (
                    info.compress_size == 0
                    or info.file_size > info.compress_size * _MAX_COMPRESSION_RATIO
                ):
                    raise UniversalImportError("ARCHIVE_COMPRESSION_RATIO_EXCEEDED")
                if key.endswith(_BLOCKED_SUFFIXES):
                    raise UniversalImportError("ARCHIVE_ACTIVE_CONTENT_FORBIDDEN")
                if not info.is_dir():
                    names.append(name)
            lowered = {name.casefold() for name in names}
            inner_xlsx = [name for name in names if name.casefold().endswith(".xlsx")]
            return {
                "entries": len(infos),
                "total_uncompressed_bytes": total,
                "is_xlsx": _XLSX_REQUIRED_PARTS.issubset(lowered),
                "is_single_xlsx_wrapper": len(names) == 1 and len(inner_xlsx) == 1,
            }
    except UniversalImportError:
        raise
    except BadZipFile as exc:
        raise UniversalImportError("ARCHIVE_CORRUPTED") from exc


def _classify(payload: bytes, suffix: str) -> tuple[str, str, dict[str, Any]]:
    if _looks_executable(payload, suffix):
        return "QUARANTINED_SECURITY", "EXECUTABLE_OR_SCRIPT_CONTENT", {}
    if payload.startswith(b"PK\x03\x04"):
        summary = _zip_summary(payload)
        if summary["is_xlsx"] or summary["is_single_xlsx_wrapper"]:
            return "ROUTE_XLSX", "XLSX_OR_ZIP_XLSX", summary
        return "ACCEPTED_UNPARSED", "SAFE_ARCHIVE_UNSUPPORTED", summary
    if payload.startswith(b"%PDF-"):
        return "ACCEPTED_PARTIAL", "PDF", {"signature": "PDF"}
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "ACCEPTED_PARTIAL", "PNG", {"signature": "PNG"}
    if payload.startswith(b"\xff\xd8\xff"):
        return "ACCEPTED_PARTIAL", "JPEG", {"signature": "JPEG"}
    if payload.startswith((b"GIF87a", b"GIF89a")):
        return "ACCEPTED_PARTIAL", "GIF", {"signature": "GIF"}
    if payload.startswith((b"II*\x00", b"MM\x00*")):
        return "ACCEPTED_PARTIAL", "TIFF", {"signature": "TIFF"}
    if payload.startswith(b"RIFF") and len(payload) >= 12 and payload[8:12] == b"WEBP":
        return "ACCEPTED_PARTIAL", "WEBP", {"signature": "WEBP"}
    if payload.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return "ACCEPTED_UNPARSED", "OLE_COMPOUND", {}
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        return "ACCEPTED_UNPARSED", "UNKNOWN_BINARY", {}
    upper = text.upper()
    if "<!DOCTYPE" in upper or "<!ENTITY" in upper:
        return "QUARANTINED_SECURITY", "XML_ENTITY_DECLARATION_FORBIDDEN", {}
    stripped = text.lstrip()
    if stripped.startswith(("{", "[")):
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            return "QUARANTINED_CORRUPTED", "JSON_INVALID", {}
        return "ACCEPTED_PARTIAL", "JSON", {
            "root_type": type(value).__name__,
            "item_count": len(value) if isinstance(value, (dict, list)) else None,
        }
    if stripped.startswith("<"):
        try:
            root = ElementTree.fromstring(text)
        except ElementTree.ParseError:
            return "QUARANTINED_CORRUPTED", "XML_INVALID", {}
        return "ACCEPTED_PARTIAL", "XML", {"root_tag": root.tag}
    try:
        sample = text[:64_000]
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        rows = list(csv.reader(StringIO(sample), dialect))
        if rows and len(rows[0]) > 1:
            return "ACCEPTED_PARTIAL", "DELIMITED_TEXT", {
                "delimiter": dialect.delimiter,
                "sample_rows": len(rows),
                "sample_columns": len(rows[0]),
            }
    except csv.Error:
        pass
    return "ACCEPTED_UNPARSED", "TEXT_UNCLASSIFIED", {
        "character_count": len(text),
    }


def register_file(
    *,
    file_path: Path,
    storage_root: Path,
    malware_scan_evidence_sha256: str | None = None,
    malware_scan_outcome: str | None = None,
) -> dict[str, Any]:
    if not file_path.is_file():
        raise UniversalImportError("FILE_NOT_FOUND")
    payload = file_path.read_bytes()
    if not payload:
        raise UniversalImportError("FILE_EMPTY")
    if len(payload) > _MAX_FILE_BYTES:
        raise UniversalImportError("FILE_SIZE_EXCEEDED")
    digest = sha256(payload).hexdigest()
    try:
        status, detected_format, metadata = _classify(payload, file_path.suffix)
    except UniversalImportError as exc:
        status = (
            "QUARANTINED_SECURITY"
            if any(token in exc.code for token in ("ACTIVE_CONTENT", "ENCRYPTED"))
            else "QUARANTINED_CORRUPTED"
        )
        detected_format = exc.code
        metadata = {}
    destination: Path | None = None
    if status != "ROUTE_XLSX":
        zone = "quarantine" if status.startswith("QUARANTINED") else "inbox"
        destination = (
            storage_root.resolve()
            / "universal-files"
            / zone
            / digest
            / _safe_filename(file_path.name)
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copyfile(file_path, destination)
    return {
        "status": status,
        "detected_format": detected_format,
        "file_sha256": digest,
        "file_size_bytes": len(payload),
        "sanitized_filename": _safe_filename(file_path.name),
        "stored_path": str(destination) if destination is not None else None,
        "metadata": metadata,
        "malware_scan_evidence_sha256": malware_scan_evidence_sha256,
        "malware_scan_outcome": malware_scan_outcome,
        "authority_attested": True,
        "runtime_profile": "HOME_LOCAL",
        "storage_encryption_required": False,
        "marketplace_write_enabled": False,
        "calculation": None,
        "limitations": [
            "PILOT_READY_NOT_ASSERTED",
            "UNPARSED_FILES_NOT_USED_FOR_FINANCE",
            "HOME_LOCAL_UNENCRYPTED_STORAGE",
        ],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Register any safe local file without inventing parsed data"
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
    try:
        if not args.authority_attested:
            raise UniversalImportError("AUTHORITY_ATTESTATION_REQUIRED")
        report = register_file(
            file_path=args.file,
            storage_root=args.storage_root,
            malware_scan_evidence_sha256=args.malware_scan_evidence_sha256,
            malware_scan_outcome=args.malware_scan_outcome,
        )
        _atomic_json(args.output, report)
        print(json.dumps({
            "status": report["status"],
            "output": str(args.output),
            "detected_format": report["detected_format"],
        }, ensure_ascii=False))
        return 2 if report["status"].startswith("QUARANTINED") else 0
    except Exception as exc:
        code = getattr(exc, "code", "UNIVERSAL_IMPORT_UNEXPECTED_ERROR")
        print(json.dumps({"status": "ERROR", "code": code}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
