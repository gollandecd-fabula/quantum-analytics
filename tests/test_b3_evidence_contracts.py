from __future__ import annotations

import copy
import json
import unittest
from collections import deque
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"
VECTORS = ROOT / "tests" / "contracts" / "fixtures" / "b3-evidence-chain-vectors.json"

REQUIRED_TYPES = {
    "METRIC_DEFINITION",
    "CALCULATION_PROFILE",
    "RULE_RESOLUTION",
    "CONFIGURATION_RULE",
    "ROUNDING_POLICY",
    "SOURCE_AUTHORITY",
    "TRANSFORMATION",
    "CANONICAL_EVENT",
    "SOURCE_RECORD",
    "SOURCE_FILE",
    "FRESHNESS_ASSESSMENT",
    "CONFIDENCE_ASSESSMENT",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def diagnose_graph(graph: dict[str, Any]) -> str | None:
    nodes = graph["nodes"]
    node_map = {node["node_id"]: node for node in nodes}
    if len(node_map) != len(nodes) or graph["root_node_id"] not in node_map:
        return "EVIDENCE_NODE_MISSING"

    for node in nodes:
        if node["organization_id"] != graph["organization_id"]:
            return "EVIDENCE_TENANT_MISMATCH"
        if node["mode"] != graph["mode"]:
            return "EVIDENCE_MODE_CONTAMINATION"
        if graph["mode"] == "ACTUAL" and node.get("scenario_id") is not None:
            return "EVIDENCE_MODE_CONTAMINATION"
        if graph["mode"] == "SCENARIO" and node.get("scenario_id") != graph.get("scenario_id"):
            return "EVIDENCE_MODE_CONTAMINATION"

    adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_map}
    for edge in graph["edges"]:
        if edge["from"] not in node_map or edge["to"] not in node_map:
            return "EVIDENCE_NODE_MISSING"
        adjacency[edge["from"]].append(edge["to"])

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> bool:
        if node_id in visiting:
            return True
        if node_id in visited:
            return False
        visiting.add(node_id)
        if any(visit(child) for child in adjacency[node_id]):
            return True
        visiting.remove(node_id)
        visited.add(node_id)
        return False

    if any(visit(node_id) for node_id in adjacency):
        return "EVIDENCE_GRAPH_CYCLE"

    reachable: set[str] = set()
    queue = deque([graph["root_node_id"]])
    while queue:
        node_id = queue.popleft()
        if node_id in reachable:
            continue
        reachable.add(node_id)
        queue.extend(adjacency[node_id])

    reachable_types = {node_map[node_id]["node_type"] for node_id in reachable}
    if not REQUIRED_TYPES.issubset(reachable_types):
        return "EVIDENCE_REQUIRED_PATH_MISSING"
    return None


def apply_mutation(base: dict[str, Any], mutation: dict[str, Any]) -> dict[str, Any]:
    graph = copy.deepcopy(base)
    if "remove_node" in mutation:
        graph["nodes"] = [node for node in graph["nodes"] if node["node_id"] != mutation["remove_node"]]
        graph["edges"] = [edge for edge in graph["edges"] if edge["from"] != mutation["remove_node"] and edge["to"] != mutation["remove_node"]]
    if "edge" in mutation:
        graph["edges"].append(mutation["edge"])
    if "node_id" in mutation:
        node = next(item for item in graph["nodes"] if item["node_id"] == mutation["node_id"])
        for key, value in mutation.items():
            if key != "node_id":
                node[key] = value
    return graph


class B3EvidenceContractTests(unittest.TestCase):
    def test_b1a_dependencies_exist_in_branch_baseline(self) -> None:
        required = (
            "docs/finance/CONFIGURATION_RULE_CONTRACT.md",
            "docs/finance/RULE_RESOLUTION_CONTRACT.md",
            "docs/finance/CALCULATION_PROFILE_CONTRACT.md",
            "schemas/metric-definition.schema.json",
            "schemas/calculation-profile.schema.json",
            "tests/test_b1a_financial_contracts.py",
            "docs/evidence/STAGE_B_B1A_CONTRACT_EVIDENCE.yaml",
        )
        for relative in required:
            with self.subTest(path=relative):
                self.assertTrue((ROOT / relative).is_file(), relative)

    def test_b3_schemas_are_json_without_defaults(self) -> None:
        for name in ("metric-result.schema.json", "evidence-chain.schema.json"):
            with self.subTest(schema=name):
                text = (SCHEMAS / name).read_text(encoding="utf-8")
                document = json.loads(text)
                self.assertEqual(document["$schema"], "https://json-schema.org/draft/2020-12/schema")
                self.assertNotIn('"default"', text)

    def test_metric_result_states_match_canonical_typed_value_contract(self) -> None:
        canonical = load_json(SCHEMAS / "typed-value.schema.json")["properties"]["state"]["enum"]
        metric = load_json(SCHEMAS / "metric-result.schema.json")
        self.assertEqual(set(metric["$defs"]["typedState"]["enum"]), set(canonical))
        self.assertNotIn("ZERO_VALID", metric["$defs"]["typedState"]["enum"])
        valid_branch = metric["allOf"][2]["then"]["properties"]
        self.assertNotEqual(valid_branch["value"], {"type": "null"})

    def test_all_b3_versioned_references_require_positive_integer_versions(self) -> None:
        for name in ("metric-result.schema.json", "evidence-chain.schema.json"):
            with self.subTest(schema=name):
                version = load_json(SCHEMAS / name)["$defs"]["versionedRef"]["properties"]["version"]
                self.assertEqual(version, {"type": "integer", "minimum": 1})

    def test_valid_evidence_graph_has_complete_required_paths(self) -> None:
        graph = load_json(VECTORS)["valid_graph"]
        self.assertIsNone(diagnose_graph(graph))

    def test_invalid_graph_vectors_fail_closed(self) -> None:
        document = load_json(VECTORS)
        for vector in document["invalid_vectors"]:
            with self.subTest(vector=vector["id"]):
                mutation = vector["mutation"]
                if "reference_version" in mutation:
                    diagnostic = "EVIDENCE_VERSION_INVALID" if mutation["reference_version"] < 1 else None
                elif "content_hash" in mutation:
                    diagnostic = "EVIDENCE_HASH_MISMATCH" if len(mutation["content_hash"]) != 64 else None
                else:
                    diagnostic = diagnose_graph(apply_mutation(document["valid_graph"], mutation))
                self.assertEqual(diagnostic, vector["expected_diagnostic"])

    def test_actual_scenario_isolation_is_encoded_in_both_schemas(self) -> None:
        for name in ("metric-result.schema.json", "evidence-chain.schema.json"):
            with self.subTest(schema=name):
                text = json.dumps(load_json(SCHEMAS / name), sort_keys=True)
                self.assertIn('"ACTUAL"', text)
                self.assertIn('"SCENARIO"', text)
                self.assertIn('"scenario_id"', text)

    def test_metric_snapshot_contract_declares_reproducibility_metadata(self) -> None:
        contract = (ROOT / "docs/evidence/METRIC_SNAPSHOT_CONTRACT.md").read_text(encoding="utf-8")
        for phrase in (
            "Numeric zero is a valid payload of `VALID`",
            "expense boundary",
            "freshness",
            "confidence",
            "prior snapshot identifier",
            "Actual and Scenario isolation",
            "Aliases such as `latest`",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, contract)

    def test_evidence_contract_requires_source_file_sha_and_fail_closed_behavior(self) -> None:
        contract = (ROOT / "docs/evidence/EVIDENCE_CHAIN_CONTRACT.md").read_text(encoding="utf-8")
        for phrase in (
            "source files and their SHA-256",
            "Every node must have the same `organization_id`",
            "The calculation subgraph must be acyclic",
            "EVIDENCE_REQUIRED_PATH_MISSING",
            "EVIDENCE_REPRODUCTION_FAILED",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, contract)


if __name__ == "__main__":
    unittest.main()
