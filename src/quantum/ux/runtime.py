from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from quantum.reporting import ReportingError, validate_report_record

UX_SCHEMA_VERSION = "quantum-ux-view-v1"
CONFIGURATION_FORM_VERSION = "quantum-configuration-form-v1"
EXCEPTION_INBOX_VERSION = "quantum-exception-inbox-v1"

_CONFIGURATION_FIELDS = (
    "cost",
    "tax_rate",
    "tax_base",
    "other_expense",
)
_TAX_BASES = frozenset({
    "GROSS_SALES",
    "NET_SALES",
    "PAYOUT",
    "PRODUCT_COST",
    "CUSTOM_VARIABLE",
})
_TYPED_STATES = frozenset({
    "VALID",
    "EMPTY",
    "BLOCKED",
    "UNAVAILABLE",
    "CONFLICT",
    "INVALID",
    "NOT_APPLICABLE",
})
_MODES = frozenset({"ACTUAL", "SCENARIO"})
_HASH_RE = re.compile(r"^[a-f0-9]{64}$")
_DECIMAL_RE = re.compile(r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")

_FIELD_DEFINITIONS: dict[str, dict[str, Any]] = {
    "cost": {
        "label": "Product cost",
        "input_kind": "COST",
        "control": "decimal",
        "requires_currency": True,
        "accessible_name": "Product cost",
        "resolution": "Provide an explicit scoped product-cost value.",
    },
    "tax_rate": {
        "label": "Tax rate",
        "input_kind": "TAX_RATE",
        "control": "decimal",
        "requires_currency": False,
        "accessible_name": "Tax rate",
        "resolution": "Provide an explicit tax rate without a hidden default.",
    },
    "tax_base": {
        "label": "Tax base",
        "input_kind": "TAX_BASE",
        "control": "select",
        "requires_currency": False,
        "accessible_name": "Tax base",
        "resolution": "Select the explicit tax base used by the tax rule.",
    },
    "other_expense": {
        "label": "Other expense",
        "input_kind": "OTHER_EXPENSE",
        "control": "decimal",
        "requires_currency": True,
        "accessible_name": "Other expense",
        "resolution": "Provide an explicit scoped other-expense value.",
    },
}

_STATE_PRESENTATION: dict[str, tuple[str, str, str]] = {
    "EMPTY": ("No value", "empty", "No value is available."),
    "BLOCKED": ("Blocked", "blocked", "The result is blocked."),
    "UNAVAILABLE": ("Unavailable", "unavailable", "The source is unavailable."),
    "CONFLICT": ("Conflict", "conflict", "Conflicting evidence prevents publication."),
    "INVALID": ("Invalid", "invalid", "The result is invalid."),
    "NOT_APPLICABLE": ("Not applicable", "not-applicable", "The metric is not applicable."),
}


class UXError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise UXError("UX_JSON_INVALID") from exc


def _clone_json(value: Any) -> Any:
    return json.loads(_canonical_json(value))


def _canonical_hash(document: Mapping[str, Any], excluded: frozenset[str]) -> str:
    payload = {key: value for key, value in document.items() if key not in excluded}
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _is_nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _is_rfc3339(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _timestamp(value: datetime | str, code: str) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise UXError(code)
        return value.isoformat()
    if _is_rfc3339(value):
        return value
    raise UXError(code)


def _validate_scope(scope: object, organization_id: str) -> dict[str, str]:
    if not isinstance(scope, Mapping):
        raise UXError("UX_SCOPE_INVALID")
    allowed = {
        "organization_id",
        "marketplace_account_id",
        "marketplace",
        "product_id",
        "product_group_id",
        "calculation_profile_id",
        "scenario_id",
    }
    if set(scope) - allowed:
        raise UXError("UX_SCOPE_INVALID")
    if scope.get("organization_id") != organization_id:
        raise UXError("UX_SCOPE_ORGANIZATION_MISMATCH")
    if "product_id" in scope and "product_group_id" in scope:
        raise UXError("UX_SCOPE_PRODUCT_AMBIGUOUS")
    normalized: dict[str, str] = {}
    for key, value in scope.items():
        if not _is_nonempty_string(value):
            raise UXError("UX_SCOPE_INVALID")
        normalized[str(key)] = str(value)
    return normalized


def _base_form_fields() -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for field_id in _CONFIGURATION_FIELDS:
        definition = _FIELD_DEFINITIONS[field_id]
        fields.append({
            "field_id": field_id,
            "label": definition["label"],
            "input_kind": definition["input_kind"],
            "control": definition["control"],
            "required": True,
            "requires_currency": definition["requires_currency"],
            "accessible_name": definition["accessible_name"],
            "value": None,
            "state": "EMPTY",
            "diagnostic": "CONFIGURATION_REQUIRED",
        })
    return fields


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
    """Build an explicit, preview-only configuration form with no business defaults."""
    if not _is_nonempty_string(form_id):
        raise UXError("UX_FORM_ID_INVALID")
    if not _is_nonempty_string(organization_id):
        raise UXError("UX_ORGANIZATION_ID_INVALID")
    if mode not in _MODES:
        raise UXError("UX_MODE_INVALID")
    if mode == "ACTUAL" and scenario_id is not None:
        raise UXError("UX_SCENARIO_INVALID")
    if mode == "SCENARIO" and not _is_nonempty_string(scenario_id):
        raise UXError("UX_SCENARIO_INVALID")
    if not _is_nonempty_string(actor):
        raise UXError("UX_ACTOR_INVALID")
    normalized_scope = _validate_scope(scope, organization_id)
    if mode == "SCENARIO" and normalized_scope.get("scenario_id") != scenario_id:
        raise UXError("UX_SCOPE_SCENARIO_MISMATCH")
    if mode == "ACTUAL" and "scenario_id" in normalized_scope:
        raise UXError("UX_SCOPE_SCENARIO_MISMATCH")
    if currency is not None and (
        not isinstance(currency, str) or _CURRENCY_RE.fullmatch(currency) is None
    ):
        raise UXError("UX_CURRENCY_INVALID")

    normalized_valid_from = (
        None if valid_from is None else _timestamp(valid_from, "UX_VALID_FROM_INVALID")
    )
    normalized_valid_to = (
        None if valid_to is None else _timestamp(valid_to, "UX_VALID_TO_INVALID")
    )
    if normalized_valid_from is not None and normalized_valid_to is not None:
        start = datetime.fromisoformat(normalized_valid_from.replace("Z", "+00:00"))
        end = datetime.fromisoformat(normalized_valid_to.replace("Z", "+00:00"))
        if end <= start:
            raise UXError("UX_VALIDITY_INTERVAL_INVALID")

    form = {
        "schema_version": CONFIGURATION_FORM_VERSION,
        "form_id": form_id,
        "organization_id": organization_id,
        "mode": mode,
        "scenario_id": scenario_id,
        "actor": actor,
        "scope": normalized_scope,
        "valid_from": normalized_valid_from,
        "valid_to": normalized_valid_to,
        "currency": currency,
        "created_at": _timestamp(created_at, "UX_CREATED_AT_INVALID"),
        "publication_state": "PREVIEW_ONLY",
        "fields": _base_form_fields(),
        "status": "BLOCKED",
        "problems": [],
        "form_hash": "",
    }
    form["form_hash"] = _canonical_hash(form, frozenset({"form_hash"}))
    return form


def _validate_configuration_form(form: object) -> None:
    if not isinstance(form, Mapping):
        raise UXError("UX_FORM_MALFORMED")
    required = {
        "schema_version", "form_id", "organization_id", "mode", "scenario_id",
        "actor", "scope", "valid_from", "valid_to", "currency", "created_at",
        "publication_state", "fields", "status", "problems", "form_hash",
    }
    if set(form) != required:
        raise UXError("UX_FORM_MALFORMED")
    if form.get("schema_version") != CONFIGURATION_FORM_VERSION:
        raise UXError("UX_FORM_SCHEMA_INVALID")
    if form.get("publication_state") != "PREVIEW_ONLY":
        raise UXError("UX_FORM_PUBLICATION_STATE_INVALID")
    if not isinstance(form.get("fields"), list):
        raise UXError("UX_FORM_FIELDS_INVALID")
    if form.get("form_hash") != _canonical_hash(form, frozenset({"form_hash"})):
        raise UXError("UX_FORM_HASH_MISMATCH")


def apply_configuration_values(
    form: Mapping[str, Any],
    values: Mapping[str, object],
) -> dict[str, Any]:
    """Apply explicit user values without activating rules or substituting defaults."""
    _validate_configuration_form(form)
    if not isinstance(values, Mapping) or set(values) - set(_CONFIGURATION_FIELDS):
        raise UXError("UX_CONFIGURATION_VALUES_INVALID")

    updated = _clone_json(form)
    problems: list[dict[str, str]] = []
    valid_count = 0

    if updated["valid_from"] is None:
        problems.append({
            "code": "VALID_FROM_REQUIRED",
            "field_id": "valid_from",
            "message": "An explicit validity start is required.",
        })

    for field in updated["fields"]:
        field_id = field["field_id"]
        raw = values.get(field_id)
        if raw is None or raw == "":
            field["value"] = None
            field["state"] = "EMPTY"
            field["diagnostic"] = "CONFIGURATION_REQUIRED"
            continue

        if field_id == "tax_base":
            if not isinstance(raw, str) or raw not in _TAX_BASES:
                field["value"] = None
                field["state"] = "INVALID"
                field["diagnostic"] = "TAX_BASE_INVALID"
                problems.append({
                    "code": "TAX_BASE_INVALID",
                    "field_id": field_id,
                    "message": "Tax base must use the approved closed vocabulary.",
                })
                continue
        elif not isinstance(raw, str) or _DECIMAL_RE.fullmatch(raw) is None:
            field["value"] = None
            field["state"] = "INVALID"
            field["diagnostic"] = "DECIMAL_INPUT_INVALID"
            problems.append({
                "code": "DECIMAL_INPUT_INVALID",
                "field_id": field_id,
                "message": "Value must be an explicit normalized decimal string.",
            })
            continue

        if field["requires_currency"] and updated["currency"] is None:
            field["value"] = None
            field["state"] = "BLOCKED"
            field["diagnostic"] = "CURRENCY_REQUIRED"
            problems.append({
                "code": "CURRENCY_REQUIRED",
                "field_id": field_id,
                "message": "Currency is required for monetary configuration.",
            })
            continue

        field["value"] = raw
        field["state"] = "VALID"
        field["diagnostic"] = None
        valid_count += 1

    empty_count = sum(field["state"] == "EMPTY" for field in updated["fields"])
    invalid_count = sum(
        field["state"] in {"INVALID", "BLOCKED"} for field in updated["fields"]
    )
    if problems or invalid_count:
        status = "BLOCKED"
    elif valid_count == len(_CONFIGURATION_FIELDS):
        status = "READY_FOR_RULE_DRAFT"
    elif valid_count and empty_count:
        status = "PARTIAL"
    else:
        status = "BLOCKED"

    updated["status"] = status
    updated["problems"] = problems
    updated["form_hash"] = _canonical_hash(updated, frozenset({"form_hash"}))
    return updated


def render_report_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return a text-first accessible presentation model for one B4 report record."""
    try:
        validate_report_record(record)
    except ReportingError as exc:
        raise UXError(f"UX_REPORT_INVALID:{exc.code}") from exc

    state = record["state"]
    if state not in _TYPED_STATES:
        raise UXError("UX_TYPED_STATE_INVALID")

    is_numeric_zero = state == "VALID" and record["value"] == "0"
    if state == "VALID":
        value_text = str(record["value"])
        if is_numeric_zero:
            status_label = "Valid numeric zero"
            status_token = "valid-zero"
            accessible_summary = "Valid result with numeric value zero."
        else:
            status_label = "Valid"
            status_token = "valid"
            accessible_summary = f"Valid result: {value_text}."
    else:
        status_label, status_token, accessible_summary = _STATE_PRESENTATION[state]
        value_text = "—"

    view = {
        "schema_version": UX_SCHEMA_VERSION,
        "view_type": "METRIC_RESULT",
        "view_id": f"ux:{record['report_record_id']}",
        "organization_id": record["organization_id"],
        "mode": record["mode"],
        "scenario_id": record["scenario_id"],
        "metric_snapshot_id": record["metric_snapshot_id"],
        "state": state,
        "status_label": status_label,
        "status_token": status_token,
        "semantic_role": "status",
        "accessible_summary": accessible_summary,
        "value_text": value_text,
        "is_numeric_zero": is_numeric_zero,
        "reason_code": record["reason_code"],
        "publication_state": record["publication_state"],
        "evidence_available": record["evidence_chain_content_hash"] is not None,
        "limitations": list(record["limitations"]),
        "view_hash": "",
    }
    view["view_hash"] = _canonical_hash(view, frozenset({"view_hash"}))
    return view


def build_report_drilldown(record: Mapping[str, Any]) -> dict[str, Any]:
    try:
        validate_report_record(record)
    except ReportingError as exc:
        raise UXError(f"UX_REPORT_INVALID:{exc.code}") from exc

    verified = record["publication_state"] == "EVIDENCE_VERIFIED"
    drilldown = {
        "schema_version": UX_SCHEMA_VERSION,
        "view_type": "EVIDENCE_DRILLDOWN",
        "view_id": f"ux:evidence:{record['report_record_id']}",
        "organization_id": record["organization_id"],
        "mode": record["mode"],
        "scenario_id": record["scenario_id"],
        "metric_snapshot_id": record["metric_snapshot_id"],
        "metric_content_hash": record["metric_content_hash"],
        "evidence_chain_ref": _clone_json(record["evidence_chain_ref"]),
        "evidence_chain_content_hash": record["evidence_chain_content_hash"],
        "verification_status": "VERIFIED" if verified else "PREVIEW_ONLY",
        "can_claim_verified_evidence": verified,
        "limitations": list(record["limitations"]),
        "view_hash": "",
    }
    drilldown["view_hash"] = _canonical_hash(drilldown, frozenset({"view_hash"}))
    return drilldown


def _exception_id(*parts: str) -> str:
    payload = "\x1f".join(parts).encode("utf-8")
    return "exc-" + hashlib.sha256(payload).hexdigest()[:24]


def _ensure_same_context(
    organization_id: str | None,
    mode: str | None,
    scenario_id: str | None,
    *,
    candidate_organization_id: str,
    candidate_mode: str,
    candidate_scenario_id: str | None,
) -> tuple[str, str, str | None]:
    if organization_id is None:
        return candidate_organization_id, candidate_mode, candidate_scenario_id
    if organization_id != candidate_organization_id:
        raise UXError("UX_INBOX_TENANT_MIXED")
    if mode != candidate_mode or scenario_id != candidate_scenario_id:
        raise UXError("UX_INBOX_MODE_MIXED")
    return organization_id, mode, scenario_id


def build_exception_inbox(
    records: Sequence[Mapping[str, Any]],
    *,
    configuration_forms: Sequence[Mapping[str, Any]] = (),
    generated_at: datetime | str,
) -> dict[str, Any]:
    """Build an immutable exception view while retaining independent valid metrics."""
    organization_id: str | None = None
    mode: str | None = None
    scenario_id: str | None = None
    exceptions: list[dict[str, Any]] = []
    available_metric_ids: list[str] = []
    seen_records: set[str] = set()

    for record in records:
        try:
            validate_report_record(record)
        except ReportingError as exc:
            raise UXError(f"UX_REPORT_INVALID:{exc.code}") from exc
        record_id = str(record["report_record_id"])
        if record_id in seen_records:
            raise UXError("UX_INBOX_RECORD_DUPLICATE")
        seen_records.add(record_id)
        organization_id, mode, scenario_id = _ensure_same_context(
            organization_id,
            mode,
            scenario_id,
            candidate_organization_id=str(record["organization_id"]),
            candidate_mode=str(record["mode"]),
            candidate_scenario_id=record["scenario_id"],
        )
        if record["state"] == "VALID":
            available_metric_ids.append(str(record["metric_snapshot_id"]))
            continue
        if record["state"] == "NOT_APPLICABLE":
            continue
        reason = record["reason_code"] or f"STATE_{record['state']}"
        evidence_ref = record["evidence_chain_ref"]
        exceptions.append({
            "exception_id": _exception_id("metric", record_id, str(reason)),
            "category": "METRIC",
            "state": record["state"],
            "cause": reason,
            "affected_metric_ids": [record["metric_snapshot_id"]],
            "evidence_refs": [_clone_json(evidence_ref)],
            "required_resolution": "Resolve the recorded cause and recalculate without replacing missing values with zero.",
            "severity": "ERROR" if record["state"] in {"BLOCKED", "CONFLICT", "INVALID"} else "WARNING",
            "status": "OPEN",
            "accessible_summary": f"{record['state']} metric {record['metric_snapshot_id']}: {reason}.",
        })

    for form in configuration_forms:
        _validate_configuration_form(form)
        organization_id, mode, scenario_id = _ensure_same_context(
            organization_id,
            mode,
            scenario_id,
            candidate_organization_id=str(form["organization_id"]),
            candidate_mode=str(form["mode"]),
            candidate_scenario_id=form["scenario_id"],
        )
        for field in form["fields"]:
            if field["state"] == "VALID":
                continue
            definition = _FIELD_DEFINITIONS[field["field_id"]]
            cause = field["diagnostic"] or "CONFIGURATION_REQUIRED"
            exceptions.append({
                "exception_id": _exception_id(
                    "configuration", str(form["form_id"]), field["field_id"], cause
                ),
                "category": "CONFIGURATION",
                "state": field["state"],
                "cause": cause,
                "affected_metric_ids": [],
                "evidence_refs": [],
                "required_resolution": definition["resolution"],
                "severity": "ERROR" if field["state"] in {"BLOCKED", "INVALID"} else "WARNING",
                "status": "OPEN",
                "accessible_summary": f"Configuration {field['label']}: {cause}.",
            })
        if form["valid_from"] is None:
            exceptions.append({
                "exception_id": _exception_id(
                    "configuration", str(form["form_id"]), "valid_from", "VALID_FROM_REQUIRED"
                ),
                "category": "CONFIGURATION",
                "state": "EMPTY",
                "cause": "VALID_FROM_REQUIRED",
                "affected_metric_ids": [],
                "evidence_refs": [],
                "required_resolution": "Provide an explicit validity start.",
                "severity": "ERROR",
                "status": "OPEN",
                "accessible_summary": "Configuration validity start is required.",
            })

    if organization_id is None or mode is None:
        raise UXError("UX_INBOX_CONTEXT_EMPTY")

    exceptions.sort(key=lambda item: item["exception_id"])
    available_metric_ids.sort()
    inbox = {
        "schema_version": EXCEPTION_INBOX_VERSION,
        "organization_id": organization_id,
        "mode": mode,
        "scenario_id": scenario_id,
        "generated_at": _timestamp(generated_at, "UX_INBOX_TIMESTAMP_INVALID"),
        "exceptions": exceptions,
        "available_metric_ids": available_metric_ids,
        "independent_results_preserved": bool(available_metric_ids),
        "exception_count": len(exceptions),
        "inbox_hash": "",
    }
    inbox["inbox_hash"] = _canonical_hash(inbox, frozenset({"inbox_hash"}))
    return inbox


def validate_ux_hash(document: Mapping[str, Any], hash_field: str) -> None:
    value = document.get(hash_field)
    if not isinstance(value, str) or _HASH_RE.fullmatch(value) is None:
        raise UXError("UX_HASH_INVALID")
    if value != _canonical_hash(document, frozenset({hash_field})):
        raise UXError("UX_HASH_MISMATCH")
