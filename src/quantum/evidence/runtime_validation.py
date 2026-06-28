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


def _graph_has_cycle(graph: object) -> bool | None:
    if not isinstance(graph, Mapping):
        return None
    raw_nodes = graph.get("nodes")
    raw_edges = graph.get("edges")
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        return None

    node_ids = {
        node.get("node_id")
        for node in raw_nodes
        if isinstance(node, Mapping)
        and isinstance(node.get("node_id"), str)
        and node.get("node_id")
    }
    adjacency: dict[str, list[str]] = {str(node_id): [] for node_id in node_ids}
    for edge in raw_edges:
        if not isinstance(edge, Mapping):
            continue
        source = edge.get("from_node_id")
        target = edge.get("to_node_id")
        if isinstance(source, str) and isinstance(target, str):
            if source in adjacency and target in adjacency:
                adjacency[source].append(target)

    state: dict[str, int] = {}
    for start in adjacency:
        if state.get(start, 0) != 0:
            continue
        state[start] = 1
        stack: list[tuple[str, int]] = [(start, 0)]
        while stack:
            node_id, index = stack[-1]
            targets = adjacency.get(node_id, ())
            if index >= len(targets):
                state[node_id] = 2
                stack.pop()
                continue
            target = targets[index]
            stack[-1] = (node_id, index + 1)
            target_state = state.get(target, 0)
            if target_state == 1:
                return True
            if target_state == 0:
                state[target] = 1
                stack.append((target, 0))
    return False


def verify_evidence_chain(graph: object, **kwargs: Any) -> tuple[str, ...]:
    cycle = _graph_has_cycle(graph)
    try:
        errors = list(_base.verify_evidence_chain(graph, **kwargs))
    except RecursionError:
        errors = []
        _append(
            errors,
            "EVIDENCE_GRAPH_CYCLE" if cycle is True else "EVIDENCE_MALFORMED",
        )
    if cycle is True:
        _append(errors, "EVIDENCE_GRAPH_CYCLE")
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
        and snapshot.get("value_type") in {"DECIMAL", "RATE"}
        and snapshot.get("unit") in {"MONEY", "MONEY_PER_ITEM"}
    ):
        _append(errors, "METRIC_SNAPSHOT_VALUE_INVALID")

    rounding = snapshot.get("rounding")
    if isinstance(rounding, Mapping) and (
        rounding.get("application_point") not in ROUNDING_APPLICATION_POINTS
        or rounding.get("resolved_mode") not in ROUNDING_MODES
    ):
        _append(errors, "METRIC_SNAPSHOT_ROUNDING_INVALID")

    return tuple(errors)


def diagnose_metric_snapshot(snapshot: object) -> str | None:
    errors = verify_metric_snapshot(snapshot)
    return errors[0] if errors else None
