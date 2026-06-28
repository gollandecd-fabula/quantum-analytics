from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from . import verification as _base

ROUNDING_APPLICATION_POINTS = frozenset({
    "RULE_INPUT_NORMALIZATION",
    "RULE_COMPONENT_RESULT",
    "METRIC_FINAL_ACCOUNTING",
    "REPORT_PRESENTATION",
    "EXPORT_PRESENTATION",
})
ROUNDING_MODES = frozenset({
    "HALF_EVEN",
    "HALF_UP",
    "DOWN",
    "UP",
    "FLOOR",
    "CEILING",
})


def _append(errors: list[str], code: str) -> None:
    if code not in errors:
        errors.append(code)


def _is_allowed_string(value: object, allowed: frozenset[str] | set[str]) -> bool:
    return isinstance(value, str) and value in allowed


def verify_evidence_chain(graph: object, **kwargs: Any) -> tuple[str, ...]:
    errors = list(_base.verify_evidence_chain(graph, **kwargs))
    if not isinstance(graph, Mapping):
        return tuple(errors)

    raw_nodes = graph.get("nodes")
    raw_edges = graph.get("edges")
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        return tuple(errors)

    nodes: dict[str, Mapping[str, Any]] = {}
    for node in raw_nodes:
        if not isinstance(node, Mapping):
            continue
        node_id = node.get("node_id")
        if isinstance(node_id, str) and node_id and node_id not in nodes:
            nodes[node_id] = node

    root_ref = graph.get("root_metric_snapshot_ref")
    roots = [
        node_id
        for node_id, node in nodes.items()
        if node.get("node_type") == "METRIC_SNAPSHOT"
        and node.get("artifact_ref") == root_ref
    ]
    if len(roots) != 1:
        return tuple(errors)
    root_id = roots[0]

    profile_ids = {
        edge.get("to_node_id")
        for edge in raw_edges
        if isinstance(edge, Mapping)
        and edge.get("from_node_id") == root_id
        and edge.get("edge_type") == "RESULT_CALCULATED_WITH"
        and isinstance(edge.get("to_node_id"), str)
        and nodes.get(str(edge.get("to_node_id")), {}).get("node_type")
        == "CALCULATION_PROFILE"
    }
    for profile_id in profile_ids:
        has_rule = any(
            isinstance(edge, Mapping)
            and edge.get("from_node_id") == profile_id
            and edge.get("edge_type") == "PROFILE_SELECTS_RULE"
            and isinstance(edge.get("to_node_id"), str)
            and nodes.get(str(edge.get("to_node_id")), {}).get("node_type")
            == "CONFIGURATION_RULE"
            for edge in raw_edges
        )
        if not has_rule:
            _append(errors, "EVIDENCE_REQUIRED_PATH_MISSING")

    return tuple(errors)


def verify_metric_snapshot(snapshot: object) -> tuple[str, ...]:
    errors = list(_base.verify_metric_snapshot(snapshot))
    if not isinstance(snapshot, Mapping):
        return tuple(errors)

    for field in (
        "marketplace_account_id",
        "prior_snapshot_id",
        "restates_snapshot_id",
    ):
        value = snapshot.get(field)
        if value is not None and not (
            isinstance(value, str) and bool(value)
        ):
            _append(errors, "METRIC_SNAPSHOT_MALFORMED")

    if (
        snapshot.get("state") == "VALID"
        and snapshot.get("value_type") in ("DECIMAL", "RATE")
        and snapshot.get("unit") in ("MONEY", "MONEY_PER_ITEM")
    ):
        _append(errors, "METRIC_SNAPSHOT_VALUE_INVALID")

    rounding = snapshot.get("rounding")
    if isinstance(rounding, Mapping) and (
        not _is_allowed_string(
            rounding.get("application_point"), ROUNDING_APPLICATION_POINTS
        )
        or not _is_allowed_string(rounding.get("resolved_mode"), ROUNDING_MODES)
    ):
        _append(errors, "METRIC_SNAPSHOT_ROUNDING_INVALID")

    return tuple(errors)


def diagnose_metric_snapshot(snapshot: object) -> str | None:
    errors = verify_metric_snapshot(snapshot)
    return errors[0] if errors else None
