"""OSS dependency admission contracts and validators."""

import re
from typing import Any

from . import admission as _admission

_ORIGINAL_VALIDATE_REGISTER = getattr(
    _admission,
    "_quantum_original_validate_register",
    _admission.validate_register,
)
_admission._quantum_original_validate_register = _ORIGINAL_VALIDATE_REGISTER

_DEV_TEST_USE_PREFIX = re.compile(
    r"^(?:development|dev|test|tests|testing|ci|regression)(?:\b|_)",
    re.IGNORECASE,
)
_PRODUCTION_USE_TOKEN = re.compile(
    r"(?<![A-Za-z0-9])(?:production|runtime|prod|live|operational|operations?|deploy(?:ment|ments|ed|ing)?|customer-facing|user-facing)(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_MPL_MANDATORY_CONDITIONS = {
    "development_or_test_scope_only",
    "no_vendored_modified_source_without_legal_review",
    "license_and_notice_retained",
}


def _append_unique(errors: list[str], error: str) -> None:
    if error not in errors:
        errors.append(error)


def _validate_dev_test_allowed_uses(
    component: dict[str, Any],
    name: str,
    errors: list[str],
) -> None:
    allowed_use = component.get("allowed_use")
    if not isinstance(allowed_use, list) or not allowed_use:
        return
    for value in allowed_use:
        if not isinstance(value, str) or not value.strip():
            continue
        if (
            _DEV_TEST_USE_PREFIX.search(value.strip()) is None
            or _PRODUCTION_USE_TOKEN.search(value) is not None
        ):
            _append_unique(
                errors,
                f"{name}:DEV_TEST_ALLOWED_USE_NOT_EXCLUSIVE",
            )
            return


def _validate_mpl_policy(
    license_policy: dict[str, Any],
    errors: list[str],
) -> None:
    rules = license_policy.get("conditional_licenses")
    mpl_conditions: set[str] = set()
    if isinstance(rules, list):
        for item in rules:
            if isinstance(item, dict) and item.get("license") == "MPL-2.0":
                conditions = item.get("conditions")
                if isinstance(conditions, list):
                    mpl_conditions = {
                        value for value in conditions
                        if isinstance(value, str)
                    }
                break
    if not _MPL_MANDATORY_CONDITIONS.issubset(mpl_conditions):
        _append_unique(errors, "MPL-2.0:MANDATORY_CONDITIONS_MISSING")


def validate_register(
    register: dict[str, Any],
    license_policy: dict[str, Any],
) -> tuple[str, ...]:
    """Apply core validation plus admission-level fail-closed invariants."""
    errors = list(_ORIGINAL_VALIDATE_REGISTER(register, license_policy))
    _validate_mpl_policy(license_policy, errors)

    components = register.get("components")
    if isinstance(components, list):
        for component in components:
            if not isinstance(component, dict):
                continue
            if component.get("status") != "APPROVED_DEV_TEST_ONLY":
                continue
            name = component.get("name")
            if not isinstance(name, str) or not name:
                continue
            status_errors: list[str] = []
            _admission._validate_dev_test_scope(component, name, status_errors)
            for error in status_errors:
                _append_unique(errors, error)
            _validate_dev_test_allowed_uses(component, name, errors)
    return tuple(errors)


_admission.validate_register = validate_register
load_json_document = _admission.load_json_document
validate_sbom = _admission.validate_sbom

__all__ = ["load_json_document", "validate_register", "validate_sbom"]
