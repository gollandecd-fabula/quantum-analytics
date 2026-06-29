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
SUPPORTED_CONDITIONAL_LICENSE_CONDITIONS = {
    "development_or_test_scope_only",
    "no_vendored_modified_source_without_legal_review",
    "license_and_notice_retained",
}


def load_json_document(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: top-level object required")
    return value


def _policy_string_set(
    license_policy: dict[str, Any],
    field: str,
    errors: list[str],
    *,
    invalid_code: str,
    duplicate_code: str,
) -> set[str]:
    raw_values = license_policy.get(field, [])
    if not isinstance(raw_values, list):
        errors.append(invalid_code)
        return set()

    result: set[str] = set()
    for value in raw_values:
        if not isinstance(value, str) or not value:
            errors.append(invalid_code)
            continue
        if value in result:
            errors.append(f"{value}:{duplicate_code}")
            continue
        result.add(value)
    return result


def _conditional_license_rules(
    license_policy: dict[str, Any],
    errors: list[str],
) -> dict[str, frozenset[str]]:
    raw_rules = license_policy.get("conditional_licenses", [])
    if not isinstance(raw_rules, list):
        errors.append("CONDITIONAL_LICENSES_INVALID")
        return {}

    result: dict[str, frozenset[str]] = {}
    for item in raw_rules:
        if not isinstance(item, dict):
            errors.append("CONDITIONAL_LICENSE_OBJECT_REQUIRED")
            continue
        license_id = item.get("license")
        if not isinstance(license_id, str) or not license_id:
            errors.append("CONDITIONAL_LICENSE_ID_INVALID")
            continue
        if license_id in result:
            errors.append(f"{license_id}:CONDITIONAL_LICENSE_DUPLICATE")
            continue
        conditions = item.get("conditions")
        if (
            not isinstance(conditions, list)
            or not conditions
            or any(not isinstance(value, str) or not value for value in conditions)
        ):
            errors.append(f"{license_id}:LICENSE_CONDITIONS_INVALID")
            continue
        condition_set = frozenset(conditions)
        if len(condition_set) != len(conditions):
            errors.append(f"{license_id}:LICENSE_CONDITION_DUPLICATE")
            continue
        unsupported = condition_set - SUPPORTED_CONDITIONAL_LICENSE_CONDITIONS
        if unsupported:
            errors.append(f"{license_id}:LICENSE_CONDITION_UNSUPPORTED")
            continue
        result[license_id] = condition_set
    return result


def validate_register(register: dict[str, Any], license_policy: dict[str, Any]) -> tuple[str, ...]:
    errors: list[str] = []
    if register.get("stage") != "OSS_DEPENDENCY_ADMISSION":
        errors.append("ADMISSION_STAGE_INVALID")
    if register.get("runtime_installation_authorized") is not False:
        errors.append("RUNTIME_INSTALLATION_MUST_REMAIN_BLOCKED")
    if register.get("marketplace_write_enabled") is not False:
        errors.append("MARKETPLACE_WRITES_MUST_REMAIN_BLOCKED")

    approved = _policy_string_set(
        license_policy,
        "approved_direct_licenses",
        errors,
        invalid_code="APPROVED_DIRECT_LICENSES_INVALID",
        duplicate_code="APPROVED_DIRECT_LICENSE_DUPLICATE",
    )
    conditional = _conditional_license_rules(license_policy, errors)
    prohibited = _policy_string_set(
        license_policy,
        "prohibited_direct_integration",
        errors,
        invalid_code="PROHIBITED_DIRECT_LICENSES_INVALID",
        duplicate_code="PROHIBITED_DIRECT_LICENSE_DUPLICATE",
    )
    for license_id in (
        (approved & prohibited)
        | (set(conditional) & prohibited)
        | (approved & set(conditional))
    ):
        errors.append(f"{license_id}:LICENSE_POLICY_CONFLICT")
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
        if not isinstance(name, str) or not name:
            errors.append("COMPONENT_NAME_INVALID")
            continue
        if not isinstance(ecosystem, str) or ecosystem not in ("PyPI", "npm"):
            errors.append(f"{name}:ECOSYSTEM_INVALID")
        else:
            key = (ecosystem, name)
            if key in seen:
                errors.append(f"{name}:DUPLICATE_COMPONENT")
            seen.add(key)

        version = component.get("version")
        if not isinstance(version, str) or not EXACT_VERSION.fullmatch(version):
            errors.append(f"{name}:EXACT_VERSION_REQUIRED")

        license_id = component.get("license")
        conditions: frozenset[str] | None = None
        if not isinstance(license_id, str) or not license_id:
            errors.append(f"{name}:LICENSE_ID_INVALID")
        else:
            if license_id in prohibited or license_id not in approved | set(conditional):
                errors.append(f"{name}:LICENSE_NOT_ADMITTED")
            conditions = conditional.get(license_id)

        status = component.get("status")
        if not isinstance(status, str) or status not in ALLOWED_STATUSES:
            errors.append(f"{name}:STATUS_INVALID")

        if conditions is not None:
            if (
                "development_or_test_scope_only" in conditions
                and status != "APPROVED_DEV_TEST_ONLY"
            ):
                errors.append(f"{name}:CONDITIONAL_LICENSE_SCOPE_VIOLATION")
            if "no_vendored_modified_source_without_legal_review" in conditions:
                prohibited_use = component.get("prohibited_use")
                if (
                    not isinstance(prohibited_use, list)
                    or "vendoring modified source without review" not in prohibited_use
                ):
                    errors.append(f"{name}:CONDITIONAL_LICENSE_VENDORING_GUARD_REQUIRED")
            if "license_and_notice_retained" in conditions:
                policy_rules = license_policy.get("rules")
                if (
                    not isinstance(policy_rules, dict)
                    or policy_rules.get("license_notice_required") is not True
                ):
                    errors.append(f"{name}:CONDITIONAL_LICENSE_NOTICE_POLICY_REQUIRED")

        if component.get("installation_authorized") is not False:
            errors.append(f"{name}:INSTALLATION_NOT_AUTHORIZED")

        if component.get("transitive_dependency_review_required") is not True:
            errors.append(f"{name}:TRANSITIVE_REVIEW_REQUIRED")

        source_url = component.get("source_url")
        if not isinstance(source_url, str) or not source_url.startswith("https://"):
            errors.append(f"{name}:HTTPS_SOURCE_REQUIRED")

    by_name = {
        item.get("name"): item
        for item in components
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
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
    if (
        not isinstance(prohibited_use, list)
        or any(not isinstance(value, str) or not value for value in prohibited_use)
        or not required_blocks.issubset(set(prohibited_use))
    ):
        errors.append("WBSDK_WRITE_DENYLIST_INCOMPLETE")

    return tuple(errors)


def validate_sbom(register: dict[str, Any], sbom: dict[str, Any]) -> tuple[str, ...]:
    errors: list[str] = []
    if sbom.get("spdxVersion") != "SPDX-2.3":
        errors.append("SBOM_SPDX_VERSION_INVALID")
    packages = sbom.get("packages")
    if not isinstance(packages, list):
        return tuple(errors + ["SBOM_PACKAGES_REQUIRED"])

    actual: dict[str, tuple[Any, Any, Any]] = {}
    package_ids: set[str] = set()
    for package in packages:
        if not isinstance(package, dict):
            errors.append("SBOM_PACKAGE_OBJECT_REQUIRED")
            continue

        name = package.get("name")
        if not isinstance(name, str) or not name:
            errors.append("SBOM_PACKAGE_NAME_INVALID")
        elif name in actual:
            errors.append(f"{name}:SBOM_DUPLICATE_PACKAGE")
        else:
            actual[name] = (
                package.get("versionInfo"),
                package.get("licenseDeclared"),
                package.get("filesAnalyzed"),
            )

        spdx_id = package.get("SPDXID")
        if not isinstance(spdx_id, str) or not spdx_id:
            errors.append("SBOM_SPDXID_INVALID")
        elif spdx_id in package_ids:
            errors.append(f"{spdx_id}:SBOM_DUPLICATE_SPDXID")
        else:
            package_ids.add(spdx_id)

    expected: dict[str, tuple[Any, Any, bool]] = {}
    register_components = register.get("components")
    if not isinstance(register_components, list):
        errors.append("SBOM_REGISTER_COMPONENTS_INVALID")
        register_components = []
    for item in register_components:
        if not isinstance(item, dict):
            errors.append("SBOM_REGISTER_COMPONENT_INVALID")
            continue
        item_name = item.get("name")
        if not isinstance(item_name, str) or not item_name:
            errors.append("SBOM_REGISTER_COMPONENT_NAME_INVALID")
            continue
        expected[item_name] = (item.get("version"), item.get("license"), False)
    if actual != expected:
        errors.append("SBOM_REGISTER_MISMATCH")

    document_describes = sbom.get("documentDescribes")
    if not isinstance(document_describes, list):
        errors.append("SBOM_DOCUMENT_DESCRIBES_REQUIRED")
    else:
        valid_described = [
            item for item in document_describes
            if isinstance(item, str) and item
        ]
        if len(valid_described) != len(document_describes):
            errors.append("SBOM_DOCUMENT_DESCRIBES_INVALID")
        if len(set(valid_described)) != len(valid_described):
            errors.append("SBOM_DOCUMENT_DESCRIBES_DUPLICATE")
        if set(valid_described) != package_ids:
            errors.append("SBOM_DOCUMENT_DESCRIBES_MISMATCH")
    return tuple(errors)
