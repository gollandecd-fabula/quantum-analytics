from __future__ import annotations

from collections.abc import Mapping

from ._common import (
    FinanceError,
    RESOLVER_CONTRACT_VERSION,
    _HASH_RE,
    _is_nonempty_string,
    _parse_rfc3339,
    canonical_hash,
)


def validate_resolution_envelope(resolution: Mapping[str, object]) -> None:
    required = {
        "resolver_contract_version", "context_hash", "state", "diagnostic_code",
        "candidates", "actor", "resolved_at", "trace_id",
    }
    if not isinstance(resolution, Mapping) or set(resolution) != required:
        raise FinanceError("RULE_RESOLUTION_INVALID")
    if resolution.get("resolver_contract_version") != RESOLVER_CONTRACT_VERSION:
        raise FinanceError("RULE_RESOLUTION_INVALID")
    if resolution.get("state") not in {"VALID", "BLOCKED", "CONFLICT", "UNAVAILABLE"}:
        raise FinanceError("RULE_RESOLUTION_INVALID")
    for field in ("context_hash", "trace_id"):
        value = resolution.get(field)
        if not isinstance(value, str) or _HASH_RE.fullmatch(value) is None:
            raise FinanceError("RULE_RESOLUTION_INVALID")
    if not _is_nonempty_string(resolution.get("actor")):
        raise FinanceError("RULE_RESOLUTION_INVALID")
    _parse_rfc3339(resolution.get("resolved_at"), "RULE_RESOLUTION_INVALID")
    if canonical_hash(resolution, exclude=frozenset({"trace_id"})) != resolution["trace_id"]:
        raise FinanceError("RULE_RESOLUTION_TRACE_MISMATCH")
    state = resolution["state"]
    diagnostic = resolution.get("diagnostic_code")
    if (state == "VALID") != (diagnostic is None):
        raise FinanceError("RULE_RESOLUTION_INVALID")
    candidates = resolution.get("candidates")
    if not isinstance(candidates, list):
        raise FinanceError("RULE_RESOLUTION_INVALID")
    selected = 0
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            raise FinanceError("RULE_RESOLUTION_INVALID")
        required_candidate = {
            "rule", "eligible", "selected", "exclusion_reasons", "ordering_tuple",
        }
        if set(candidate) != required_candidate:
            raise FinanceError("RULE_RESOLUTION_INVALID")
        if not isinstance(candidate.get("eligible"), bool):
            raise FinanceError("RULE_RESOLUTION_INVALID")
        if not isinstance(candidate.get("selected"), bool):
            raise FinanceError("RULE_RESOLUTION_INVALID")
        ref = candidate.get("rule")
        if not isinstance(ref, Mapping):
            raise FinanceError("RULE_RESOLUTION_INVALID")
        if set(ref) != {"rule_id", "version", "content_hash"}:
            raise FinanceError("RULE_RESOLUTION_INVALID")
        reasons = candidate.get("exclusion_reasons")
        if not isinstance(reasons, list):
            raise FinanceError("RULE_RESOLUTION_INVALID")
        if any(not _is_nonempty_string(item) for item in reasons):
            raise FinanceError("RULE_RESOLUTION_INVALID")
        if candidate["selected"]:
            if not candidate["eligible"]:
                raise FinanceError("RULE_RESOLUTION_INVALID")
            if reasons or candidate.get("ordering_tuple") is None:
                raise FinanceError("RULE_RESOLUTION_INVALID")
            selected += 1
    if state == "VALID" and selected != 1:
        raise FinanceError("RULE_RESOLUTION_INVALID")
    if state != "VALID" and selected != 0:
        raise FinanceError("RULE_RESOLUTION_INVALID")
