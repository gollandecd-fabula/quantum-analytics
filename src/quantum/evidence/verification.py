from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

_HASH_RE = re.compile(r"^[a-f0-9]{64}$")
_DECIMAL_RE = re.compile(r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?$")
_RFC3339_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})$"
)

NODE_TYPES = frozenset({
    "METRIC_SNAPSHOT", "METRIC_DEFINITION", "CALCULATION_PROFILE",
    "RULE_RESOLUTION", "CONFIGURATION_RULE", "ROUNDING_POLICY",
    "SOURCE_AUTHORITY", "PRODUCT_MASTER", "TRANSFORMATION",
    "CANONICAL_EVENT", "SOURCE_RECORD", "SOURCE_FILE",
    "FRESHNESS_ASSESSMENT", "CONFIDENCE_ASSESSMENT",
    "RECONCILIATION_RESULT", "APPROVAL",
})

EDGE_SIGNATURES: dict[str, tuple[str | None, str]] = {
    "RESULT_DEFINED_BY": ("METRIC_SNAPSHOT", "METRIC_DEFINITION"),
    "RESULT_CALCULATED_WITH": ("METRIC_SNAPSHOT", "CALCULATION_PROFILE"),
    "RESULT_USES_RESOLUTION": ("METRIC_SNAPSHOT", "RULE_RESOLUTION"),
    "RESOLUTION_SELECTS_RULE": ("RULE_RESOLUTION", "CONFIGURATION_RULE"),
    "PROFILE_SELECTS_RULE": ("CALCULATION_PROFILE", "CONFIGURATION_RULE"),
    "PROFILE_USES_ROUNDING": ("CALCULATION_PROFILE", "ROUNDING_POLICY"),
    "PROFILE_USES_SOURCE_AUTHORITY": ("CALCULATION_PROFILE", "SOURCE_AUTHORITY"),
    "RESULT_DERIVED_FROM_EVENT": ("METRIC_SNAPSHOT", "CANONICAL_EVENT"),
    "EVENT_NORMALIZED_FROM_RECORD": ("CANONICAL_EVENT", "SOURCE_RECORD"),
    "RECORD_READ_FROM_FILE": ("SOURCE_RECORD", "SOURCE_FILE"),
    "RESULT_USES_TRANSFORMATION": ("METRIC_SNAPSHOT", "TRANSFORMATION"),
    "RESULT_USES_PRODUCT_MASTER": ("METRIC_SNAPSHOT", "PRODUCT_MASTER"),
    "RESULT_HAS_FRESHNESS": ("METRIC_SNAPSHOT", "FRESHNESS_ASSESSMENT"),
    "RESULT_HAS_CONFIDENCE": ("METRIC_SNAPSHOT", "CONFIDENCE_ASSESSMENT"),
    "RESULT_RECONCILED_BY": ("METRIC_SNAPSHOT", "RECONCILIATION_RESULT"),
    "ARTIFACT_APPROVED_BY": (None, "APPROVAL"),
    "SNAPSHOT_SUPERSEDES": ("METRIC_SNAPSHOT", "METRIC_SNAPSHOT"),
    "SNAPSHOT_RESTATES": ("METRIC_SNAPSHOT", "METRIC_SNAPSHOT"),
}

_GRAPH_FIELDS = frozenset({
    "evidence_chain_id", "version", "content_hash", "organization_id", "mode",
    "scenario_id", "root_metric_snapshot_ref", "nodes", "edges", "actor",
    "reason", "trace_id", "created_at",
})
_NODE_FIELDS = frozenset({
    "node_id", "node_type", "artifact_ref", "organization_id", "mode",
    "scenario_id", "metadata",
})
_EDGE_FIELDS = frozenset({"from_node_id", "to_node_id", "edge_type", "sequence"})
_REF_FIELDS = frozenset({"id", "version", "content_hash"})

_SNAPSHOT_FIELDS = frozenset({
    "metric_snapshot_id", "snapshot_revision", "organization_id",
    "marketplace_account_id", "mode", "scenario_id", "metric_definition_ref",
    "calculation_profile_ref", "accounting_view", "period_start", "period_end",
    "state", "value", "value_type", "unit", "currency", "reason_code",
    "expense_boundary", "rounding", "source_authority_ref", "evidence_chain_ref",
    "data_freshness_state", "freshness_observed_at", "freshness_deadline",
    "confidence_state", "confidence_reasons", "limitations", "valid_from",
    "valid_to", "prior_snapshot_id", "restates_snapshot_id", "actor", "reason",
    "trace_id", "calculated_at", "content_hash",
})
_STATES = frozenset({
    "VALID", "EMPTY", "BLOCKED", "UNAVAILABLE", "CONFLICT", "INVALID",
    "NOT_APPLICABLE",
})
_EXPENSES = frozenset({
    "MARKETPLACE_COMMISSION", "FORWARD_LOGISTICS", "REVERSE_LOGISTICS",
    "STORAGE", "ADVERTISING", "FINES_WITHHOLDINGS", "PRODUCT_COST",
    "OTHER_EXPENSE", "TAX",
})
_UNITS = frozenset({
    "MONEY", "MONEY_PER_ITEM", "ITEM", "ORDER", "EVENT", "PERCENT", "RATIO",
    "COUNT",
})
_MODES = frozenset({"ACTUAL", "SCENARIO"})
_VALUE_TYPES = frozenset({"MONEY", "INTEGER", "DECIMAL", "RATE"})
_MONEY_UNITS = frozenset({"MONEY", "MONEY_PER_ITEM"})
_ACCOUNTING_VIEWS = frozenset({"OPERATIONAL", "SETTLEMENT", "TAX_RECOGNITION"})
_FRESHNESS_STATES = frozenset({"CURRENT", "STALE", "UNKNOWN", "NOT_APPLICABLE"})
_CONFIDENCE_STATES = frozenset({"HIGH", "MEDIUM", "LOW", "UNKNOWN", "NOT_APPLICABLE"})
_ROUNDING_APPLICATION_POINTS = frozenset({
    "RULE_INPUT_NORMALIZATION",
    "RULE_COMPONENT_RESULT",
    "METRIC_FINAL_ACCOUNTING",
    "REPORT_PRESENTATION",
    "EXPORT_PRESENTATION",
})
_ROUNDING_MODES = frozenset({
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


def _canonical_hash(document: Mapping[str, Any], excluded: frozenset[str]) -> str:
    payload = {key: value for key, value in document.items() if key not in excluded}
    raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def canonical_graph_hash(graph: Mapping[str, Any]) -> str:
    return _canonical_hash(graph, frozenset({"content_hash"}))


def canonical_snapshot_hash(snapshot: Mapping[str, Any]) -> str:
    return _canonical_hash(snapshot, frozenset({"content_hash"}))


def _is_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_non_negative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _is_hash(value: object) -> bool:
    return isinstance(value, str) and _HASH_RE.fullmatch(value) is not None


def _is_allowed_string(value: object, allowed: frozenset[str]) -> bool:
    return isinstance(value, str) and value in allowed


def _valid_datetime(value: object) -> bool:
    if not isinstance(value, str) or _RFC3339_RE.fullmatch(value) is None:
        return False
    normalized = value[:-1] + "+00:00" if value[-1] in {"Z", "z"} else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _parse_datetime(value: object) -> datetime | None:
    if not _valid_datetime(value):
        return None
    text = str(value)
    normalized = text[:-1] + "+00:00" if text[-1] in {"Z", "z"} else text
    return datetime.fromisoformat(normalized)


def _valid_ref(value: object, *, chain_locator: bool = False) -> bool:
    if not isinstance(value, Mapping):
        return False
    expected = {"id", "version"} if chain_locator else _REF_FIELDS
    if set(value) != set(expected):
        return False
    if not _is_nonempty_string(value.get("id")) or not _is_positive_int(value.get("version")):
        return False
    return chain_locator or _is_hash(value.get("content_hash"))


def verify_evidence_chain(
    graph: object,
    *,
    source_loader: Callable[[str], bytes] | None = None,
    require_source_bytes: bool = False,
) -> tuple[str, ...]:
    """Return deterministic fail-closed diagnostics for an Evidence Chain."""
    errors: list[str] = []
    if not isinstance(graph, Mapping):
        return ("EVIDENCE_MALFORMED",)

    if set(graph) != set(_GRAPH_FIELDS):
        _append(errors, "EVIDENCE_MALFORMED")
    if not _is_nonempty_string(graph.get("evidence_chain_id")):
        _append(errors, "EVIDENCE_MALFORMED")
    if not _is_positive_int(graph.get("version")):
        _append(errors, "EVIDENCE_VERSION_INVALID")
    if not _is_nonempty_string(graph.get("organization_id")):
        _append(errors, "EVIDENCE_TENANT_MISMATCH")
    mode = graph.get("mode")
    scenario_id = graph.get("scenario_id")
    if not _is_allowed_string(mode, _MODES):
        _append(errors, "EVIDENCE_MODE_CONTAMINATION")
    elif mode == "ACTUAL" and scenario_id is not None:
        _append(errors, "EVIDENCE_MODE_CONTAMINATION")
    elif mode == "SCENARIO" and not _is_nonempty_string(scenario_id):
        _append(errors, "EVIDENCE_MODE_CONTAMINATION")
    for field in ("actor", "reason", "trace_id"):
        if not _is_nonempty_string(graph.get(field)):
            _append(errors, "EVIDENCE_MALFORMED")
    if not _valid_datetime(graph.get("created_at")):
        _append(errors, "EVIDENCE_TIMESTAMP_INVALID")

    try:
        supplied_hash = graph.get("content_hash")
        if not _is_hash(supplied_hash) or supplied_hash != canonical_graph_hash(graph):
            _append(errors, "EVIDENCE_HASH_MISMATCH")
    except (TypeError, ValueError, OverflowError):
        _append(errors, "EVIDENCE_MALFORMED")

    root_ref = graph.get("root_metric_snapshot_ref")
    if not _valid_ref(root_ref):
        if isinstance(root_ref, Mapping) and not _is_positive_int(root_ref.get("version")):
            _append(errors, "EVIDENCE_VERSION_INVALID")
        else:
            _append(errors, "EVIDENCE_HASH_MISMATCH")

    raw_nodes = graph.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        _append(errors, "EVIDENCE_NODE_MISSING")
        raw_nodes = []

    nodes: dict[str, Mapping[str, Any]] = {}
    for raw_node in raw_nodes:
        if not isinstance(raw_node, Mapping) or set(raw_node) != set(_NODE_FIELDS):
            _append(errors, "EVIDENCE_MALFORMED")
            continue
        node_id = raw_node.get("node_id")
        if not _is_nonempty_string(node_id):
            _append(errors, "EVIDENCE_NODE_MISSING")
            continue
        node_id = str(node_id)
        if node_id in nodes:
            _append(errors, "EVIDENCE_NODE_DUPLICATE")
            continue
        nodes[node_id] = raw_node
        if not _is_allowed_string(raw_node.get("node_type"), NODE_TYPES):
            _append(errors, "EVIDENCE_NODE_TYPE_INVALID")
        ref = raw_node.get("artifact_ref")
        if not _valid_ref(ref):
            if isinstance(ref, Mapping) and not _is_positive_int(ref.get("version")):
                _append(errors, "EVIDENCE_VERSION_INVALID")
            else:
                _append(errors, "EVIDENCE_HASH_MISMATCH")
        if raw_node.get("organization_id") != graph.get("organization_id"):
            _append(errors, "EVIDENCE_TENANT_MISMATCH")
        if (
            raw_node.get("mode") != mode
            or (mode == "ACTUAL" and raw_node.get("scenario_id") is not None)
            or (mode == "SCENARIO" and raw_node.get("scenario_id") != scenario_id)
        ):
            _append(errors, "EVIDENCE_MODE_CONTAMINATION")
        if not isinstance(raw_node.get("metadata"), Mapping):
            _append(errors, "EVIDENCE_MALFORMED")

    roots = [
        node for node in nodes.values()
        if node.get("node_type") == "METRIC_SNAPSHOT"
        and node.get("artifact_ref") == root_ref
    ]
    if len(roots) != 1:
        _append(errors, "EVIDENCE_NODE_MISSING")
        root_id: str | None = None
    else:
        root_id = str(roots[0]["node_id"])

    raw_edges = graph.get("edges")
    if not isinstance(raw_edges, list):
        _append(errors, "EVIDENCE_MALFORMED")
        raw_edges = []

    adjacency: dict[str, list[str]] = {node_id: [] for node_id in nodes}
    typed_targets: dict[tuple[str, str], list[str]] = {}
    seen_edges: set[tuple[str, str, str]] = set()
    valid_edges: list[tuple[str, str, str, int]] = []

    for raw_edge in raw_edges:
        if not isinstance(raw_edge, Mapping) or set(raw_edge) != set(_EDGE_FIELDS):
            _append(errors, "EVIDENCE_MALFORMED")
            continue
        source = raw_edge.get("from_node_id")
        target = raw_edge.get("to_node_id")
        edge_type = raw_edge.get("edge_type")
        sequence = raw_edge.get("sequence")
        if not all(_is_nonempty_string(value) for value in (source, target, edge_type)):
            _append(errors, "EVIDENCE_EDGE_INVALID")
            continue
        source, target, edge_type = str(source), str(target), str(edge_type)
        if not _is_non_negative_int(sequence):
            _append(errors, "EVIDENCE_TRANSFORMATION_ORDER_AMBIGUOUS")
            continue
        key = (source, target, edge_type)
        if key in seen_edges:
            _append(errors, "EVIDENCE_EDGE_DUPLICATE")
        seen_edges.add(key)
        if source not in nodes or target not in nodes:
            _append(errors, "EVIDENCE_NODE_MISSING")
            continue
        signature = EDGE_SIGNATURES.get(edge_type)
        if signature is None:
            _append(errors, "EVIDENCE_EDGE_INVALID")
            continue
        source_type, target_type = signature
        if (
            (source_type is not None and nodes[source].get("node_type") != source_type)
            or nodes[target].get("node_type") != target_type
        ):
            _append(errors, "EVIDENCE_EDGE_INVALID")
            continue
        adjacency[source].append(target)
        typed_targets.setdefault((source, edge_type), []).append(target)
        valid_edges.append((source, target, edge_type, int(sequence)))

    state: dict[str, int] = {}
    has_cycle = False
    for start in nodes:
        if state.get(start, 0) != 0:
            continue
        state[start] = 1
        stack: list[tuple[str, int]] = [(start, 0)]
        while stack:
            node_id, index = stack[-1]
            next_nodes = adjacency.get(node_id, ())
            if index >= len(next_nodes):
                state[node_id] = 2
                stack.pop()
                continue
            target = next_nodes[index]
            stack[-1] = (node_id, index + 1)
            target_state = state.get(target, 0)
            if target_state == 1:
                has_cycle = True
                break
            if target_state == 0:
                state[target] = 1
                stack.append((target, 0))
        if has_cycle:
            break
    if has_cycle:
        _append(errors, "EVIDENCE_GRAPH_CYCLE")

    def targets(source: str, edge_type: str, node_type: str) -> list[str]:
        return [
            target for target in typed_targets.get((source, edge_type), ())
            if nodes.get(target, {}).get("node_type") == node_type
        ]

    if root_id is not None:
        reachable: set[str] = set()
        stack = [root_id]
        while stack:
            current = stack.pop()
            if current in reachable:
                continue
            reachable.add(current)
            stack.extend(adjacency.get(current, ()))
        if set(nodes) - reachable:
            _append(errors, "EVIDENCE_ORPHAN_NODE")

        required = (
            ("RESULT_DEFINED_BY", "METRIC_DEFINITION"),
            ("RESULT_CALCULATED_WITH", "CALCULATION_PROFILE"),
            ("RESULT_USES_RESOLUTION", "RULE_RESOLUTION"),
            ("RESULT_USES_TRANSFORMATION", "TRANSFORMATION"),
            ("RESULT_DERIVED_FROM_EVENT", "CANONICAL_EVENT"),
            ("RESULT_HAS_FRESHNESS", "FRESHNESS_ASSESSMENT"),
            ("RESULT_HAS_CONFIDENCE", "CONFIDENCE_ASSESSMENT"),
        )
        if any(not targets(root_id, edge_type, node_type) for edge_type, node_type in required):
            _append(errors, "EVIDENCE_REQUIRED_PATH_MISSING")

        transformation_edges = [
            edge for edge in valid_edges
            if edge[0] == root_id and edge[2] == "RESULT_USES_TRANSFORMATION"
        ]
        sequence = [edge[3] for edge in transformation_edges]
        if sorted(sequence) != list(range(len(sequence))):
            _append(errors, "EVIDENCE_TRANSFORMATION_ORDER_AMBIGUOUS")

        def approved(artifact_id: str) -> bool:
            for approval_id in targets(artifact_id, "ARTIFACT_APPROVED_BY", "APPROVAL"):
                metadata = nodes[approval_id].get("metadata")
                if not isinstance(metadata, Mapping):
                    continue
                if (
                    metadata.get("status") == "APPROVED"
                    and _valid_datetime(metadata.get("approved_at"))
                    and _is_nonempty_string(metadata.get("approver"))
                ):
                    return True
            return False

        for profile in targets(root_id, "RESULT_CALCULATED_WITH", "CALCULATION_PROFILE"):
            rules = targets(profile, "PROFILE_SELECTS_RULE", "CONFIGURATION_RULE")
            rounding = targets(profile, "PROFILE_USES_ROUNDING", "ROUNDING_POLICY")
            authorities = targets(profile, "PROFILE_USES_SOURCE_AUTHORITY", "SOURCE_AUTHORITY")
            if not rules or not rounding or not authorities:
                _append(errors, "EVIDENCE_REQUIRED_PATH_MISSING")
            if any(not approved(node_id) for node_id in rounding + authorities):
                _append(errors, "EVIDENCE_APPROVAL_MISSING")

        for resolution in targets(root_id, "RESULT_USES_RESOLUTION", "RULE_RESOLUTION"):
            if not targets(resolution, "RESOLUTION_SELECTS_RULE", "CONFIGURATION_RULE"):
                _append(errors, "EVIDENCE_REQUIRED_PATH_MISSING")

        for event in targets(root_id, "RESULT_DERIVED_FROM_EVENT", "CANONICAL_EVENT"):
            records = targets(event, "EVENT_NORMALIZED_FROM_RECORD", "SOURCE_RECORD")
            if not records:
                _append(errors, "EVIDENCE_REQUIRED_PATH_MISSING")
            for record in records:
                files = targets(record, "RECORD_READ_FROM_FILE", "SOURCE_FILE")
                if not files:
                    _append(errors, "EVIDENCE_REQUIRED_PATH_MISSING")
                for file_id in files:
                    node = nodes[file_id]
                    metadata = node.get("metadata")
                    ref = node.get("artifact_ref")
                    if not isinstance(metadata, Mapping) or not isinstance(ref, Mapping):
                        _append(errors, "EVIDENCE_SOURCE_FILE_UNAVAILABLE")
                        continue
                    retained = metadata.get("retained_bytes_sha256")
                    locator = metadata.get("storage_locator")
                    if not _is_hash(retained) or not _is_nonempty_string(locator):
                        _append(errors, "EVIDENCE_SOURCE_FILE_UNAVAILABLE")
                        continue
                    if retained != ref.get("content_hash"):
                        _append(errors, "EVIDENCE_HASH_MISMATCH")
                    if source_loader is not None:
                        try:
                            source_bytes = source_loader(str(locator))
                        except Exception:
                            _append(errors, "EVIDENCE_SOURCE_FILE_UNAVAILABLE")
                        else:
                            if not isinstance(source_bytes, bytes):
                                _append(errors, "EVIDENCE_SOURCE_FILE_UNAVAILABLE")
                            elif hashlib.sha256(source_bytes).hexdigest() != retained:
                                _append(errors, "EVIDENCE_SOURCE_BYTES_MISMATCH")
                    elif require_source_bytes:
                        _append(errors, "EVIDENCE_SOURCE_FILE_UNAVAILABLE")

    return tuple(errors)


def diagnose_evidence_chain(graph: object, **kwargs: Any) -> str | None:
    errors = verify_evidence_chain(graph, **kwargs)
    return errors[0] if errors else None


def verify_metric_snapshot(snapshot: object) -> tuple[str, ...]:
    """Validate the executable invariants of Metric Snapshot v1 without defaults."""
    errors: list[str] = []
    if not isinstance(snapshot, Mapping):
        return ("METRIC_SNAPSHOT_MALFORMED",)
    if set(snapshot) != set(_SNAPSHOT_FIELDS):
        _append(errors, "METRIC_SNAPSHOT_MALFORMED")

    for field in ("metric_snapshot_id", "organization_id", "actor", "reason", "trace_id"):
        if not _is_nonempty_string(snapshot.get(field)):
            _append(errors, "METRIC_SNAPSHOT_MALFORMED")
    for field in (
        "marketplace_account_id",
        "prior_snapshot_id",
        "restates_snapshot_id",
    ):
        value = snapshot.get(field)
        if value is not None and not _is_nonempty_string(value):
            _append(errors, "METRIC_SNAPSHOT_MALFORMED")
    if not _is_positive_int(snapshot.get("snapshot_revision")):
        _append(errors, "METRIC_SNAPSHOT_VERSION_INVALID")

    mode, scenario_id = snapshot.get("mode"), snapshot.get("scenario_id")
    if mode == "ACTUAL":
        if scenario_id is not None:
            _append(errors, "METRIC_SNAPSHOT_MODE_CONTAMINATION")
    elif mode == "SCENARIO":
        if not _is_nonempty_string(scenario_id):
            _append(errors, "METRIC_SNAPSHOT_MODE_CONTAMINATION")
    else:
        _append(errors, "METRIC_SNAPSHOT_MODE_CONTAMINATION")

    for field in ("metric_definition_ref", "calculation_profile_ref", "source_authority_ref"):
        if not _valid_ref(snapshot.get(field)):
            _append(errors, "METRIC_SNAPSHOT_REFERENCE_INVALID")
    if not _valid_ref(snapshot.get("evidence_chain_ref"), chain_locator=True):
        _append(errors, "METRIC_SNAPSHOT_REFERENCE_INVALID")

    rounding = snapshot.get("rounding")
    if (
        not isinstance(rounding, Mapping)
        or set(rounding) != {"policy_ref", "application_point", "resolved_mode", "resolved_scale"}
        or not _valid_ref(rounding.get("policy_ref"))
        or not _is_allowed_string(
            rounding.get("application_point"), _ROUNDING_APPLICATION_POINTS
        )
        or not _is_allowed_string(rounding.get("resolved_mode"), _ROUNDING_MODES)
        or not _is_non_negative_int(rounding.get("resolved_scale"))
        or int(rounding.get("resolved_scale", 29)) > 28
    ):
        _append(errors, "METRIC_SNAPSHOT_ROUNDING_INVALID")

    parsed: dict[str, datetime | None] = {}
    for field in (
        "period_start", "period_end", "freshness_observed_at", "valid_from",
        "calculated_at",
    ):
        parsed[field] = _parse_datetime(snapshot.get(field))
        if parsed[field] is None:
            _append(errors, "METRIC_SNAPSHOT_TIMESTAMP_INVALID")
    for field in ("freshness_deadline", "valid_to"):
        value = snapshot.get(field)
        parsed[field] = None if value is None else _parse_datetime(value)
        if value is not None and parsed[field] is None:
            _append(errors, "METRIC_SNAPSHOT_TIMESTAMP_INVALID")
    if parsed.get("period_start") and parsed.get("period_end") and parsed["period_start"] >= parsed["period_end"]:
        _append(errors, "METRIC_SNAPSHOT_PERIOD_INVALID")
    if parsed.get("valid_from") and parsed.get("valid_to") and parsed["valid_from"] >= parsed["valid_to"]:
        _append(errors, "METRIC_SNAPSHOT_VALIDITY_INVALID")

    try:
        supplied_hash = snapshot.get("content_hash")
        if not _is_hash(supplied_hash) or supplied_hash != canonical_snapshot_hash(snapshot):
            _append(errors, "METRIC_SNAPSHOT_HASH_MISMATCH")
    except (TypeError, ValueError, OverflowError):
        _append(errors, "METRIC_SNAPSHOT_MALFORMED")

    state = snapshot.get("state")
    value = snapshot.get("value")
    value_type = snapshot.get("value_type")
    unit = snapshot.get("unit")
    currency = snapshot.get("currency")
    reason_code = snapshot.get("reason_code")
    if not _is_allowed_string(state, _STATES):
        _append(errors, "METRIC_SNAPSHOT_STATE_INVALID")
    elif state == "VALID":
        if value is None or not _is_allowed_string(value_type, _VALUE_TYPES):
            _append(errors, "METRIC_SNAPSHOT_VALUE_INVALID")
        if not _is_allowed_string(unit, _UNITS) or reason_code is not None:
            _append(errors, "METRIC_SNAPSHOT_VALUE_INVALID")
        if value_type == "MONEY":
            if not isinstance(value, str) or not _DECIMAL_RE.fullmatch(value):
                _append(errors, "METRIC_SNAPSHOT_VALUE_INVALID")
            if not _is_allowed_string(unit, _MONEY_UNITS) or not (
                isinstance(currency, str) and re.fullmatch(r"[A-Z]{3}", currency)
            ):
                _append(errors, "METRIC_SNAPSHOT_VALUE_INVALID")
        elif value_type == "INTEGER":
            if not isinstance(value, int) or isinstance(value, bool) or currency is not None:
                _append(errors, "METRIC_SNAPSHOT_VALUE_INVALID")
            if isinstance(unit, str) and unit in _MONEY_UNITS:
                _append(errors, "METRIC_SNAPSHOT_VALUE_INVALID")
        elif isinstance(value_type, str) and value_type in {"DECIMAL", "RATE"}:
            if not isinstance(value, str) or not _DECIMAL_RE.fullmatch(value) or currency is not None:
                _append(errors, "METRIC_SNAPSHOT_VALUE_INVALID")
            if isinstance(unit, str) and unit in _MONEY_UNITS:
                _append(errors, "METRIC_SNAPSHOT_VALUE_INVALID")
    else:
        if any(item is not None for item in (value, value_type, unit, currency)):
            _append(errors, "METRIC_SNAPSHOT_NON_VALID_VALUE")
        if not _is_nonempty_string(reason_code):
            _append(errors, "METRIC_SNAPSHOT_NON_VALID_VALUE")

    expenses = snapshot.get("expense_boundary")
    if (
        not isinstance(expenses, list)
        or any(not _is_allowed_string(item, _EXPENSES) for item in expenses)
        or len(set(map(str, expenses))) != len(expenses)
    ):
        _append(errors, "METRIC_SNAPSHOT_EXPENSE_BOUNDARY_INVALID")

    if not _is_allowed_string(snapshot.get("accounting_view"), _ACCOUNTING_VIEWS):
        _append(errors, "METRIC_SNAPSHOT_ACCOUNTING_VIEW_INVALID")
    if not _is_allowed_string(snapshot.get("data_freshness_state"), _FRESHNESS_STATES):
        _append(errors, "METRIC_SNAPSHOT_FRESHNESS_INVALID")
    if not _is_allowed_string(snapshot.get("confidence_state"), _CONFIDENCE_STATES):
        _append(errors, "METRIC_SNAPSHOT_CONFIDENCE_INVALID")
    for field in ("confidence_reasons", "limitations"):
        value_list = snapshot.get(field)
        if (
            not isinstance(value_list, list)
            or any(not _is_nonempty_string(item) for item in value_list)
            or len(set(map(str, value_list))) != len(value_list)
        ):
            _append(errors, "METRIC_SNAPSHOT_MALFORMED")

    return tuple(errors)


def diagnose_metric_snapshot(snapshot: object) -> str | None:
    errors = verify_metric_snapshot(snapshot)
    return errors[0] if errors else None
