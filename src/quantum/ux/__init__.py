from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from quantum.ingestion import RawFileRecord

from . import runtime as _runtime
from .runtime import (
    CONFIGURATION_FORM_VERSION,
    EXCEPTION_INBOX_VERSION,
    UX_SCHEMA_VERSION,
    UXError,
    build_report_drilldown,
    validate_ux_hash,
)
from .validation import (
    UXBoundaryError,
    is_strict_rfc3339,
    validate_configuration_form_boundary,
    validate_import_collection_boundary,
    validate_raw_file_record_boundary,
)


def _translate_boundary_error(exc: UXBoundaryError) -> UXError:
    return UXError(exc.code)


def _is_numeric_zero(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value == 0
    if isinstance(value, str):
        try:
            return Decimal(value).is_zero()
        except InvalidOperation:
            return False
    return False


def _rehash_view(view: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in view.items() if key != "view_hash"}
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_timestamp_input(
    value: datetime | str | None,
    code: str,
    *,
    allow_none: bool,
) -> None:
    if value is None:
        if allow_none:
            return
        raise UXError(code)
    rendered = value.isoformat() if isinstance(value, datetime) else value
    if not is_strict_rfc3339(rendered):
        raise UXError(code)


def build_configuration_form(
    *,
    form_id: str,
    organization_id: str,
    mode: str,
    scenario_id: str | None,
    actor: str,
    scope: Mapping[str, str],
    valid_from: datetime | str | None,
    valid_to: datetime | str | None,
    currency: str | None,
    created_at: datetime | str,
) -> dict[str, Any]:
    _validate_timestamp_input(
        valid_from,
        "UX_VALID_FROM_INVALID",
        allow_none=True,
    )
    _validate_timestamp_input(
        valid_to,
        "UX_VALID_TO_INVALID",
        allow_none=True,
    )
    _validate_timestamp_input(
        created_at,
        "UX_CREATED_AT_INVALID",
        allow_none=False,
    )
    return _runtime.build_configuration_form(
        form_id=form_id,
        organization_id=organization_id,
        mode=mode,
        scenario_id=scenario_id,
        actor=actor,
        scope=scope,
        valid_from=valid_from,
        valid_to=valid_to,
        currency=currency,
        created_at=created_at,
    )


def apply_configuration_values(
    form: Mapping[str, Any],
    values: Mapping[str, object],
) -> dict[str, Any]:
    try:
        validate_configuration_form_boundary(form)
    except UXBoundaryError as exc:
        raise _translate_boundary_error(exc) from exc
    return _runtime.apply_configuration_values(form, values)


def render_report_record(record: Mapping[str, Any]) -> dict[str, Any]:
    view = _runtime.render_report_record(record)
    if view["state"] == "VALID" and _is_numeric_zero(record.get("value")):
        view["status_label"] = "Valid numeric zero"
        view["status_token"] = "valid-zero"
        view["accessible_summary"] = "Valid result with numeric value zero."
        view["value_text"] = str(record["value"])
        view["is_numeric_zero"] = True
        view["view_hash"] = _rehash_view(view)
    return view


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
    if tenant_id is not None and (
        not isinstance(tenant_id, str) or not tenant_id
    ):
        raise UXError("UX_INBOX_TENANT_REQUIRED")
    _validate_timestamp_input(
        generated_at,
        "UX_INBOX_TIMESTAMP_INVALID",
        allow_none=False,
    )

    seen_form_ids: set[str] = set()
    try:
        for form in configuration_forms:
            validate_configuration_form_boundary(form)
            form_id = str(form["form_id"])
            if form_id in seen_form_ids:
                raise UXBoundaryError("UX_INBOX_FORM_DUPLICATE")
            seen_form_ids.add(form_id)
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
