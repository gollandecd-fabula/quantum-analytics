from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from ._common import (
    FinanceError,
    _CURRENCY_RE,
    _DECIMAL_RE,
    _HASH_RE,
    _ID_RE,
    _SCOPE_ORDER,
    _clone_json,
    _is_nonempty_string,
    _is_positive_int,
    _parse_rfc3339,
    canonical_hash,
)
from ._expression_validation import validate_expression_ast


def rule_ref(rule: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "rule_id": rule["rule_id"],
        "version": rule["version"],
        "content_hash": rule["content_hash"],
    }


def expected_rule_signature(rule: Mapping[str, Any]) -> tuple[str, str, str | None]:
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
    payloads = [field for field in ("value", "rate", "expression") if field in rule]
    expected_payload = {
        "FIXED_VALUE": "value",
        "RATE": "rate",
        "SAFE_EXPRESSION": "expression",
    }[method]
    if payloads != [expected_payload]:
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
    approval = rule["approval_reference"]
    if approval is not None and not _is_nonempty_string(approval):
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
    money_units = {
        "MONEY", "MONEY_PER_ITEM", "MONEY_PER_ORDER",
        "MONEY_PER_EVENT", "MONEY_PER_PERIOD",
    }
    if unit in money_units:
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
    allowed_bases = {
        "NONE", "UNIT", "ORDER", "EVENT", "PERIOD", "GROSS_SALES", "NET_SALES",
        "PAYOUT", "PRODUCT_COST", "CUSTOM_VARIABLE",
    }
    if rule["base"] not in allowed_bases:
        raise FinanceError("RULE_DEPENDENCY_UNKNOWN")
    if rule["base"] == "CUSTOM_VARIABLE" and not dependencies:
        raise FinanceError("RULE_DEPENDENCY_UNKNOWN")
    group = rule["exclusivity_group"]
    if group is not None and not _is_nonempty_string(group):
        raise FinanceError("RULE_DOCUMENT_INVALID")
    return _clone_json(rule)
