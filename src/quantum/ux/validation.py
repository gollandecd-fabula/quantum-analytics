from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from uuid import UUID

from quantum.ingestion import RawFileRecord, RawFileState


class UXBoundaryError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


_HASH_RE = re.compile(r"^[a-f0-9]{64}$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9._-]{0,119}$")
_MODES = frozenset({"ACTUAL", "SCENARIO"})
_FORM_STATUSES = frozenset({"BLOCKED", "PARTIAL", "READY_FOR_RULE_DRAFT"})
_EXPECTED_FORM_FIELDS = ("cost", "tax_rate", "tax_base", "other_expense")


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _rfc3339(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def validate_configuration_form_boundary(form: object) -> None:
    """Validate mutable caller input before it reaches the UX runtime."""
    if not isinstance(form, Mapping):
        raise UXBoundaryError("UX_FORM_MALFORMED")
    if not _nonempty_string(form.get("form_id")):
        raise UXBoundaryError("UX_FORM_ID_INVALID")
    organization_id = form.get("organization_id")
    if not _nonempty_string(organization_id):
        raise UXBoundaryError("UX_ORGANIZATION_ID_INVALID")
    if not _nonempty_string(form.get("actor")):
        raise UXBoundaryError("UX_ACTOR_INVALID")
    mode = form.get("mode")
    scenario_id = form.get("scenario_id")
    if mode not in _MODES:
        raise UXBoundaryError("UX_MODE_INVALID")
    if mode == "ACTUAL" and scenario_id is not None:
        raise UXBoundaryError("UX_SCENARIO_INVALID")
    if mode == "SCENARIO" and not _nonempty_string(scenario_id):
        raise UXBoundaryError("UX_SCENARIO_INVALID")

    scope = form.get("scope")
    if not isinstance(scope, Mapping) or scope.get("organization_id") != organization_id:
        raise UXBoundaryError("UX_SCOPE_ORGANIZATION_MISMATCH")
    if "product_id" in scope and "product_group_id" in scope:
        raise UXBoundaryError("UX_SCOPE_PRODUCT_AMBIGUOUS")
    if any(not _nonempty_string(value) for value in scope.values()):
        raise UXBoundaryError("UX_SCOPE_INVALID")
    if mode == "ACTUAL" and "scenario_id" in scope:
        raise UXBoundaryError("UX_SCOPE_SCENARIO_MISMATCH")
    if mode == "SCENARIO" and scope.get("scenario_id") != scenario_id:
        raise UXBoundaryError("UX_SCOPE_SCENARIO_MISMATCH")

    currency = form.get("currency")
    if currency is not None and (
        not isinstance(currency, str) or _CURRENCY_RE.fullmatch(currency) is None
    ):
        raise UXBoundaryError("UX_CURRENCY_INVALID")
    created_at = form.get("created_at")
    if not _rfc3339(created_at):
        raise UXBoundaryError("UX_CREATED_AT_INVALID")
    valid_from = form.get("valid_from")
    valid_to = form.get("valid_to")
    if valid_from is not None and not _rfc3339(valid_from):
        raise UXBoundaryError("UX_VALID_FROM_INVALID")
    if valid_to is not None and not _rfc3339(valid_to):
        raise UXBoundaryError("UX_VALID_TO_INVALID")
    if valid_from is not None and valid_to is not None:
        start = datetime.fromisoformat(str(valid_from).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(valid_to).replace("Z", "+00:00"))
        if end <= start:
            raise UXBoundaryError("UX_VALIDITY_INTERVAL_INVALID")
    if form.get("status") not in _FORM_STATUSES:
        raise UXBoundaryError("UX_FORM_STATUS_INVALID")

    fields = form.get("fields")
    if not isinstance(fields, list) or len(fields) != len(_EXPECTED_FORM_FIELDS):
        raise UXBoundaryError("UX_FORM_FIELDS_INVALID")
    if tuple(field.get("field_id") for field in fields if isinstance(field, Mapping)) != _EXPECTED_FORM_FIELDS:
        raise UXBoundaryError("UX_FORM_FIELDS_INVALID")

    problems = form.get("problems")
    if not isinstance(problems, list):
        raise UXBoundaryError("UX_FORM_PROBLEMS_INVALID")
    for problem in problems:
        if (
            not isinstance(problem, Mapping)
            or set(problem) != {"code", "field_id", "message"}
            or any(not _nonempty_string(problem.get(key)) for key in problem)
        ):
            raise UXBoundaryError("UX_FORM_PROBLEMS_INVALID")


def validate_raw_file_record_boundary(record: object) -> None:
    """Reject forged or state-inconsistent ingestion records at the UX boundary."""
    if not isinstance(record, RawFileRecord):
        raise UXBoundaryError("UX_IMPORT_RECORD_INVALID")
    try:
        UUID(record.raw_file_id)
    except (TypeError, ValueError, AttributeError) as exc:
        raise UXBoundaryError("UX_IMPORT_RECORD_INVALID") from exc
    if not _nonempty_string(record.tenant_id):
        raise UXBoundaryError("UX_IMPORT_RECORD_INVALID")
    if not isinstance(record.sha256, str) or _HASH_RE.fullmatch(record.sha256) is None:
        raise UXBoundaryError("UX_IMPORT_RECORD_INVALID")
    if (
        not isinstance(record.size_bytes, int)
        or isinstance(record.size_bytes, bool)
        or record.size_bytes < 0
    ):
        raise UXBoundaryError("UX_IMPORT_RECORD_INVALID")
    if (
        not isinstance(record.sanitized_filename, str)
        or _SAFE_FILENAME_RE.fullmatch(record.sanitized_filename) is None
    ):
        raise UXBoundaryError("UX_IMPORT_RECORD_INVALID")
    expected_storage_key = f"tenants/{record.tenant_id}/raw/{record.sha256}"
    if record.storage_key != expected_storage_key:
        raise UXBoundaryError("UX_IMPORT_RECORD_INVALID")
    if not isinstance(record.state, RawFileState):
        raise UXBoundaryError("UX_IMPORT_STATE_INVALID")
    if (
        not isinstance(record.diagnostics, tuple)
        or len(record.diagnostics) != len(set(record.diagnostics))
        or any(not _nonempty_string(item) for item in record.diagnostics)
    ):
        raise UXBoundaryError("UX_IMPORT_RECORD_INVALID")

    if record.state in {RawFileState.RECEIVED, RawFileState.VALIDATING}:
        valid_payload = (
            record.schema_id is None
            and record.structural_fingerprint is None
            and record.semantic_fingerprint is None
            and not record.diagnostics
        )
    elif record.state is RawFileState.VALID:
        valid_payload = (
            _nonempty_string(record.schema_id)
            and isinstance(record.structural_fingerprint, dict)
            and isinstance(record.semantic_fingerprint, dict)
            and not record.diagnostics
        )
    elif record.state is RawFileState.QUARANTINED:
        valid_payload = (
            record.schema_id is None
            and isinstance(record.structural_fingerprint, dict)
            and record.semantic_fingerprint is None
            and bool(record.diagnostics)
        )
    else:
        valid_payload = (
            record.state is RawFileState.REJECTED
            and record.schema_id is None
            and record.structural_fingerprint is None
            and record.semantic_fingerprint is None
            and bool(record.diagnostics)
        )
    if not valid_payload:
        raise UXBoundaryError("UX_IMPORT_STATE_PAYLOAD_INVALID")


def validate_import_collection_boundary(
    records: Sequence[RawFileRecord],
    tenant_id: str | None,
) -> None:
    if not records:
        return
    if not _nonempty_string(tenant_id):
        raise UXBoundaryError("UX_INBOX_TENANT_REQUIRED")
    seen: set[str] = set()
    for record in records:
        validate_raw_file_record_boundary(record)
        if record.tenant_id != tenant_id:
            raise UXBoundaryError("UX_INBOX_TENANT_MIXED")
        if record.raw_file_id in seen:
            raise UXBoundaryError("UX_INBOX_IMPORT_DUPLICATE")
        seen.add(record.raw_file_id)
