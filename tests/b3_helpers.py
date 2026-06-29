from __future__ import annotations

import copy
import json
from pathlib import Path

from quantum.evidence import canonical_graph_hash, canonical_snapshot_hash

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"
VECTORS = ROOT / "tests/contracts/fixtures/b3-evidence-chain-vectors.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def graph_data():
    return load_json(VECTORS)


def mutate(base, mutation):
    graph = copy.deepcopy(base)
    if "remove_node" in mutation:
        node_id = mutation["remove_node"]
        graph["nodes"] = [node for node in graph["nodes"] if node["node_id"] != node_id]
        graph["edges"] = [
            edge for edge in graph["edges"]
            if node_id not in (edge["from_node_id"], edge["to_node_id"])
        ]
    if "remove_edge" in mutation:
        expected = mutation["remove_edge"]
        graph["edges"] = [
            edge for edge in graph["edges"]
            if not all(edge.get(key) == value for key, value in expected.items())
        ]
    if "add_edge" in mutation:
        graph["edges"].append(mutation["add_edge"])
    if "replace_edge" in mutation:
        expected = mutation["replace_edge"]
        edge = next(
            edge for edge in graph["edges"]
            if edge["from_node_id"] == expected["from_node_id"]
            and edge["to_node_id"] == expected["to_node_id"]
            and edge["edge_type"] == expected["edge_type"]
        )
        edge["edge_type"] = expected["new_edge_type"]
    if "set_edge_sequence" in mutation:
        expected = mutation["set_edge_sequence"]
        edge = next(
            edge for edge in graph["edges"]
            if edge["from_node_id"] == expected["from_node_id"]
            and edge["to_node_id"] == expected["to_node_id"]
            and edge["edge_type"] == expected["edge_type"]
        )
        edge["sequence"] = expected["sequence"]
    if "node_id" in mutation:
        node = next(node for node in graph["nodes"] if node["node_id"] == mutation["node_id"])
        node.update({key: value for key, value in mutation.items() if key != "node_id"})
    if "root_reference_version" in mutation:
        graph["root_metric_snapshot_ref"]["version"] = mutation["root_reference_version"]
    if "source_file_retained_hash" in mutation:
        node = next(node for node in graph["nodes"] if node["node_type"] == "SOURCE_FILE")
        node["metadata"]["retained_bytes_sha256"] = mutation["source_file_retained_hash"]
    if "set_graph_field" in mutation:
        graph.update(mutation["set_graph_field"])
    if "graph_content_hash" in mutation:
        graph["content_hash"] = mutation["graph_content_hash"]
    elif not mutation.get("preserve_graph_hash", False):
        graph["content_hash"] = canonical_graph_hash(graph)
    return graph


def valid_snapshot():
    snapshot = {
        "metric_snapshot_id": "metric-result",
        "snapshot_revision": 1,
        "organization_id": "org-synthetic",
        "marketplace_account_id": "wb-account-1",
        "mode": "ACTUAL",
        "scenario_id": None,
        "metric_definition_ref": {"id": "metric-definition", "version": 1, "content_hash": "2" * 64},
        "calculation_profile_ref": {"id": "profile", "version": 1, "content_hash": "3" * 64},
        "accounting_view": "SETTLEMENT",
        "period_start": "2026-06-01T00:00:00Z",
        "period_end": "2026-07-01T00:00:00Z",
        "state": "VALID",
        "value": "0",
        "value_type": "MONEY",
        "unit": "MONEY_PER_ITEM",
        "currency": "RUB",
        "reason_code": None,
        "expense_boundary": ["MARKETPLACE_COMMISSION", "PRODUCT_COST", "TAX"],
        "rounding": {
            "policy_ref": {"id": "rounding", "version": 1, "content_hash": "6" * 64},
            "application_point": "METRIC_FINAL_ACCOUNTING",
            "resolved_mode": "HALF_EVEN",
            "resolved_scale": 2,
        },
        "source_authority_ref": {"id": "authority", "version": 1, "content_hash": "7" * 64},
        "evidence_chain_ref": {"id": "evidence-chain-synthetic-1", "version": 1},
        "data_freshness_state": "CURRENT",
        "freshness_observed_at": "2026-06-28T09:00:00Z",
        "freshness_deadline": "2026-06-29T09:00:00Z",
        "confidence_state": "HIGH",
        "confidence_reasons": ["all required source paths present"],
        "limitations": ["synthetic fixture"],
        "valid_from": "2026-06-28T09:00:00Z",
        "valid_to": None,
        "prior_snapshot_id": None,
        "restates_snapshot_id": None,
        "actor": "b3-contract-test",
        "reason": "synthetic contract verification",
        "trace_id": "trace-b3-1",
        "calculated_at": "2026-06-28T09:00:00Z",
        "content_hash": "",
    }
    snapshot["content_hash"] = canonical_snapshot_hash(snapshot)
    return snapshot
