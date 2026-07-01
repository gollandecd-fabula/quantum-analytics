from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from typing import Any

from ._common import (
    FinanceError, RESOLVER_CONTRACT_VERSION, _CURRENCY_RE, _DECIMAL_RE,
    _HASH_RE, _ID_RE, _SCOPE_ORDER,
    _Value, canonical_hash, _clone_json, _is_nonempty_string, _is_positive_int,
    _make_nonvalid, _make_valid, _parse_rfc3339, _value_from_dict,
    _value_to_dict,
)
from ._expression import evaluate_expression
from ._expression_validation import validate_expression_ast
from ._rounding import (
    _input_decimal, _normalize_value, _propagate, _quantize,
    validate_rounding_policy,
)


def _validate_context(context: object) -> dict[str, Any]:
    if not isinstance(context, Mapping):
        raise FinanceError("RULE_CONTEXT_INVALID")
    required = {
        "organization_id", "mode", "scenario_id", "calculation_instant",
        "marketplace_account_id", "marketplace", "product_id", "product_group_id",
        "calculation_profile_id", "resolved_at", "actor",
    }
    if set(context) != required:
        raise FinanceError("RULE_CONTEXT_INVALID")
    for field in ("organization_id", "calculation_profile_id", "actor"):
        if not _is_nonempty_string(context[field]):
            raise FinanceError("RULE_CONTEXT_INVALID")
    for field in ("marketplace_account_id", "marketplace", "product_id", "product_group_id"):
        if context[field] is not None and not _is_nonempty_string(context[field]):
            raise FinanceError("RULE_CONTEXT_INVALID")
    mode = context["mode"]
    scenario_id = context["scenario_id"]
    if mode == "ACTUAL":
        if scenario_id is not None:
            raise FinanceError("PROFILE_MODE_CONTAMINATION")
    elif mode == "SCENARIO":
        if not _is_nonempty_string(scenario_id):
            raise FinanceError("PROFILE_MODE_CONTAMINATION")
    else:
        raise FinanceError("RULE_CONTEXT_INVALID")
    _parse_rfc3339(context["calculation_instant"], "RULE_CONTEXT_INVALID")
    _parse_rfc3339(context["resolved_at"], "RULE_CONTEXT_INVALID")
    return _clone_json(context)


def _rule_ref(rule: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "rule_id": rule["rule_id"],
        "version": rule["version"],
        "content_hash": rule["content_hash"],
    }


def _expected_rule_signature(rule: Mapping[str, Any]) -> tuple[str, str, str | None]:
    unit = str(rule["unit"])
    if unit.startswith("MONEY"):
        return "MONEY", unit, str(rule["currency"])
    if unit == "RATE":
        return "RATE", "RATE", None
    return "DECIMAL", unit, None


def _validate_rule_document(rule: object) -> dict[str, Any]:
    if not isinstance(rule, Mapping):
        raise FinanceError("RULE_DOCUMENT_INVALID")
    required = {
        "rule_id", "version", "content_hash", "rule_type", "scope", "method",
        "base", "unit", "currency", "dependencies", "valid_from", "valid_to",
        "priority", "exclusivity_group", "status", "source", "actor",
        "created_at", "change_reason", "approval_reference", "supersedes",
    }
    allowed = required | {"value", "rate", "expression"}
    if not required.issubset(rule) or set(rule) - allowed:
        raise FinanceError("RULE_DOCUMENT_INVALID")
    if not isinstance(rule["rule_id"], str) or _ID_RE.fullmatch(rule["rule_id"]) is None:
        raise FinanceError("RULE_DOCUMENT_INVALID")
    if not _is_positive_int(rule["version"]):
        raise FinanceError("RULE_DOCUMENT_INVALID")
    if not isinstance(rule["content_hash"], str) or _HASH_RE.fullmatch(rule["content_hash"]) is None:
        raise FinanceError("RULE_HASH_MISMATCH")
    if canonical_hash(rule, exclude=frozenset({"content_hash"})) != rule["content_hash"]:
        raise FinanceError("RULE_HASH_MISMATCH")
    if rule["status"] not in {"DRAFT", "SHADOW", "PILOT", "ACTIVE", "SUSPENDED", "RETIRED"}:
        raise FinanceError("RULE_DOCUMENT_INVALID")
    if rule["rule_type"] not in {"COST", "TAX", "OTHER_EXPENSE", "ALLOCATION"}:
        raise FinanceError("RULE_DOCUMENT_INVALID")
    method = rule["method"]
    if method not in {"FIXED_VALUE", "RATE", "SAFE_EXPRESSION"}:
        raise FinanceError("RULE_DOCUMENT_INVALID")
    present_payloads = [field for field in ("value", "rate", "expression") if field in rule]
    expected_payload = {
        "FIXED_VALUE": "value",
        "RATE": "rate",
        "SAFE_EXPRESSION": "expression",
    }[method]
    if present_payloads != [expected_payload]:
        raise FinanceError("RULE_METHOD_PAYLOAD_MISMATCH")
    if not isinstance(rule["priority"], int) or isinstance(rule["priority"], bool):
        raise FinanceError("RULE_DOCUMENT_INVALID")
    if not -100000 <= rule["priority"] <= 100000:
        raise FinanceError("RULE_DOCUMENT_INVALID")
    valid_from = _parse_rfc3339(rule["valid_from"], "RULE_VALIDITY_INVALID")
    if rule["valid_to"] is not None:
        valid_to = _parse_rfc3339(rule["valid_to"], "RULE_VALIDITY_INVALID")
        if valid_to <= valid_from:
            raise FinanceError("RULE_VALIDITY_INVALID")
    _parse_rfc3339(rule["created_at"], "RULE_DOCUMENT_INVALID")
    for field in ("source", "actor", "change_reason"):
        if not _is_nonempty_string(rule[field]):
            raise FinanceError("RULE_DOCUMENT_INVALID")
    if rule["approval_reference"] is not None and not _is_nonempty_string(
        rule["approval_reference"]
    ):
        raise FinanceError("RULE_DOCUMENT_INVALID")
    supersedes = rule["supersedes"]
    if supersedes is not None and (
        not isinstance(supersedes, Mapping)
        or set(supersedes) != {"rule_id", "version"}
        or not _is_nonempty_string(supersedes["rule_id"])
        or not _is_positive_int(supersedes["version"])
    ):
        raise FinanceError("RULE_DOCUMENT_INVALID")
    scope = rule["scope"]
    allowed_scope = {"organization_id", *_SCOPE_ORDER}
    if (
        not isinstance(scope, Mapping)
        or set(scope) - allowed_scope
        or not _is_nonempty_string(scope.get("organization_id"))
    ):
        raise FinanceError("RULE_SCOPE_INVALID")
    for field in _SCOPE_ORDER:
        if field in scope and not _is_nonempty_string(scope[field]):
            raise FinanceError("RULE_SCOPE_INVALID")
    if "product_id" in scope and "product_group_id" in scope:
        raise FinanceError("RULE_SCOPE_INVALID")
    unit = rule["unit"]
    currency = rule["currency"]
    monetary_units = {
        "MONEY", "MONEY_PER_ITEM", "MONEY_PER_ORDER",
        "MONEY_PER_EVENT", "MONEY_PER_PERIOD",
    }
    if unit in monetary_units:
        if not isinstance(currency, str) or _CURRENCY_RE.fullmatch(currency) is None:
            raise FinanceError("RULE_CURRENCY_UNIT_MISMATCH")
    elif unit in {"RATE", "DIMENSIONLESS"}:
        if currency is not None:
            raise FinanceError("RULE_CURRENCY_UNIT_MISMATCH")
    else:
        raise FinanceError("RULE_CURRENCY_UNIT_MISMATCH")
    dependencies = rule["dependencies"]
    if (
        not isinstance(dependencies, list)
        or len(dependencies) > 128
        or len(dependencies) != len(set(dependencies))
        or any(
            not isinstance(item, str)
            or re.fullmatch(r"^[a-z][a-z0-9_.:-]{0,127}$", item) is None
            for item in dependencies
        )
    ):
        raise FinanceError("RULE_DEPENDENCY_UNKNOWN")
    if method == "RATE":
        if rule["unit"] != "RATE" or rule["currency"] is not None or rule["base"] == "NONE":
            raise FinanceError("RULE_CURRENCY_UNIT_MISMATCH")
        if len(dependencies) != 1:
            raise FinanceError("RULE_DEPENDENCY_UNKNOWN")
        if not isinstance(rule["rate"], str) or _DECIMAL_RE.fullmatch(rule["rate"]) is None:
            raise FinanceError("RULE_RATE_INVALID")
    elif method == "FIXED_VALUE":
        if not isinstance(rule["value"], str) or _DECIMAL_RE.fullmatch(rule["value"]) is None:
            raise FinanceError("RULE_VALUE_INVALID")
    else:
        if not isinstance(rule["expression"], Mapping):
            raise FinanceError("RULE_UNSAFE_EXPRESSION")
        validate_expression_ast(rule["expression"], dependencies)
    if rule["base"] not in {
        "NONE", "UNIT", "ORDER", "EVENT", "PERIOD", "GROSS_SALES", "NET_SALES",
        "PAYOUT", "PRODUCT_COST", "CUSTOM_VARIABLE",
    }:
        raise FinanceError("RULE_DEPENDENCY_UNKNOWN")
    if rule["base"] == "CUSTOM_VARIABLE" and not dependencies:
        raise FinanceError("RULE_DEPENDENCY_UNKNOWN")
    if rule["exclusivity_group"] is not None and not _is_nonempty_string(
        rule["exclusivity_group"]
    ):
        raise FinanceError("RULE_DOCUMENT_INVALID")
    return _clone_json(rule)


def resolve_rule(rules: Sequence[Mapping[str, Any]], context: Mapping[str, Any]) -> dict[str, Any]:
    normalized_context = _validate_context(context)
    if not isinstance(rules, Sequence) or isinstance(rules, (str, bytes)):
        raise FinanceError("RULE_DOCUMENT_INVALID")
    normalized_rules = sorted(
        (_validate_rule_document(rule) for rule in rules),
        key=lambda item: (item["rule_id"], item["version"], item["content_hash"]),
    )
    instant = _parse_rfc3339(normalized_context["calculation_instant"], "RULE_CONTEXT_INVALID")
    candidates: list[dict[str, Any]] = []
    eligible_rows: list[tuple[tuple[Any, ...], int]] = []

    for index, rule in enumerate(normalized_rules):
        exclusions: list[str] = []
        scope = rule["scope"]
        if scope["organization_id"] != normalized_context["organization_id"]:
            exclusions.append("ORGANIZATION_MISMATCH")
        if rule["status"] not in {"SHADOW", "PILOT", "ACTIVE"}:
            exclusions.append("RULE_NOT_APPROVED")
        valid_from = _parse_rfc3339(rule["valid_from"], "RULE_VALIDITY_INVALID")
        valid_to = (
            _parse_rfc3339(rule["valid_to"], "RULE_VALIDITY_INVALID")
            if rule["valid_to"] is not None
            else None
        )
        if instant < valid_from or (valid_to is not None and instant >= valid_to):
            exclusions.append("RULE_OUTSIDE_VALIDITY")
        rule_scenario = scope.get("scenario_id")
        if normalized_context["mode"] == "ACTUAL":
            if rule_scenario is not None:
                exclusions.append("SCENARIO_RULE_EXCLUDED")
        else:
            if rule_scenario not in {None, normalized_context["scenario_id"]}:
                exclusions.append("SCENARIO_MISMATCH")
        for field in _SCOPE_ORDER[:-1]:
            if field in scope and scope[field] != normalized_context[field]:
                exclusions.append(f"{field.upper()}_MISMATCH")
        specificity = tuple(1 if field in scope else 0 for field in _SCOPE_ORDER)
        ordering = (
            specificity,
            rule["priority"],
            valid_from,
            rule["version"],
        )
        eligible = not exclusions
        candidate = {
            "rule": _rule_ref(rule),
            "eligible": eligible,
            "selected": False,
            "exclusion_reasons": sorted(set(exclusions)),
            "ordering_tuple": [
                list(specificity),
                rule["priority"],
                rule["valid_from"],
                rule["version"],
            ] if eligible else None,
        }
        candidates.append(candidate)
        if eligible:
            eligible_rows.append((ordering, index))

    state = "VALID"
    diagnostic: str | None = None
    eligible_rule_docs = [
        normalized_rules[index] for _, index in eligible_rows
    ]
    groups: dict[str, int] = {}
    for rule in eligible_rule_docs:
        group = rule["exclusivity_group"]
        if group is not None:
            groups[group] = groups.get(group, 0) + 1
    if any(count > 1 for count in groups.values()):
        state = "CONFLICT"
        diagnostic = "RULE_EXCLUSIVITY_OVERLAP"
    elif not eligible_rows:
        state = "BLOCKED"
        status_only = any(
            candidate["exclusion_reasons"] == ["RULE_NOT_APPROVED"]
            for candidate in candidates
        )
        diagnostic = "RULE_NOT_APPROVED" if status_only else "RULE_REQUIRED_MISSING"
    else:
        eligible_rows.sort(key=lambda item: item[0], reverse=True)
        best_order = eligible_rows[0][0]
        best = [index for order, index in eligible_rows if order == best_order]
        if len(best) != 1:
            state = "CONFLICT"
            diagnostic = "RULE_RESOLUTION_TIE"
        else:
            candidates[best[0]]["selected"] = True

    payload = {
        "resolver_contract_version": RESOLVER_CONTRACT_VERSION,
        "context_hash": canonical_hash(normalized_context),
        "state": state,
        "diagnostic_code": diagnostic,
        "candidates": candidates,
        "actor": normalized_context["actor"],
        "resolved_at": normalized_context["resolved_at"],
        "trace_id": "",
    }
    payload["trace_id"] = canonical_hash(payload, exclude=frozenset({"trace_id"}))
    return payload


def evaluate_resolved_rule(
    resolution: Mapping[str, Any],
    rules: Sequence[Mapping[str, Any]],
    variables: Mapping[str, Mapping[str, Any]],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    validated_policy = validate_rounding_policy(policy)
    normalized_rules = [_validate_rule_document(rule) for rule in rules]
    rule_lookup = {
        (rule["rule_id"], rule["version"], rule["content_hash"]): rule
        for rule in normalized_rules
    }
    resolution_fields = {
        "resolver_contract_version", "context_hash", "state", "diagnostic_code",
        "candidates", "actor", "resolved_at", "trace_id",
    }
    if (
        not isinstance(resolution, Mapping)
        or set(resolution) != resolution_fields
        or resolution.get("resolver_contract_version") != RESOLVER_CONTRACT_VERSION
        or resolution.get("state") not in {
            "VALID", "BLOCKED", "CONFLICT", "UNAVAILABLE",
        }
    ):
        raise FinanceError("RULE_RESOLUTION_INVALID")
    trace_id = resolution.get("trace_id")
    if (
        not isinstance(trace_id, str)
        or _HASH_RE.fullmatch(trace_id) is None
        or canonical_hash(resolution, exclude=frozenset({"trace_id"})) != trace_id
    ):
        raise FinanceError("RULE_RESOLUTION_TRACE_MISMATCH")
    state = resolution["state"]
    diagnostic = resolution.get("diagnostic_code")
    if (state == "VALID") != (diagnostic is None):
        raise FinanceError("RULE_RESOLUTION_INVALID")
    candidates = resolution.get("candidates")
    if not isinstance(candidates, list):
        raise FinanceError("RULE_RESOLUTION_INVALID")
    selected = [
        candidate for candidate in candidates
        if isinstance(candidate, Mapping)
        and candidate.get("eligible") is True
        and candidate.get("selected") is True
    ]
    if state != "VALID":
        if selected:
            raise FinanceError("RULE_RESOLUTION_INVALID")
        return _value_to_dict(
            _make_nonvalid(
                str(state),
                value_type="DECIMAL",
                unit="DIMENSIONLESS",
                currency=None,
                reason_code=str(diagnostic),
                source_ids=(trace_id,),
            )
        )
    if len(selected) != 1:
        raise FinanceError("RULE_RESOLUTION_INVALID")
    ref = selected[0].get("rule")
    if (
        not isinstance(ref, Mapping)
        or set(ref) != {"rule_id", "version", "content_hash"}
    ):
        raise FinanceError("RULE_RESOLUTION_INVALID")
    key = (ref.get("rule_id"), ref.get("version"), ref.get("content_hash"))
    if key not in rule_lookup:
        raise FinanceError("RULE_REFERENCE_MISSING")
    rule = rule_lookup[key]
    dependencies = rule["dependencies"]
    missing = sorted(set(dependencies) - set(variables))
    if missing:
        value_type, unit, currency = _expected_rule_signature(rule)
        return _value_to_dict(
            _make_nonvalid(
                "UNAVAILABLE",
                value_type=value_type,
                unit=unit,
                currency=currency,
                reason_code=f"RULE_DEPENDENCY_UNAVAILABLE:{missing[0]}",
                source_ids=(trace_id, rule["content_hash"]),
            )
        )
    typed_variables = {
        name: _value_from_dict(raw, source_id=name)
        for name, raw in variables.items()
    }
    dependency_values = [typed_variables[name] for name in dependencies]
    if rule["method"] == "SAFE_EXPRESSION":
        return evaluate_expression(
            rule["expression"],
            {name: variables[name] for name in dependencies},
            dependencies,
            validated_policy,
        )
    if rule["method"] == "FIXED_VALUE":
        value = _input_decimal(rule["value"], validated_policy, code="RULE_VALUE_INVALID")
        result_type = "MONEY" if rule["unit"].startswith("MONEY") else "DECIMAL"
        currency = rule["currency"] if result_type == "MONEY" else None
        rounded, scale = _quantize(
            value, validated_policy, "RULE_COMPONENT_RESULT", result_type
        )
        return _value_to_dict(
            _make_valid(
                rounded,
                value_type=result_type,
                unit=rule["unit"],
                currency=currency,
                source_ids=(trace_id, rule["content_hash"]),
            ),
            scale=scale,
        )

    propagated = _propagate(
        dependency_values,
        value_type="RATE",
        unit="RATE",
        currency=None,
    )
    if propagated is not None:
        return _value_to_dict(propagated)
    rate = _input_decimal(rule["rate"], validated_policy, code="RULE_RATE_INVALID")
    rounded, scale = _quantize(
        rate, validated_policy, "RULE_COMPONENT_RESULT", "RATE"
    )
    return _value_to_dict(
        _make_valid(
            rounded,
            value_type="RATE",
            unit="RATE",
            currency=None,
            source_ids=(trace_id, rule["content_hash"]),
        ),
        scale=scale,
    )
