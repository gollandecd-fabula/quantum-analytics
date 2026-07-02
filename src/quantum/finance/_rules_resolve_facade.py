from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ._rules import resolve_rule as _base_resolve
from ._rules_trace_registry import register_resolution, snapshot_rules


def resolve_rule(
    rules: Sequence[Mapping[str, Any]],
    context: Mapping[str, Any],
) -> dict[str, Any]:
    snapshot = snapshot_rules(rules)
    resolution = _base_resolve(snapshot, context)
    register_resolution(resolution, snapshot)
    return resolution
