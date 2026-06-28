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


def _typed_target_ids(
    raw_edges: list[object],
    nodes: Mapping[str, Mapping[str, Any]],
    source_id: str,
    edge_type: str,
    node_type: str,
) -> set[str]:
    return {
        target_id
        for edge in raw_edges
        if isinstance(edge, Mapping)
        and edge.get("from_node_id") == source_id
        and edge.get("edge_type") == edge_type
        and isinstance((target_id := edge.get("to_node_id")), str)
        and nodes.get(target_id, {}).get("node_type") == node_type
    }


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

    singular_root_paths = (
        ("RESULT_DEFINED_BY", "METRIC_DEFINITION"),
        ("RESULT_CALCULATED_WITH", "CALCULATION_PROFILE"),
        ("RESULT_HAS_FRESHNESS", "FRESHNESS_ASSESSMENT"),
        ("RESULT_HAS_CONFIDENCE", "CONFIDENCE_ASSESSMENT"),
    )
    for edge_type, node_type in singular_root_paths:
        if len(
            _typed_target_ids(raw_edges, nodes, root_id, edge_type, node_type)
        ) != 1:
            _append(errors, "EVIDENCE_REQUIRED_PATH_MISSING")

    profile_ids = _typed_target_ids(
        raw_edges,
        nodes,
        root_id,
        "RESULT_CALCULATED_WITH",
        "CALCULATION_PROFILE",
    )
    resolution_ids = _typed_target_ids(
        raw_edges,
        nodes,
        root_id,
        "RESULT_USES_RESOLUTION",
        "RULE_RESOLUTION",
    )

    resolved_rule_ids: set[str] = set()
    for resolution_id in resolution_ids:
        resolution_rule_ids = _typed_target_ids(
            raw_edges,
            nodes,
            resolution_id,
            "RESOLUTION_SELECTS_RULE",
            "CONFIGURATION_RULE",
        )
        if len(resolution_rule_ids) != 1:
            _append(errors, "EVIDENCE_REQUIRED_PATH_MISSING")
        resolved_rule_ids.update(resolution_rule_ids)

    for profile_id in profile_ids:
        if len(
            _typed_target_ids(
                raw_edges,
                nodes,
                profile_id,
                "PROFILE_USES_ROUNDING",
                "ROUNDING_POLICY",
            )
        ) != 1:
            _append(errors, "EVIDENCE_REQUIRED_PATH_MISSING")
        if len(
            _typed_target_ids(
                raw_edges,
                nodes,
                profile_id,
                "PROFILE_USES_SOURCE_AUTHORITY",
                "SOURCE_AUTHORITY",
            )
        ) != 1:
            _append(errors, "EVIDENCE_REQUIRED_PATH_MISSING")

        profile_rule_ids = _typed_target_ids(
            raw_edges,
            nodes,
            profile_id,
            "PROFILE_SELECTS_RULE",
            "CONFIGURATION_RULE",
        )
        if (
            not profile_rule_ids
            or not resolved_rule_ids
            or not profile_rule_ids.issubset(resolved_rule_ids)
        ):
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
