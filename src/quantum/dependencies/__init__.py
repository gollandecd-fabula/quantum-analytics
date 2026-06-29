"""OSS dependency admission contracts and validators."""

from typing import Any

from . import admission as _admission

_ORIGINAL_VALIDATE_REGISTER = getattr(
    _admission,
    "_quantum_original_validate_register",
    _admission.validate_register,
)
_admission._quantum_original_validate_register = _ORIGINAL_VALIDATE_REGISTER


def validate_register(
    register: dict[str, Any],
    license_policy: dict[str, Any],
) -> tuple[str, ...]:
    """Apply core validation plus status-level dev/test invariants."""
    errors = list(_ORIGINAL_VALIDATE_REGISTER(register, license_policy))
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
                if error not in errors:
                    errors.append(error)
    return tuple(errors)


_admission.validate_register = validate_register
load_json_document = _admission.load_json_document
validate_sbom = _admission.validate_sbom

__all__ = ["load_json_document", "validate_register", "validate_sbom"]
