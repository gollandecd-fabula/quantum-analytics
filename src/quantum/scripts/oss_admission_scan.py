from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantum.dependencies.admission import (
    load_json_document,
    validate_register,
    validate_sbom,
)

ROOT = Path(__file__).resolve().parents[3]
REGISTER_PATH = ROOT / "docs/dependencies/OSS_DEPENDENCY_REGISTER.yaml"
LICENSE_PATH = ROOT / "docs/dependencies/LICENSE_ALLOWLIST.yaml"
SBOM_PATH = ROOT / "docs/dependencies/SBOM.spdx.json"
USER_AGENT = "quantum-analytics-oss-admission/1.0"
OSV_BATCH_URL = "https://api.osv.dev/v1/querybatch"


def request_json(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    attempts: int = 3,
    timeout: int = 30,
) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if payload is not None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                value = json.loads(response.read().decode("utf-8"))
            if not isinstance(value, dict):
                raise RuntimeError("JSON object response required")
            return value
        except (OSError, ValueError, urllib.error.URLError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"request failed after {attempts} attempts: {url}") from last_error


def registry_metadata(component: dict[str, Any]) -> dict[str, Any]:
    name = urllib.parse.quote(component["name"], safe="@/-")
    version = urllib.parse.quote(component["version"], safe=".-")
    if component["ecosystem"] == "PyPI":
        url = f"https://pypi.org/pypi/{name}/{version}/json"
        payload = request_json(url)
        info = payload.get("info")
        if not isinstance(info, dict):
            raise RuntimeError(f"{component['name']}: PyPI info missing")
        license_text = " ".join(
            str(value)
            for value in (
                info.get("license_expression"),
                info.get("license"),
                " ".join(info.get("classifiers", [])),
            )
            if value
        )
        return {
            "registry": "PyPI",
            "registry_url": url,
            "name": info.get("name"),
            "version": info.get("version"),
            "license_text": license_text,
        }

    url = f"https://registry.npmjs.org/{name}/{version}"
    payload = request_json(url)
    return {
        "registry": "npm",
        "registry_url": url,
        "name": payload.get("name"),
        "version": payload.get("version"),
        "license_text": str(payload.get("license", "")),
        "integrity": (payload.get("dist") or {}).get("integrity"),
    }


def _contains_license_token(observed: str, token: str) -> bool:
    pattern = rf"(?<![A-Z0-9]){re.escape(token.upper())}(?![A-Z0-9])"
    return re.search(pattern, observed.upper()) is not None


def license_matches(expected: str, observed: str) -> bool:
    normalized = " ".join(observed.upper().split())
    if expected == "MIT":
        return (
            _contains_license_token(normalized, "MIT")
            or (
                "PERMISSION IS HEREBY GRANTED, FREE OF CHARGE" in normalized
                and "THE SOFTWARE IS PROVIDED" in normalized
                and '"AS IS"' in normalized
            )
        )
    if expected == "Apache-2.0":
        return (
            _contains_license_token(normalized, "APACHE-2.0")
            or (
                "APACHE LICENSE" in normalized
                and _contains_license_token(normalized, "2.0")
            )
        )
    if expected == "MPL-2.0":
        return (
            _contains_license_token(normalized, "MPL-2.0")
            or (
                "MOZILLA PUBLIC LICENSE" in normalized
                and _contains_license_token(normalized, "2.0")
            )
        )
    return _contains_license_token(normalized, expected)


def run_scan() -> dict[str, Any]:
    register = load_json_document(REGISTER_PATH)
    license_policy = load_json_document(LICENSE_PATH)
    sbom = load_json_document(SBOM_PATH)
    errors = list(validate_register(register, license_policy))
    errors.extend(validate_sbom(register, sbom))
    if errors:
        raise RuntimeError(foffline admission validation failed: " + ", ".join(errors))

    registry_results = []
    queries = []
    for component in register["components"]:
        metadata = registry_metadata(component)
        if str(metadata["name"]).lower() != component["name"].lower():
            raise RuntimeError(f"{component['name']}: registry name mismatch")
        if metadata["version"] != component["version"]:
            raise RuntimeError(f"{component['name']}: registry version mismatch")
        if not license_matches(component["license"], metadata["license_text"]):
            raise RuntimeError(f"{component['name']}: registry license mismatch")
        if component["ecosystem"] == "npm" and not metadata.get("integrity"):
            raise RuntimeError(f"{component['name']}: npm integrity missing")
        registry_results.append(metadata)
        queries.append({
            "package": {
                "name": component["name"],
                "ecosystem": component["ecosystem"],
            },
            "version": component["version"],
        })

    osv = request_json(OSV_BATCH_URL, payload={"queries": queries})
    results = osv.get("results")
    if not isinstance(results, list) or len(results) != len(queries):
        raise RuntimeError("OSV result cardinality mismatch")

    vulnerabilities = []
    for component, result in zip(register["components"], results, strict=True):
        if not isinstance(result, dict):
            raise RuntimeError(f"{component['name']}: malformed OSV result")
        for vulnerability in result.get("vulns", []):
            vulnerabilities.append({
                "component": component["name"],
                "version": component["version"],
                "id": vulnerability.get("id"),
                "aliases": vulnerability.get("aliases", []),
            })
    if vulnerabilities:
        raise RuntimeError("known vulnerabilities found: " + json.dumps(vulnerabilities))

    return {
        "stage": "OSS_DEPENDENCY_ADMISSION",
        "status": "PASS",
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "component_count": len(register["components"]),
        "registry_results": registry_results,
        "osv_query_count": len(queries),
        "known_vulnerability_count": 0,
        "runtime_installation_authorized": False,
        "marketplace_write_enabled": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run_scan()
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
