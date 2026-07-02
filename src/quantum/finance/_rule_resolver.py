from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ._common import FinanceError, RESOLVER_CONTRACT_VERSION, _SCOPE_ORDER, _parse_rfc3339, canonical_hash
from ._rule_context import validate_rule_context
from ._rule_documents import _validate_rule_document, rule_ref


def resolve_rule(
    rules: Sequence[Mapping[str, Any]],
    context: Mapping[str, Any],
) -> dict[str, Any]:
    normalized_context = validate_rule_context(context)
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
        elif rule_scenario not in {None, normalized_context["scenario_id"]}:
            exclusions.append("SCENARIO_MISMATCH")
        for field in _SCOPE_ORDER[:-1]:
            if field in scope and scope[field] != normalized_context[field]:
                exclusions.append(f"{field.upper()}_MISMATCH")
        specificity = tuple(1 if field in scope else 0 for field in _SCOPE_ORDER)
        ordering = (specificity, rule["priority"], valid_from, rule["version"])
        eligible = not exclusions
        candidates.append({
            "rule": rule_ref(rule),
            "eligible": eligible,
            "selected": False,
            "exclusion_reasons": sorted(set(exclusions)),
            "ordering_tuple": [
                list(specificity), rule["priority"], rule["valid_from"], rule["version"],
            ] if eligible else None,
        })
        if eligible:
            eligible_rows.append((ordering, index))
    state = "VALID"
    diagnostic: str | None = None
    eligible_rules = [normalized_rules[index] for _, index in eligible_rows]
    groups: dict[str, int] = {}
    for rule in eligible_rules:
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
