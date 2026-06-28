import copy
import hashlib
import json
import re
import unittest
from pathlib import Path

R = Path(__file__).resolve().parents[1]
S = R / "schemas"
V = R / "tests/contracts/fixtures/b3-evidence-chain-vectors.json"
H = re.compile(r"^[a-f0-9]{64}$")
SIG = {
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

def j(path):
    return json.loads(path.read_text(encoding="utf-8"))

def ref(value):
    return (
        isinstance(value.get("version"), int)
        and not isinstance(value.get("version"), bool)
        and value["version"] > 0
        and bool(H.fullmatch(str(value.get("content_hash", ""))))
        and bool(value.get("id"))
    )

def canonical_graph_hash(graph):
    payload = copy.deepcopy(graph)
    payload.pop("content_hash", None)
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

def diagnose(graph):
    nodes = {item["node_id"]: item for item in graph.get("nodes", [])}
    if len(nodes) != len(graph.get("nodes", [])):
        return "EVIDENCE_NODE_MISSING"
    if (
        not isinstance(graph.get("version"), int)
        or isinstance(graph.get("version"), bool)
        or graph["version"] < 1
    ):
        return "EVIDENCE_VERSION_INVALID"
    supplied_hash = str(graph.get("content_hash", ""))
    if not H.fullmatch(supplied_hash):
        return "EVIDENCE_HASH_MISMATCH"
    if supplied_hash != canonical_graph_hash(graph):
        return "EVIDENCE_HASH_MISMATCH"
    root_ref = graph.get("root_metric_snapshot_ref", {})
    if not ref(root_ref):
        return (
            "EVIDENCE_VERSION_INVALID"
            if root_ref.get("version", 0) < 1
            else "EVIDENCE_HASH_MISMATCH"
        )
    roots = [
        item
        for item in nodes.values()
        if item["node_type"] == "METRIC_SNAPSHOT"
        and item["artifact_ref"] == root_ref
    ]
    if len(roots) != 1:
        return "EVIDENCE_NODE_MISSING"
    for item in nodes.values():
        artifact_ref = item.get("artifact_ref", {})
        if not ref(artifact_ref):
            return (
                "EVIDENCE_VERSION_INVALID"
                if artifact_ref.get("version", 0) < 1
                else "EVIDENCE_HASH_MISMATCH"
            )
        if item.get("organization_id") != graph.get("organization_id"):
            return "EVIDENCE_TENANT_MISMATCH"
        if (
            item.get("mode") != graph.get("mode")
            or (graph.get("mode") == "ACTUAL" and item.get("scenario_id") is not None)
            or (
                graph.get("mode") == "SCENARIO"
                and item.get("scenario_id") != graph.get("scenario_id")
            )
        ):
            return "EVIDENCE_MODE_CONTAMINATION"

    adjacency = {key: [] for key in nodes}
    targets_by_type = {}
    edges = graph.get("edges", [])
    for edge in edges:
        source = edge.get("from_node_id")
        target = edge.get("to_node_id")
        edge_type = edge.get("edge_type")
        if source not in nodes or target not in nodes:
            return "EVIDENCE_NODE_MISSING"
        if edge_type not in SIG:
            return "EVIDENCE_EDGE_INVALID"
        source_type, target_type = SIG[edge_type]
        if (
            (source_type and nodes[source]["node_type"] != source_type)
            or nodes[target]["node_type"] != target_type
        ):
            return "EVIDENCE_EDGE_INVALID"
        adjacency[source].append(target)
        targets_by_type.setdefault((source, edge_type), []).append(target)

    seen = set()
    stack = set()
    def cyclic(node_id):
        if node_id in stack:
            return True
        if node_id in seen:
            return False
        stack.add(node_id)
        if any(cyclic(target) for target in adjacency[node_id]):
            return True
        stack.remove(node_id)
        seen.add(node_id)
        return False
    if any(cyclic(node_id) for node_id in nodes):
        return "EVIDENCE_GRAPH_CYCLE"

    root_id = roots[0]["node_id"]
    transformation_edges = [
        edge for edge in edges
        if edge.get("from_node_id") == root_id
        and edge.get("edge_type") == "RESULT_USES_TRANSFORMATION"
    ]
    sequences = [edge.get("sequence") for edge in transformation_edges]
    if (
        any(
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
            for value in sequences
        )
        or sorted(sequences) != list(range(len(sequences)))
    ):
        return "EVIDENCE_TRANSFORMATION_ORDER_AMBIGUOUS"

    def targets(source, edge_type, node_type):
        return [
            target
            for target in targets_by_type.get((source, edge_type), [])
            if nodes[target]["node_type"] == node_type
        ]

    basics = [
        ("RESULT_DEFINED_BY", "METRIC_DEFINITION"),
        ("RESULT_CALCULATED_WITH", "CALCULATION_PROFILE"),
        ("RESULT_USES_RESOLUTION", "RULE_RESOLUTION"),
        ("RESULT_USES_TRANSFORMATION", "TRANSFORMATION"),
        ("RESULT_DERIVED_FROM_EVENT", "CANONICAL_EVENT"),
        ("RESULT_HAS_FRESHNESS", "FRESHNESS_ASSESSMENT"),
        ("RESULT_HAS_CONFIDENCE", "CONFIDENCE_ASSESSMENT"),
    ]
    if any(not targets(root_id, edge_type, node_type) for edge_type, node_type in basics):
        return "EVIDENCE_REQUIRED_PATH_MISSING"
    for profile in targets(root_id, "RESULT_CALCULATED_WITH", "CALCULATION_PROFILE"):
        if (
            not targets(profile, "PROFILE_USES_ROUNDING", "ROUNDING_POLICY")
            or not targets(profile, "PROFILE_USES_SOURCE_AUTHORITY", "SOURCE_AUTHORITY")
        ):
            return "EVIDENCE_REQUIRED_PATH_MISSING"
    for resolution in targets(root_id, "RESULT_USES_RESOLUTION", "RULE_RESOLUTION"):
        if not targets(
            resolution, "RESOLUTION_SELECTS_RULE", "CONFIGURATION_RULE"
        ):
            return "EVIDENCE_REQUIRED_PATH_MISSING"
    for event in targets(root_id, "RESULT_DERIVED_FROM_EVENT", "CANONICAL_EVENT"):
        records = targets(event, "EVENT_NORMALIZED_FROM_RECORD", "SOURCE_RECORD")
        if not records:
            return "EVIDENCE_REQUIRED_PATH_MISSING"
        for record in records:
            files = targets(record, "RECORD_READ_FROM_FILE", "SOURCE_FILE")
            if not files:
                return "EVIDENCE_REQUIRED_PATH_MISSING"
            for source_file in files:
                metadata = nodes[source_file].get("metadata", {})
                if (
                    not H.fullmatch(str(metadata.get("retained_bytes_sha256", "")))
                    or not metadata.get("storage_locator")
                ):
                    return "EVIDENCE_SOURCE_FILE_UNAVAILABLE"
    return None

def mutate(base, mutation):
    graph = copy.deepcopy(base)
    if "remove_node" in mutation:
        node_id = mutation["remove_node"]
        graph["nodes"] = [
            item for item in graph["nodes"] if item["node_id"] != node_id
        ]
        graph["edges"] = [
            edge
            for edge in graph["edges"]
            if node_id not in (edge["from_node_id"], edge["to_node_id"])
        ]
    if "remove_edge" in mutation:
        expected = mutation["remove_edge"]
        graph["edges"] = [
            edge
            for edge in graph["edges"]
            if not all(edge.get(key) == value for key, value in expected.items())
        ]
    if "add_edge" in mutation:
        graph["edges"].append(mutation["add_edge"])
    if "replace_edge" in mutation:
        expected = mutation["replace_edge"]
        target = next(
            edge
            for edge in graph["edges"]
            if edge["from_node_id"] == expected["from_node_id"]
            and edge["to_node_id"] == expected["to_node_id"]
            and edge["edge_type"] == expected["edge_type"]
        )
        target["edge_type"] = expected["new_edge_type"]
    if "set_edge_sequence" in mutation:
        expected = mutation["set_edge_sequence"]
        target = next(
            edge
            for edge in graph["edges"]
            if edge["from_node_id"] == expected["from_node_id"]
            and edge["to_node_id"] == expected["to_node_id"]
            and edge["edge_type"] == expected["edge_type"]
        )
        target["sequence"] = expected["sequence"]
    if "node_id" in mutation:
        target = next(
            item for item in graph["nodes"] if item["node_id"] == mutation["node_id"]
        )
        target.update(
            {key: value for key, value in mutation.items() if key != "node_id"}
        )
    if "root_reference_version" in mutation:
        graph["root_metric_snapshot_ref"]["version"] = mutation[
            "root_reference_version"
        ]
    if "set_graph_field" in mutation:
        graph.update(mutation["set_graph_field"])
    if "graph_content_hash" in mutation:
        graph["content_hash"] = mutation["graph_content_hash"]
    elif not mutation.get("preserve_graph_hash", False):
        graph["content_hash"] = canonical_graph_hash(graph)
    return graph

def value_type_branches(schema):
    result = {}
    for branch in schema["allOf"]:
        condition = branch.get("if", {}).get("allOf", [])
        for clause in condition:
            value_type = (
                clause.get("properties", {})
                .get("value_type", {})
                .get("const")
            )
            if value_type:
                result[value_type] = branch["then"]["properties"]
    return result

class B3(unittest.TestCase):
    def test_01_b1a_dependencies(self):
        for path in [
            "docs/finance/CONFIGURATION_RULE_CONTRACT.md",
            "docs/finance/RULE_RESOLUTION_CONTRACT.md",
            "docs/finance/CALCULATION_PROFILE_CONTRACT.md",
            "schemas/metric-definition.schema.json",
            "schemas/calculation-profile.schema.json",
            "tests/test_b1a_financial_contracts.py",
            "docs/evidence/STAGE_B_B1A_CONTRACT_EVIDENCE.yaml",
        ]:
            self.assertTrue((R / path).is_file(), path)

    def test_02_schemas_json_no_defaults(self):
        for name in ["metric-result.schema.json", "evidence-chain.schema.json"]:
            self.assertNotIn('"default"', (S / name).read_text(encoding="utf-8"))
            self.assertEqual(
                j(S / name)["$schema"],
                "https://json-schema.org/draft/2020-12/schema",
            )

    def test_03_states_and_zero(self):
        canonical = set(
            j(S / "typed-value.schema.json")["properties"]["state"]["enum"]
        )
        metric = j(S / "metric-result.schema.json")
        self.assertEqual(set(metric["$defs"]["typedState"]["enum"]), canonical)
        self.assertNotIn("ZERO_VALID", canonical)
        valid_branch = next(
            branch for branch in metric["allOf"]
            if branch.get("if", {}).get("properties", {}).get("state", {}).get("const")
            == "VALID"
        )
        self.assertNotEqual(
            valid_branch["then"]["properties"]["value"], {"type": "null"}
        )

    def test_04_units_align(self):
        metric_units = set(
            j(S / "metric-definition.schema.json")["properties"]["unit"]["enum"]
        )
        result_units = set(
            j(S / "metric-result.schema.json")["properties"]["unit"]["enum"]
        )
        result_units.discard(None)
        self.assertTrue(metric_units <= result_units, metric_units - result_units)
        self.assertIn("MONEY_PER_ITEM", result_units)

    def test_05_positive_refs(self):
        for name in ["metric-result.schema.json", "evidence-chain.schema.json"]:
            self.assertEqual(
                j(S / name)["$defs"]["versionedRef"]["properties"]["version"],
                {"type": "integer", "minimum": 1},
            )

    def test_06_fixture_schema_shape(self):
        graph = j(V)["valid_graph"]
        schema = j(S / "evidence-chain.schema.json")
        self.assertEqual(set(graph), set(schema["required"]))
        self.assertTrue(
            all(
                set(node) == set(schema["$defs"]["node"]["required"])
                for node in graph["nodes"]
            )
        )
        self.assertTrue(
            all(
                set(edge) == set(schema["$defs"]["edge"]["required"])
                for edge in graph["edges"]
            )
        )

    def test_07_valid_graph(self):
        self.assertIsNone(diagnose(j(V)["valid_graph"]))

    def test_08_invalid_vectors(self):
        data = j(V)
        for vector in data["invalid_vectors"]:
            self.assertEqual(
                diagnose(mutate(data["valid_graph"], vector["mutation"])),
                vector["expected_diagnostic"],
                vector["id"],
            )

    def test_09_mode_isolation(self):
        for name in ["metric-result.schema.json", "evidence-chain.schema.json"]:
            encoded = json.dumps(j(S / name))
            self.assertIn("ACTUAL", encoded)
            self.assertIn("SCENARIO", encoded)
            self.assertIn("scenario_id", encoded)

    def test_10_metric_contract(self):
        content = (R / "docs/evidence/METRIC_SNAPSHOT_CONTRACT.md").read_text(
            encoding="utf-8"
        )
        for phrase in [
            "Numeric zero is a valid payload of `VALID`",
            "expense boundary",
            "freshness",
            "confidence",
            "prior snapshot identifier",
            "Actual and Scenario isolation",
            "Aliases such as `latest`",
            "MONEY_PER_ITEM",
        ]:
            self.assertIn(phrase, content)

    def test_11_evidence_contract(self):
        content = (R / "docs/evidence/EVIDENCE_CHAIN_CONTRACT.md").read_text(
            encoding="utf-8"
        )
        for phrase in [
            "SOURCE_RECORD -> RECORD_READ_FROM_FILE -> SOURCE_FILE",
            "RULE_RESOLUTION -> RESOLUTION_SELECTS_RULE -> CONFIGURATION_RULE",
            "Merely making each required node type reachable",
            "Every node has a stable ID",
            "The calculation subgraph must be acyclic",
            "EVIDENCE_REQUIRED_PATH_MISSING",
            "EVIDENCE_REPRODUCTION_FAILED",
        ]:
            self.assertIn(phrase, content)

    def test_12_graph_hash_is_canonical_and_tamper_evident(self):
        graph = j(V)["valid_graph"]
        self.assertEqual(graph["content_hash"], canonical_graph_hash(graph))
        tampered = copy.deepcopy(graph)
        tampered["actor"] = "different-actor"
        self.assertEqual(diagnose(tampered), "EVIDENCE_HASH_MISMATCH")

    def test_13_transformation_sequence_is_unique_and_contiguous(self):
        graph = j(V)["valid_graph"]
        root = graph["root_metric_snapshot_ref"]["id"]
        sequences = [
            edge["sequence"]
            for edge in graph["edges"]
            if edge["from_node_id"] == root
            and edge["edge_type"] == "RESULT_USES_TRANSFORMATION"
        ]
        self.assertEqual(sorted(sequences), list(range(len(sequences))))
        ambiguous = mutate(
            graph,
            {
                "set_edge_sequence": {
                    "from_node_id": root,
                    "to_node_id": "transformation-2",
                    "edge_type": "RESULT_USES_TRANSFORMATION",
                    "sequence": 0,
                }
            },
        )
        self.assertEqual(
            diagnose(ambiguous),
            "EVIDENCE_TRANSFORMATION_ORDER_AMBIGUOUS",
        )

    def test_14_money_currency_and_unit_binding(self):
        schema = j(S / "metric-result.schema.json")
        money = value_type_branches(schema)["MONEY"]
        self.assertEqual(money["unit"]["enum"], ["MONEY", "MONEY_PER_ITEM"])
        self.assertEqual(money["currency"]["type"], "string")
        self.assertEqual(money["currency"]["pattern"], "^[A-Z]{3}$")
        self.assertEqual(money["value"], {"$ref": "#/$defs/decimalString"})

    def test_15_value_type_payload_bindings(self):
        branches = value_type_branches(j(S / "metric-result.schema.json"))
        self.assertEqual(branches["INTEGER"]["value"], {"type": "integer"})
        self.assertEqual(branches["INTEGER"]["currency"], {"type": "null"})
        self.assertEqual(
            branches["INTEGER"]["unit"],
            {"not": {"enum": ["MONEY", "MONEY_PER_ITEM"]}},
        )
        self.assertEqual(
            branches["DECIMAL"]["value"], {"$ref": "#/$defs/decimalString"}
        )
        self.assertEqual(
            branches["DECIMAL"]["unit"],
            {"not": {"enum": ["MONEY", "MONEY_PER_ITEM"]}},
        )
        self.assertEqual(
            branches["RATE"]["value"], {"$ref": "#/$defs/decimalString"}
        )
        self.assertEqual(
            branches["RATE"]["unit"],
            {"not": {"enum": ["MONEY", "MONEY_PER_ITEM"]}},
        )
        self.assertEqual(branches["RATE"]["currency"], {"type": "null"})

if __name__ == "__main__":
    unittest.main()
