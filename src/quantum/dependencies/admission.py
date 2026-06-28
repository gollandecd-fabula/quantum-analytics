from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

EXACT_VERSION = re.compile(r"^[0-9]+(?:\.[0-9A-Za-z-]+)+$")
ALLOWED_STATUSES = {
    "APPROVED_FOR_FUTURE_INTEGRATION",
    "APPROVED_DEV_TEST_ONLY",
    "APPROVED_PENDING_REGISTRY_CONFIRMATION",
    "AUDIT_REQUIRED",
}


def load_json_document(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: top-level object required")
    return value


def validate_register(register: dict[str, Any], license_policy: dict[str, Any]) -> tuple[str, ...]:
    errors: list[str] = []
    if register.get("stage") != "OSS_DEPENDENCY_ADMISSION":
        errors.append("ADMISSION_STAGE_INVALID")
    if register.get("runtime_installation_authorized") is not False:
        errors.append("RUNTIME_INSTALLATION_MUST_REMAIN_BLOCKED")
    if register.get("marketplace_write_enabled") is not False:
        errors.append("MARKETPLACE_WRITES_MUST_REMAIN_BLOCKED")

    approved = set(license_policy.get("approved_direct_licenses", []))
    conditional = {
        item.get("license")
        for item in license_policy.get("conditional_licenses", [])
        if isinstance(item, dict)
    }
    prohibited = set(license_policy.get("prohibited_direct_integration", []))
    seen: set[tuple[str, str]] = set()

    components = register.get("components")
    if not isinstance(components, list) or not components:
        return tuple(errors + ["COMPONENTS_REQUIRED"])

    for component in components:
        if not isinstance(component, dict):
            errors.append("COMPONENT_OBJECT_REQUIRED")
            continue
        name = component.get("name")
        ecosystem = component.get("ecosystem")
        key = (ecosystem, name)
        if not isinstance(name, str) or not name:
            errors.append("COMPONENT_NAME_INVALID")
            continue
        if ecosystem not in {"PyPI", "npm"}:
            errors.append(f"{name}:ECOSYSTEM_INVALID")
        if key in seen:
            errors.append(f"{name}:DUPLICATE_COMPONENT")
        seen.add(key)

        version = component.get("version")
        if not isinstance(version, str) or not EXACT_VERSION.fullmatch(version):
            errors.append(f"{name}:EXACT_VERSION_REQUIRED")

        license_id = component.get("license")
        if license_id in prohibited or license_id not in approved | conditional:
            errors.append(f"{name}:LICENSE_NOT_ADMITTED")

        status = component.get("status")
        if status not in ALLOWED_STATUSES:
            errors.append(f"{name}:STATUS_INVALID")

        if component.get("installation_authorized") is not False:
            errors.append(f"{name}:INSTALLATION_NOT_AUTHORIZED")

        if component.get("transitive_dependency_review_required") is not True:
            errors.append(f"{name}:TRANSITIVE_REVIEW_REQUIRED")

        source_url = component.get("source_url")
        if not isinstance(source_url, str) or not source_url.startswith("https://"):
            errors.append(f"{name}:HTTPS_SOURCE_REQUIRED")

    by_name = {item.get("name"): item for item in components if isinstance(item, dict)}
    hypothesis = by_name.get("hypothesis", {})
    if hypothesis.get("status") != "APPROVED_DEV_TEST_ONLY":
        errors.append("HYPOTHESIS_MUST_BE_DEV_TEST_ONLY")
    if hypothesis.get("license") != "MPL-2.0":
        errors.append("HYPOTHESIS_LICENSE_POLICY_MISMATCH")

    wbsdk = by_name.get("wbsdk", {})
    if wbsdk.get("status") != "AUDIT_REQUIRED":
        errors.append("WBSDK_MUST_REMAIN_AUDIT_REQUIRED")
    if wbsdk.get("read_only_facade_required") is not True:
        errors.append("WBSDK_READ_ONLY_FACADE_REQUIRED")
    if wbsdk.get("write_methods_exposed") is not True:
        errors.append("WBSDK_WRITE_CAPABILITY_MUST_BE_RECORDED")
    prohibited_use = wbsdk.get("prohibited_use", [])
    required_blocks = {
        "price writes",
        "stock writes",
        "card writes",
        "promotion writes",
        "order cancellation",
        "supply writes",
        "media writes",
        "direct use by domain services",
    }
    if not isinstance(prohibited_use, list) or not required_blocks.issubset(set(prohibited_use)):
        errors.append("WBSDK_WRITE_DENYLIST_INCOMPLETE")

    return tuple(errors)


def validate_sbom(register: dict[str, Any], sbom: dict[str, Any]) -> tuple[str, ...]:
    errors: list[str] = []
    if sbom.get("spdxVersion") != "SPDX-2.3":
        errors.append("SBOM_SPDX_VERSION_INVALID")
    packages = sbom.get("packages")
    if not isinstance(packages, list):
        return tuple(errors + ["SBOM_PACKAGES_REQUIRED"])

    actual = {}
    for package in packages:
        if not isinstance(package, dict):
            errors.append("SBOM_PACKAGE_OBJECT_REQUIRED")
            continue
        actual[package.get("name")] = (
            package.get("versionInfo"),
            package.get("licenseDeclared"),
            package.get("filesAnalyzed"),
        )
    expected = {
        item["name"]: (item["version"], item["license"], False)
        for item in register["components"]
    }
    if actual != expected:
        errors.append("SBOM_REGISTER_MISMATCH")

    described = set(sbom.get("documentDescribes", []))
    package_ids = {item.get("SPDXID") for item in packages if isinstance(item, dict)}
    if described != package_ids:
        errors.append("SBOM_DOCUMENT_DESCRIBES_MISMATCH")
    return tuple(errors)
