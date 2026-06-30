from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from quantum.ingestion import RawFileRecord

from . import runtime as _runtime
from .runtime import (
    CONFIGURATION_FORM_VERSION,
    EXCEPTION_INBOX_VERSION,
    UX_SCHEMA_VERSION,
    UXError,
    build_configuration_form,
    build_report_drilldown,
    render_report_record,
    validate_ux_hash,
)
from .validation import (
    UXBoundaryError,
    validate_configuration_form_boundary,
    validate_import_collection_boundary,
    validate_raw_file_record_boundary,
)


def _translate_boundary_error(exc: UXBoundaryError) -> UXError:
    return UXError(exc.code)


def apply_configuration_values(
    form: Mapping[str, Any],
    values: Mapping[str, object],
) -> dict[str, Any]:
    try:
        validate_configuration_form_boundary(form)
    except UXBoundaryError as exc:
        raise _translate_boundary_error(exc) from exc
    return _runtime.apply_configuration_values(form, values)


def render_import_status(record: RawFileRecord) -> dict[str, Any]:
    try:
        validate_raw_file_record_boundary(record)
    except UXBoundaryError as exc:
        raise _translate_boundary_error(exc) from exc
    return _runtime.render_import_status(record)


def build_exception_inbox(
    records: Sequence[Mapping[str, Any]],
    *,
    configuration_forms: Sequence[Mapping[str, Any]] = (),
    import_records: Sequence[RawFileRecord] = (),
    tenant_id: str | None = None,
    generated_at: datetime | str,
) -> dict[str, Any]:
    try:
        for form in configuration_forms:
            validate_configuration_form_boundary(form)
        validate_import_collection_boundary(import_records, tenant_id)
    except UXBoundaryError as exc:
        raise _translate_boundary_error(exc) from exc
    return _runtime.build_exception_inbox(
        records,
        configuration_forms=configuration_forms,
        import_records=import_records,
        tenant_id=tenant_id,
        generated_at=generated_at,
    )


__all__ = [
    "CONFIGURATION_FORM_VERSION",
    "EXCEPTION_INBOX_VERSION",
    "UX_SCHEMA_VERSION",
    "UXError",
    "apply_configuration_values",
    "build_configuration_form",
    "build_exception_inbox",
    "build_report_drilldown",
    "render_import_status",
    "render_report_record",
    "validate_ux_hash",
]
