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


def valid_ref(value):
    version = value.get("version")
    return (
        isinstance(version, int)
        and not isinstance(version, bool)
        and version > 0
        and bool(value.get("id"))
        and bool(H.fullmatch(str(value.get("content_hash", ""))))
    )


def canonical_graph_hash(graph):
    payload = copy.deepcopy(graph)
    payload.pop("content_hash", None)
    raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def diagnose(graph):
    rows = graph.get("nodes", [])
    nodes = {node["node_id"]: node for node in rows}
    if len(nodes) != len(rows):
        return "EVIDENCE_NODE_MISSING"
    version = graph.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        return "EVIDENCE_VERSION_INVALID"
    supplied = str(graph.get("content_hash", ""))
    if not H.fullmatch(supplied) or supplied != canonical_graph_hash(graph):
        return "EVIDENCE_HASH_MISMATCH"

    root_ref = graph.get("root_metric_snapshot_ref", {})
    if not valid_ref(root_ref):
        return (
            "EVIDENCE_VERSION_INVALID"
            if root_ref.get("version", 0) < 1
            else "EVIDENCE_HASH_MISMATCH"
        )
    roots = [
        node
        for node in nodes.values()
        if node["node_type"] == "METRIC_SNAPSHOT"
        and node["artifact_ref"] == root_ref
    ]
    if len(roots) != 1:
        return "EVIDENCE_NODE_MISSING"

    for node in nodes.values():
        ref = node.get("artifact_ref", {})
        if not valid_ref(ref):
            return (
                "EVIDENCE_VERSION_INVALID"
                if ref.get("version", 0) < 1
                else "EVIDENCE_HASH_MISMATCH"
            )
        if node.get("organization_id") != graph.get("organization_id"):
            return "EVIDENCE_TENANT_MISMATCH"
        if (
            node.get("mode") != graph.get("mode")
            or (
                graph.get("mode") == "ACTUAL"
                and node.get("scenario_id") is not None
            )
            or (
                graph.get("mode") == "SCENARIO"
                and node.get("scenario_id") != graph.get("scenario_id")
            )
        ):
            return "EVIDENCE_MODE_CONTAMINATION"

    adjacency = {node_id: [] for node_id in nodes}
    typed_targets = {}
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
            source_type
            and nodes[source]["node_type"] != source_type
            or nodes[target]["node_type"] != target_type
        ):
            return "EVIDENCE_EDGE_INVALID"
        adjacency[source].append(target)
        typed_targets.setdefault((source, edge_type), []).append(target)

    seen, active = set(), set()

    def cyclic(node_id):
        if node_id in active:
            return True
        if node_id in seen:
            return False
        active.add(node_id)
        if any(cyclic(target) for target in adjacency[node_id]):
            return True
        active.remove(node_id)
        seen.add(node_id)
        return False

    if any(cyclic(node_id) for node_id in nodes):
        return "EVIDENCE_GRAPH_CYCLE"

    root_id = roots[0]["node_id"]
    transformation_edges = [
        edge
        for edge in edges
        if edge.get("from_node_id") == root_id
        and edge.get("edge_type") == "RESULT_USES_TRANSFORMATION"
    ]
    sequence = [edge.get("sequence") for edge in transformation_edges]
    if (
        any(
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
            for value in sequence
        )
        or sorted(sequence) != list(range(len(sequence)))
    ):
        return "EVIDENCE_TRANSFORMATION_ORDER_AMBIGUOUS"

    def targets(source, edge_type, node_type):
        return [
            target
            for target in typed_targets.get((source, edge_type), [])
            if nodes[target]["node_type"] == node_type
        ]

    required = [
        ("RESULT_DEFINED_BY", "METRIC_DEFINITION"),
        ("RESULT_CALCULATED_WITH", "CALCULATION_PROFILE"),
        ("RESULT_USES_RESOLUTION", "RULE_RESOLUTION"),
        ("RESULT_USES_TRANSFORMATION", "TRANSFORMATION"),
        ("RESULT_DERIVED_FROM_EVENT", "CANONICAL_EVENT"),
        ("RESULT_HAS_FRESHNESS", "FRESHNESS_ASSESSMENT"),
        ("RESULT_HAS_CONFIDENCE", "CONFIDENCE_ASSESSMENT"),
    ]
    if any(
        not targets(root_id, edge_type, node_type)
        for edge_type, node_type in required
    ):
        return "EVIDENCE_REQUIRED_PATH_MISSING"

    def approved(artifact_id):
        for approval_id in targets(
            artifact_id, "ARTIFACT_APPROVED_BY", "APPROVAL"
        ):
            metadata = nodes[approval_id].get("metadata", {})
            if (
                metadata.get("status") == "APPROVED"
                and metadata.get("approved_at")
                and metadata.get("approver")
            ):
                return True
        return False

    for profile in targets(
        root_id, "RESULT_CALCULATED_WITH", "CALCULATION_PROFILE"
    ):
        rounding = targets(profile, "PROFILE_USES_ROUNDING", "ROUNDING_POLICY")
        authorities = targets(
            profile, "PROFILE_USES_SOURCE_AUTHORITY", "SOURCE_AUTHORITY"
        )
        if not rounding or not authorities:
            return "EVIDENCE_REQUIRED_PATH_MISSING"
        if any(not approved(node_id) for node_id in rounding + authorities):
            return "EVIDENCE_APPROVAL_MISSING"

    for resolution in targets(
        root_id, "RESULT_USES_RESOLUTION", "RULE_RESOLUTION"
    ):
        if not targets(
            resolution, "RESOLUTION_SELECTS_RULE", "CONFIGURATION_RULE"
        ):
            return "EVIDENCE_REQUIRED_PATH_MISSING"

    for event in targets(
        root_id, "RESULT_DERIVED_FROM_EVENT", "CANONICAL_EVENT"
    ):
        records = targets(
            event, "EVENT_NORMALIZED_FROM_RECORD", "SOURCE_RECORD"
        )
        if not records:
            return "EVIDENCE_REQUIRED_PATH_MISSING"
        for record in records:
            files = targets(record, "RECORD_READ_FROM_FILE", "SOURCE_FILE")
            if not files:
                return "EVIDENCE_REQUIRED_PATH_MISSING"
            for file_id in files:
                node = nodes[file_id]
                metadata = node.get("metadata", {})
                retained = str(metadata.get("retained_bytes_sha256", ""))
                if not H.fullmatch(retained) or not metadata.get(
                    "storage_locator"
                ):
                    return "EVIDENCE_SOURCE_FILE_UNAVAILABLE"
                if retained != node["artifact_ref"]["content_hash"]:
                    return "EVIDENCE_HASH_MISMATCH"
    return None


def mutate(base, mutation):
    graph = copy.deepcopy(base)
    if "remove_node" in mutation:
        node_id = mutation["remove_node"]
        graph["nodes"] = [
            node for node in graph["nodes"] if node["node_id"] != node_id
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
        edge = next(
            edge
            for edge in graph["edges"]
            if edge["from_node_id"] == expected["from_node_id"]
            and edge["to_node_id"] == expected["to_node_id"]
            and edge["edge_type"] == expected["edge_type"]
        )
        edge["edge_type"] = expected["new_edge_type"]
    if "set_edge_sequence" in mutation:
        expected = mutation["set_edge_sequence"]
        edge = next(
            edge
            for edge in graph["edges"]
            if edge["from_node_id"] == expected["from_node_id"]
            and edge["to_node_id"] == expected["to_node_id"]
            and edge["edge_type"] == expected["edge_type"]
        )
        edge["sequence"] = expected["sequence"]
    if "node_id" in mutation:
        node = next(
            node
            for node in graph["nodes"]
            if node["node_id"] == mutation["node_id"]
        )
        node.update(
            {key: value for key, value in mutation.items() if key != "node_id"}
        )
    if "root_reference_version" in mutation:
        graph["root_metric_snapshot_ref"]["version"] = mutation[
            "root_reference_version"
        ]
    if "source_file_retained_hash" in mutation:
        node = next(
            node
            for node in graph["nodes"]
            if node["node_type"] == "SOURCE_FILE"
        )
        node["metadata"]["retained_bytes_sha256"] = mutation[
            "source_file_retained_hash"
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
        for clause in branch.get("if", {}).get("allOf", []):
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
            self.assertNotIn(
                '"default"', (S / name).read_text(encoding="utf-8")
            )
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

    def test_04_units_align(self):
        expected = set(
            j(S / "metric-definition.schema.json")["properties"]["unit"]["enum"]
        )
        actual = set(
            j(S / "metric-result.schema.json")["properties"]["unit"]["enum"]
        )
        actual.discard(None)
        self.assertTrue(expected <= actual)
        self.assertIn("MONEY_PER_ITEM", actual)

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
        text = (R / "docs/evidence/METRIC_SNAPSHOT_CONTRACT.md").read_text(
            encoding="utf-8"
        )
        for phrase in [
            "Numeric zero is a valid payload of `VALID`",
            "expense boundary",
            "freshness",
            "confidence",
            "Actual and Scenario isolation",
            "MONEY_PER_ITEM",
            "cycle-breaking identity locator",
        ]:
            self.assertIn(phrase, text)

    def test_11_evidence_contract(self):
        text = (R / "docs/evidence/EVIDENCE_CHAIN_CONTRACT.md").read_text(
            encoding="utf-8"
        )
        for phrase in [
            "SOURCE_RECORD -> RECORD_READ_FROM_FILE -> SOURCE_FILE",
            "RULE_RESOLUTION -> RESOLUTION_SELECTS_RULE -> CONFIGURATION_RULE",
            "ROUNDING_POLICY -> ARTIFACT_APPROVED_BY -> APPROVAL",
            "SOURCE_AUTHORITY -> ARTIFACT_APPROVED_BY -> APPROVAL",
            "EVIDENCE_REQUIRED_PATH_MISSING",
            "EVIDENCE_APPROVAL_MISSING",
        ]:
            self.assertIn(phrase, text)

    def test_12_graph_hash_is_canonical_and_tamper_evident(self):
        graph = j(V)["valid_graph"]
        self.assertEqual(graph["content_hash"], canonical_graph_hash(graph))
        tampered = copy.deepcopy(graph)
        tampered["actor"] = "different"
        self.assertEqual(diagnose(tampered), "EVIDENCE_HASH_MISMATCH")

    def test_13_transformation_sequence_is_unique_and_contiguous(self):
        graph = j(V)["valid_graph"]
        sequence = [
            edge["sequence"]
            for edge in graph["edges"]
            if edge["edge_type"] == "RESULT_USES_TRANSFORMATION"
        ]
        self.assertEqual(sorted(sequence), list(range(len(sequence))))

    def test_14_money_currency_and_unit_binding(self):
        money = value_type_branches(j(S / "metric-result.schema.json"))["MONEY"]
        self.assertEqual(
            money["unit"]["enum"], ["MONEY", "MONEY_PER_ITEM"]
        )
        self.assertEqual(money["currency"]["pattern"], "^[A-Z]{3}$")
        self.assertEqual(
            money["value"], {"$ref": "#/$defs/decimalString"}
        )

    def test_15_value_type_payload_bindings(self):
        branches = value_type_branches(j(S / "metric-result.schema.json"))
        self.assertEqual(branches["INTEGER"]["value"], {"type": "integer"})
        self.assertEqual(branches["INTEGER"]["currency"], {"type": "null"})
        self.assertEqual(
            branches["DECIMAL"]["value"],
            {"$ref": "#/$defs/decimalString"},
        )
        self.assertEqual(
            branches["RATE"]["value"], {"$ref": "#/$defs/decimalString"}
        )

    def test_16_snapshot_evidence_hash_cycle_is_broken(self):
        metric = j(S / "metric-result.schema.json")
        evidence = j(S / "evidence-chain.schema.json")
        locator = metric["$defs"]["evidenceChainRef"]
        self.assertEqual(set(locator["required"]), {"id", "version"})
        self.assertNotIn("content_hash", locator["properties"])
        self.assertIn(
            "content_hash",
            evidence["$defs"]["versionedRef"]["required"],
        )

    def test_17_source_file_hash_matches_retained_bytes(self):
        data = j(V)
        source_file = next(
            node
            for node in data["valid_graph"]["nodes"]
            if node["node_type"] == "SOURCE_FILE"
        )
        self.assertEqual(
            source_file["artifact_ref"]["content_hash"],
            source_file["metadata"]["retained_bytes_sha256"],
        )
        mismatch = mutate(
            data["valid_graph"],
            {"source_file_retained_hash": "e" * 64},
        )
        self.assertEqual(diagnose(mismatch), "EVIDENCE_HASH_MISMATCH")

    def test_18_rounding_and_authority_require_approval(self):
        data = j(V)
        for source, target in [
            ("rounding", "approval-rounding"),
            ("authority", "approval-authority"),
        ]:
            mutation = {
                "remove_edge": {
                    "from_node_id": source,
                    "to_node_id": target,
                    "edge_type": "ARTIFACT_APPROVED_BY",
                }
            }
            self.assertEqual(
                diagnose(mutate(data["valid_graph"], mutation)),
                "EVIDENCE_APPROVAL_MISSING",
            )


if __name__ == "__main__":
    unittest.main()
