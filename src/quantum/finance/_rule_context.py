from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ._common import FinanceError, _clone_json, _is_nonempty_string, _parse_rfc3339


def validate_rule_context(context: object) -> dict[str, Any]:
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
    optional = ("marketplace_account_id", "marketplace", "product_id", "product_group_id")
    for field in optional:
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
