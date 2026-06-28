from __future__ import annotations

import copy
import unittest

from quantum.evidence import canonical_graph_hash, diagnose_evidence_chain, verify_evidence_chain
from tests.b3_helpers import graph_data, mutate


class B3EvidenceContracts(unittest.TestCase):
    def test_01_valid_graph(self):
        self.assertEqual(verify_evidence_chain(graph_data()["valid_graph"]), ())

    def test_02_invalid_vectors(self):
        data = graph_data()
        for vector in data["invalid_vectors"]:
            self.assertEqual(
                diagnose_evidence_chain(mutate(data["valid_graph"], vector["mutation"])),
                vector["expected_diagnostic"],
                vector["id"],
            )

        missing_profile_rule = mutate(
            data["valid_graph"],
            {
                "remove_edge": {
                    "from_node_id": "profile",
                    "to_node_id": "rule",
                    "edge_type": "PROFILE_SELECTS_RULE",
                }
            },
        )
        self.assertEqual(
            diagnose_evidence_chain(missing_profile_rule),
            "EVIDENCE_REQUIRED_PATH_MISSING",
        )

    def test_03_required_source_bytes(self):
        data = graph_data()
        graph = data["valid_graph"]
        self.assertIn("EVIDENCE_SOURCE_FILE_UNAVAILABLE", verify_evidence_chain(
            graph, require_source_bytes=True
        ))
        payload = data["source_payload_utf8"].encode("utf-8")
        loader = lambda locator: payload if locator == "object://synthetic/source.csv" else b""
        self.assertEqual(verify_evidence_chain(
            graph, source_loader=loader, require_source_bytes=True
        ), ())

    def test_04_wrong_source_bytes(self):
        self.assertIn(
            "EVIDENCE_SOURCE_BYTES_MISMATCH",
            verify_evidence_chain(
                graph_data()["valid_graph"], source_loader=lambda _: b"changed-bytes"
            ),
        )

    def test_05_malformed_top_level(self):
        self.assertEqual(verify_evidence_chain(None), ("EVIDENCE_MALFORMED",))
        self.assertIn("EVIDENCE_MALFORMED", verify_evidence_chain({"nodes": []}))

    def test_06_missing_node_id(self):
        graph = copy.deepcopy(graph_data()["valid_graph"])
        graph["nodes"][0].pop("node_id")
        graph["content_hash"] = canonical_graph_hash(graph)
        self.assertIn("EVIDENCE_MALFORMED", verify_evidence_chain(graph))

    def test_07_duplicate_node(self):
        graph = copy.deepcopy(graph_data()["valid_graph"])
        graph["nodes"].append(copy.deepcopy(graph["nodes"][0]))
        graph["content_hash"] = canonical_graph_hash(graph)
        self.assertIn("EVIDENCE_NODE_DUPLICATE", verify_evidence_chain(graph))

    def test_08_duplicate_edge(self):
        graph = copy.deepcopy(graph_data()["valid_graph"])
        graph["edges"].append(copy.deepcopy(graph["edges"][0]))
        graph["content_hash"] = canonical_graph_hash(graph)
        self.assertIn("EVIDENCE_EDGE_DUPLICATE", verify_evidence_chain(graph))

    def test_09_orphan_node_and_deep_path(self):
        graph = copy.deepcopy(graph_data()["valid_graph"])
        orphan = copy.deepcopy(graph["nodes"][1])
        orphan["node_id"] = "orphan-definition"
        orphan["artifact_ref"]["id"] = "orphan-definition"
        graph["nodes"].append(orphan)
        graph["content_hash"] = canonical_graph_hash(graph)
        self.assertIn("EVIDENCE_ORPHAN_NODE", verify_evidence_chain(graph))

        deep = copy.deepcopy(graph_data()["valid_graph"])
        template = next(
            node for node in deep["nodes"]
            if node["node_type"] == "METRIC_SNAPSHOT"
        )
        previous = template["node_id"]
        for index in range(1100):
            node = copy.deepcopy(template)
            node_id = f"history-{index}"
            node["node_id"] = node_id
            node["artifact_ref"] = {
                "id": node_id,
                "version": 1,
                "content_hash": f"{index + 1:064x}",
            }
            deep["nodes"].append(node)
            deep["edges"].append({
                "from_node_id": previous,
                "to_node_id": node_id,
                "edge_type": "SNAPSHOT_SUPERSEDES",
                "sequence": 0,
            })
            previous = node_id
        deep["content_hash"] = canonical_graph_hash(deep)
        self.assertIn("EVIDENCE_MALFORMED", verify_evidence_chain(deep))

    def test_10_naive_created_at(self):
        graph = copy.deepcopy(graph_data()["valid_graph"])
        graph["created_at"] = "2026-06-28T09:00:00"
        graph["content_hash"] = canonical_graph_hash(graph)
        self.assertIn("EVIDENCE_TIMESTAMP_INVALID", verify_evidence_chain(graph))


if __name__ == "__main__":
    unittest.main()
