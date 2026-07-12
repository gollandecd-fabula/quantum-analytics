from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from .dashboard import (
    INTERACTIVE_DASHBOARD_SCHEMA_VERSION,
    render_dashboard_html,
)
from .local_bundle import (
    EXPECTED_XLSX_SHEETS,
    LOCAL_OUTPUT_MANIFEST_SCHEMA_VERSION,
    OutputBundleError,
    _canonical_json_bytes,
    build_local_output_bundle,
    render_xlsx_report,
    validate_local_output_bundle,
)


_SAFE_TOKEN = re.compile(r"[^A-Za-z0-9._-]+")
_HASH = re.compile(r"^[0-9a-f]{64}$")
_OUTPUT_ARTIFACT_NAMES = (
    "Quantum_Report.xlsx",
    "dashboard.html",
    "quantum_result.json",
    "recommendations.json",
)
_MANIFEST_NAME = "evidence_manifest.json"


def _json_bytes(value: Any) -> bytes:
    return _canonical_json_bytes(value)


def _chmod(path: Path, mode: int) -> None:
    try:
        path.chmod(mode)
    except OSError:
        pass


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _write_payload(path: Path, payload: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    _chmod(path, 0o600)


def _artifact(name: str, payload: bytes) -> dict[str, Any]:
    return {
        "name": name,
        "size_bytes": len(payload),
        "sha256": sha256(payload).hexdigest(),
    }


def _manifest_hash(manifest: Mapping[str, Any]) -> str:
    return sha256(
        _json_bytes(
            {
                key: value
                for key, value in manifest.items()
                if key != "manifest_hash"
            }
        )
    ).hexdigest()


def _build_manifest(
    bundle: Mapping[str, Any],
    payloads: Mapping[str, bytes],
) -> dict[str, Any]:
    artifacts = [_artifact(name, payloads[name]) for name in sorted(payloads)]
    manifest: dict[str, Any] = {
        "schema_version": LOCAL_OUTPUT_MANIFEST_SCHEMA_VERSION,
        "bundle_id": bundle["bundle_id"],
        "bundle_hash": bundle["bundle_hash"],
        "generated_at": bundle["generated_at"],
        "manifest_excludes_self": True,
        "artifact_count": len(artifacts),
        "artifact_names": sorted(payloads),
        "artifacts": artifacts,
        "manifest_hash": "",
    }
    manifest["manifest_hash"] = _manifest_hash(manifest)
    return manifest


def validate_local_output_manifest(manifest: object) -> None:
    expected = {
        "schema_version",
        "bundle_id",
        "bundle_hash",
        "generated_at",
        "manifest_excludes_self",
        "artifact_count",
        "artifact_names",
        "artifacts",
        "manifest_hash",
    }
    if not isinstance(manifest, Mapping) or set(manifest) != expected:
        raise OutputBundleError("OUTPUT_MANIFEST_FIELDS_INVALID")
    if manifest.get("schema_version") != LOCAL_OUTPUT_MANIFEST_SCHEMA_VERSION:
        raise OutputBundleError("OUTPUT_MANIFEST_SCHEMA_UNSUPPORTED")
    if manifest.get("manifest_excludes_self") is not True:
        raise OutputBundleError("OUTPUT_MANIFEST_SELF_POLICY_INVALID")
    bundle_hash = manifest.get("bundle_hash")
    manifest_hash = manifest.get("manifest_hash")
    if not isinstance(bundle_hash, str) or _HASH.fullmatch(bundle_hash) is None:
        raise OutputBundleError("OUTPUT_MANIFEST_BUNDLE_HASH_INVALID")
    if not isinstance(manifest_hash, str) or _HASH.fullmatch(manifest_hash) is None:
        raise OutputBundleError("OUTPUT_MANIFEST_HASH_INVALID")
    names = manifest.get("artifact_names")
    artifacts = manifest.get("artifacts")
    count = manifest.get("artifact_count")
    if (
        not isinstance(names, list)
        or names != sorted(_OUTPUT_ARTIFACT_NAMES)
        or not isinstance(artifacts, list)
        or not isinstance(count, int)
        or isinstance(count, bool)
        or count != len(artifacts)
        or count != len(names)
    ):
        raise OutputBundleError("OUTPUT_MANIFEST_ARTIFACTS_INVALID")
    seen: set[str] = set()
    for item in artifacts:
        if not isinstance(item, Mapping) or set(item) != {
            "name",
            "size_bytes",
            "sha256",
        }:
            raise OutputBundleError("OUTPUT_MANIFEST_ARTIFACT_INVALID")
        name = item.get("name")
        size = item.get("size_bytes")
        digest = item.get("sha256")
        if (
            not isinstance(name, str)
            or name not in names
            or name in seen
            or Path(name).name != name
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
            or not isinstance(digest, str)
            or _HASH.fullmatch(digest) is None
        ):
            raise OutputBundleError("OUTPUT_MANIFEST_ARTIFACT_INVALID")
        seen.add(name)
    if seen != set(names):
        raise OutputBundleError("OUTPUT_MANIFEST_ARTIFACTS_INVALID")
    if manifest_hash != _manifest_hash(manifest):
        raise OutputBundleError("OUTPUT_MANIFEST_HASH_MISMATCH")


def _read_json(path: Path, code: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OutputBundleError(code) from exc


def _xlsx_sheet_names(path: Path) -> tuple[str, ...]:
    try:
        with ZipFile(path) as archive:
            workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
            sheets = workbook.find(
                "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheets"
            )
            if sheets is None:
                raise OutputBundleError("OUTPUT_XLSX_SHEETS_MISSING")
            names = tuple(item.get("name") or "" for item in list(sheets))
            for name in archive.namelist():
                if name.startswith("xl/worksheets/") and name.endswith(".xml"):
                    payload = archive.read(name)
                    worksheet = ElementTree.fromstring(payload)
                    formulas = worksheet.findall(
                        ".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}f"
                    )
                    if formulas:
                        raise OutputBundleError("OUTPUT_XLSX_FORMULA_FORBIDDEN")
            return names
    except (BadZipFile, KeyError, ElementTree.ParseError, OSError) as exc:
        raise OutputBundleError("OUTPUT_XLSX_INVALID") from exc


def _verify_dashboard_payload(payload: bytes, bundle_hash: str) -> None:
    required = (
        bundle_hash.encode("ascii"),
        b'id="bundle-data"',
        f'data-dashboard-schema="{INTERACTIVE_DASHBOARD_SCHEMA_VERSION}"'.encode(
            "ascii"
        ),
        b'http-equiv="Content-Security-Policy"',
        b"connect-src 'none'",
        b"object-src 'none'",
        b"frame-src 'none'",
        b"form-action 'none'",
    )
    if any(item not in payload for item in required):
        raise OutputBundleError("OUTPUT_DASHBOARD_BUNDLE_MISMATCH")
    forbidden = (
        b"http://",
        b"https://",
        b"<iframe",
        b"<object",
        b"<embed",
        b"<link",
        b"<base",
        b' src="',
        b" src='",
        b"fetch(",
        b"XMLHttpRequest",
        b"WebSocket",
        b"EventSource",
        b"sendBeacon",
        b".innerHTML",
        b"document.write",
        b"eval(",
    )
    if any(item in payload for item in forbidden):
        raise OutputBundleError("OUTPUT_DASHBOARD_EXTERNAL_RESOURCE_FORBIDDEN")


def verify_local_output_directory(directory: Path) -> dict[str, Any]:
    if not isinstance(directory, Path) or not directory.is_dir() or directory.is_symlink():
        raise OutputBundleError("OUTPUT_DIRECTORY_INVALID")
    expected_files = set(_OUTPUT_ARTIFACT_NAMES) | {_MANIFEST_NAME}
    actual_files = {
        item.name
        for item in directory.iterdir()
        if item.is_file() and not item.is_symlink()
    }
    if actual_files != expected_files or any(item.is_symlink() for item in directory.iterdir()):
        raise OutputBundleError("OUTPUT_DIRECTORY_CONTENT_INVALID")
    manifest = _read_json(
        directory / _MANIFEST_NAME,
        "OUTPUT_MANIFEST_JSON_INVALID",
    )
    validate_local_output_manifest(manifest)
    by_name = {item["name"]: item for item in manifest["artifacts"]}
    for name in manifest["artifact_names"]:
        path = directory / name
        payload = path.read_bytes()
        item = by_name[name]
        if len(payload) != item["size_bytes"]:
            raise OutputBundleError("OUTPUT_ARTIFACT_SIZE_MISMATCH:" + name)
        if sha256(payload).hexdigest() != item["sha256"]:
            raise OutputBundleError("OUTPUT_ARTIFACT_HASH_MISMATCH:" + name)

    bundle = _read_json(
        directory / "quantum_result.json",
        "OUTPUT_BUNDLE_JSON_INVALID",
    )
    validate_local_output_bundle(bundle)
    if bundle["bundle_hash"] != manifest["bundle_hash"]:
        raise OutputBundleError("OUTPUT_MANIFEST_BUNDLE_MISMATCH")
    recommendations = _read_json(
        directory / "recommendations.json",
        "OUTPUT_RECOMMENDATIONS_JSON_INVALID",
    )
    if _json_bytes(recommendations) != _json_bytes(bundle["recommendations"]):
        raise OutputBundleError("OUTPUT_RECOMMENDATIONS_MISMATCH")
    dashboard = (directory / "dashboard.html").read_bytes()
    _verify_dashboard_payload(dashboard, bundle["bundle_hash"])
    if _xlsx_sheet_names(directory / "Quantum_Report.xlsx") != EXPECTED_XLSX_SHEETS:
        raise OutputBundleError("OUTPUT_XLSX_SHEET_CONTRACT_INVALID")
    return {
        "status": "OUTPUT_BUNDLE_VERIFIED",
        "bundle_hash": bundle["bundle_hash"],
        "manifest_hash": manifest["manifest_hash"],
        "artifact_count": manifest["artifact_count"] + 1,
    }


def _result(
    *,
    status: str,
    target: Path,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    artifacts = [
        {
            **item,
            "path": str(target / item["name"]),
        }
        for item in manifest["artifacts"]
    ]
    manifest_payload = (target / _MANIFEST_NAME).read_bytes()
    artifacts.append(
        {
            **_artifact(_MANIFEST_NAME, manifest_payload),
            "path": str(target / _MANIFEST_NAME),
        }
    )
    return {
        "status": status,
        "schema_version": LOCAL_OUTPUT_MANIFEST_SCHEMA_VERSION,
        "directory": str(target),
        "bundle_hash": manifest["bundle_hash"],
        "manifest_hash": manifest["manifest_hash"],
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
    }


def write_local_output_bundle(
    report: Mapping[str, Any],
    *,
    output_root: Path,
    generated_at: datetime | str,
) -> dict[str, Any]:
    if not isinstance(output_root, Path):
        raise OutputBundleError("OUTPUT_ROOT_INVALID")
    root = output_root.resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    _chmod(root, 0o700)
    bundle = build_local_output_bundle(report, generated_at=generated_at)
    token = _SAFE_TOKEN.sub("-", str(bundle["dataset_id"])).strip("-._")
    if not token:
        token = "dataset"
    target = root / (
        "quantum_" + token[:60] + "_" + str(bundle["bundle_hash"])[:16]
    )
    if target.exists():
        verified = verify_local_output_directory(target)
        if verified["bundle_hash"] != bundle["bundle_hash"]:
            raise OutputBundleError("OUTPUT_EXISTING_BUNDLE_CONFLICT")
        manifest = _read_json(
            target / _MANIFEST_NAME,
            "OUTPUT_MANIFEST_JSON_INVALID",
        )
        return _result(
            status="OUTPUT_BUNDLE_REUSED",
            target=target,
            manifest=manifest,
        )

    payloads = {
        "quantum_result.json": _json_bytes(bundle),
        "recommendations.json": _json_bytes(bundle["recommendations"]),
        "Quantum_Report.xlsx": render_xlsx_report(bundle),
        "dashboard.html": render_dashboard_html(bundle),
    }
    if set(payloads) != set(_OUTPUT_ARTIFACT_NAMES):
        raise OutputBundleError("OUTPUT_ARTIFACT_SET_INVALID")
    manifest = _build_manifest(bundle, payloads)
    manifest_payload = _json_bytes(manifest)
    staging = Path(
        tempfile.mkdtemp(
            prefix="." + target.name + ".staging-",
            dir=root,
        )
    )
    _chmod(staging, 0o700)
    try:
        for name in sorted(payloads):
            _write_payload(staging / name, payloads[name])
        _write_payload(staging / _MANIFEST_NAME, manifest_payload)
        _fsync_directory(staging)
        verify_local_output_directory(staging)
        if target.exists():
            verified = verify_local_output_directory(target)
            if verified["bundle_hash"] != bundle["bundle_hash"]:
                raise OutputBundleError("OUTPUT_EXISTING_BUNDLE_CONFLICT")
            shutil.rmtree(staging)
            existing_manifest = _read_json(
                target / _MANIFEST_NAME,
                "OUTPUT_MANIFEST_JSON_INVALID",
            )
            return _result(
                status="OUTPUT_BUNDLE_REUSED",
                target=target,
                manifest=existing_manifest,
            )
        os.replace(staging, target)
        _chmod(target, 0o700)
        _fsync_directory(root)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise
    verify_local_output_directory(target)
    return _result(
        status="OUTPUT_BUNDLE_COMPLETE",
        target=target,
        manifest=manifest,
    )
