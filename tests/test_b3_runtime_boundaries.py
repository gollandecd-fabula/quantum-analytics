from __future__ import annotations

import copy
import unittest
from pathlib import Path

from quantum.evidence import (
    EDGE_SIGNATURES,
    canonical_graph_hash,
    canonical_snapshot_hash,
    verify_evidence_chain,
    verify_metric_snapshot,
)
from tests.b3_helpers import ROOT, SCHEMAS, graph_data, load_json, valid_snapshot


class B3RuntimeBoundaries(unittest.TestCase):
    def test_01_b1a_dependencies(self):
        required = (
            "docs/finance/CONFIGURATION_RULE_CONTRACT.md",
            "docs/finance/RULE_RESOLUTION_CONTRACT.md",
            "docs/finance/CALCULATION_PROFILE_CONTRACT.md",
            "schemas/metric-definition.schema.json",
            "schemas/calculation-profile.schema.json",
            "tests/test_b1a_financial_contracts.py",
            "docs/evidence/STAGE_B_B1A_CONTRACT_EVIDENCE.yaml",
        )
        for relative_path in required:
            self.assertTrue((ROOT / relative_path).is_file(), relative_path)

    def test_02_schema_declarations(self):
        for name in ("metric-result.schema.json", "evidence-chain.schema.json"):
            text = (SCHEMAS / name).read_text(encoding="utf-8")
            self.assertNotIn('"default"', text)
            self.assertEqual(
                load_json(SCHEMAS / name)["$schema"],
                "https://json-schema.org/draft/2020-12/schema",
            )

        metric_schema = load_json(SCHEMAS / "metric-result.schema.json")
        chain_ref = metric_schema["$defs"]["evidenceChainRef"]
        self.assertEqual(chain_ref["required"], ["id", "version"])
        self.assertNotIn("content_hash", chain_ref["properties"])
        self.assertFalse(chain_ref["additionalProperties"])

        contract = (
            ROOT / "docs/evidence/METRIC_SNAPSHOT_CONTRACT.md"
        ).read_text(encoding="utf-8")
        self.assertIn("cycle-breaking identity locator", contract)
        self.assertIn("create and hash the Metric Snapshot", contract)
        self.assertIn("create the Evidence Chain", contract)

    def test_03_runtime_location(self):
        import quantum.evidence as public
        import quantum.evidence.runtime_validation as runtime

        self.assertTrue(callable(runtime.verify_evidence_chain))
        self.assertIs(public.verify_evidence_chain, runtime.verify_evidence_chain)
        self.assertIs(public.verify_metric_snapshot, runtime.verify_metric_snapshot)
        self.assertIn("src/quantum/evidence", Path(runtime.__file__).as_posix())

        runtime_path = "src/quantum/evidence/runtime_validation.py"
        evidence = (
            ROOT / "docs/evidence/STAGE_B_B3_CONTRACT_EVIDENCE.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn(f"runtime_verifier_location: {runtime_path}", evidence)
        self.assertIn(f"    - {runtime_path}", evidence)
        self.assertIn(
            "branch: build-b3-metric-evidence-contracts-v4",
            evidence,
        )

        for relative_path in (
            "docs/evidence/STAGE_B_B3_EXECUTION_STATE.yaml",
            "docs/evidence/STAGE_B_EXECUTION_STATE.yaml",
        ):
            state = (ROOT / relative_path).read_text(encoding="utf-8")
            self.assertIn(f"runtime_verifier: {runtime_path}", state)
            self.assertIn(
                "working_branch: build-b3-metric-evidence-contracts-v4",
                state,
            )

    def test_04_non_mapping_reference(self):
        graph = copy.deepcopy(graph_data()["valid_graph"])
        graph["root_metric_snapshot_ref"] = 7
        graph["content_hash"] = canonical_graph_hash(graph)
        self.assertIn("EVIDENCE_HASH_MISMATCH", verify_evidence_chain(graph))

    def test_05_string_version(self):
        graph = copy.deepcopy(graph_data()["valid_graph"])
        graph["version"] = "1"
        graph["content_hash"] = canonical_graph_hash(graph)
        self.assertIn("EVIDENCE_VERSION_INVALID", verify_evidence_chain(graph))

    def test_06_approval_timezone(self):
        for approved_at in (
            "2026-06-28T08:00:00",
            "2026-06-28 08:00:00+00:00",
        ):
            graph = copy.deepcopy(graph_data()["valid_graph"])
            approval = next(
                node for node in graph["nodes"]
                if node["node_id"] == "approval-rounding"
            )
            approval["metadata"]["approved_at"] = approved_at
            graph["content_hash"] = canonical_graph_hash(graph)
            self.assertIn(
                "EVIDENCE_APPROVAL_MISSING",
                verify_evidence_chain(graph),
            )

        graph = copy.deepcopy(graph_data()["valid_graph"])
        graph["created_at"] = "2026-06-28 09:00:00+00:00"
        graph["content_hash"] = canonical_graph_hash(graph)
        self.assertIn(
            "EVIDENCE_TIMESTAMP_INVALID",
            verify_evidence_chain(graph),
        )

        snapshot = valid_snapshot()
        snapshot["period_start"] = "2026-06-01 00:00:00+00:00"
        snapshot["content_hash"] = canonical_snapshot_hash(snapshot)
        self.assertIn(
            "METRIC_SNAPSHOT_TIMESTAMP_INVALID",
            verify_metric_snapshot(snapshot),
        )

    def test_07_edge_signatures_are_typed(self):
        self.assertEqual(
            EDGE_SIGNATURES["RECORD_READ_FROM_FILE"],
            ("SOURCE_RECORD", "SOURCE_FILE"),
        )
        self.assertEqual(
            EDGE_SIGNATURES["RESOLUTION_SELECTS_RULE"],
            ("RULE_RESOLUTION", "CONFIGURATION_RULE"),
        )

        def clone_node(graph, source_id, new_id, hash_char):
            source = next(
                node for node in graph["nodes"] if node["node_id"] == source_id
            )
            cloned = copy.deepcopy(source)
            cloned["node_id"] = new_id
            cloned["artifact_ref"] = {
                "id": new_id,
                "version": 1,
                "content_hash": hash_char * 64,
            }
            graph["nodes"].append(cloned)

        def assert_required_path_rejected(graph):
            graph["content_hash"] = canonical_graph_hash(graph)
            self.assertIn(
                "EVIDENCE_REQUIRED_PATH_MISSING",
                verify_evidence_chain(graph),
            )

        graph = copy.deepcopy(graph_data()["valid_graph"])
        clone_node(graph, "rule", "rule-unrelated", "f")
        profile_edge = next(
            edge for edge in graph["edges"]
            if edge["from_node_id"] == "profile"
            and edge["edge_type"] == "PROFILE_SELECTS_RULE"
        )
        profile_edge["to_node_id"] = "rule-unrelated"
        assert_required_path_rejected(graph)

        singular_root_cases = (
            ("metric-definition", "metric-definition-extra", "RESULT_DEFINED_BY"),
            ("freshness", "freshness-extra", "RESULT_HAS_FRESHNESS"),
            ("confidence", "confidence-extra", "RESULT_HAS_CONFIDENCE"),
        )
        for source_id, new_id, edge_type in singular_root_cases:
            with self.subTest(edge_type=edge_type):
                graph = copy.deepcopy(graph_data()["valid_graph"])
                clone_node(graph, source_id, new_id, "e")
                graph["edges"].append({
                    "from_node_id": "metric-result",
                    "to_node_id": new_id,
                    "edge_type": edge_type,
                    "sequence": 1,
                })
                assert_required_path_rejected(graph)

        graph = copy.deepcopy(graph_data()["valid_graph"])
        clone_node(graph, "profile", "profile-extra", "e")
        graph["edges"].extend([
            {
                "from_node_id": "metric-result",
                "to_node_id": "profile-extra",
                "edge_type": "RESULT_CALCULATED_WITH",
                "sequence": 1,
            },
            {
                "from_node_id": "profile-extra",
                "to_node_id": "rule",
                "edge_type": "PROFILE_SELECTS_RULE",
                "sequence": 0,
            },
            {
                "from_node_id": "profile-extra",
                "to_node_id": "rounding",
                "edge_type": "PROFILE_USES_ROUNDING",
                "sequence": 0,
            },
            {
                "from_node_id": "profile-extra",
                "to_node_id": "authority",
                "edge_type": "PROFILE_USES_SOURCE_AUTHORITY",
                "sequence": 0,
            },
        ])
        assert_required_path_rejected(graph)

        graph = copy.deepcopy(graph_data()["valid_graph"])
        clone_node(graph, "rule", "rule-extra", "e")
        graph["edges"].extend([
            {
                "from_node_id": "resolution",
                "to_node_id": "rule-extra",
                "edge_type": "RESOLUTION_SELECTS_RULE",
                "sequence": 1,
            },
            {
                "from_node_id": "profile",
                "to_node_id": "rule-extra",
                "edge_type": "PROFILE_SELECTS_RULE",
                "sequence": 1,
            },
        ])
        assert_required_path_rejected(graph)

        graph = copy.deepcopy(graph_data()["valid_graph"])
        clone_node(graph, "resolution", "resolution-extra", "e")
        clone_node(graph, "rule", "rule-unprofiled", "f")
        graph["edges"].extend([
            {
                "from_node_id": "metric-result",
                "to_node_id": "resolution-extra",
                "edge_type": "RESULT_USES_RESOLUTION",
                "sequence": 1,
            },
            {
                "from_node_id": "resolution-extra",
                "to_node_id": "rule-unprofiled",
                "edge_type": "RESOLUTION_SELECTS_RULE",
                "sequence": 0,
            },
        ])
        assert_required_path_rejected(graph)

        profile_singleton_cases = (
            (
                "rounding",
                "rounding-extra",
                "PROFILE_USES_ROUNDING",
                "approval-rounding",
            ),
            (
                "authority",
                "authority-extra",
                "PROFILE_USES_SOURCE_AUTHORITY",
                "approval-authority",
            ),
        )
        for source_id, new_id, edge_type, approval_id in profile_singleton_cases:
            with self.subTest(edge_type=edge_type):
                graph = copy.deepcopy(graph_data()["valid_graph"])
                clone_node(graph, source_id, new_id, "e")
                graph["edges"].extend([
                    {
                        "from_node_id": "profile",
                        "to_node_id": new_id,
                        "edge_type": edge_type,
                        "sequence": 1,
                    },
                    {
                        "from_node_id": new_id,
                        "to_node_id": approval_id,
                        "edge_type": "ARTIFACT_APPROVED_BY",
                        "sequence": 0,
                    },
                ])
                assert_required_path_rejected(graph)


if __name__ == "__main__":
    unittest.main()
