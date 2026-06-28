from __future__ import annotations

import copy
import unittest
from pathlib import Path

from quantum.evidence import EDGE_SIGNATURES, canonical_graph_hash, verify_evidence_chain
from tests.b3_helpers import ROOT, SCHEMAS, graph_data, load_json


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
        graph = copy.deepcopy(graph_data()["valid_graph"])
        approval = next(
            node for node in graph["nodes"]
            if node["node_id"] == "approval-rounding"
        )
        approval["metadata"]["approved_at"] = "2026-06-28T08:00:00"
        graph["content_hash"] = canonical_graph_hash(graph)
        self.assertIn("EVIDENCE_APPROVAL_MISSING", verify_evidence_chain(graph))

    def test_07_edge_signatures_are_typed(self):
        self.assertEqual(
            EDGE_SIGNATURES["RECORD_READ_FROM_FILE"],
            ("SOURCE_RECORD", "SOURCE_FILE"),
        )
        self.assertEqual(
            EDGE_SIGNATURES["RESOLUTION_SELECTS_RULE"],
            ("RULE_RESOLUTION", "CONFIGURATION_RULE"),
        )

        graph = copy.deepcopy(graph_data()["valid_graph"])
        unrelated_rule = copy.deepcopy(
            next(node for node in graph["nodes"] if node["node_id"] == "rule")
        )
        unrelated_rule["node_id"] = "rule-unrelated"
        unrelated_rule["artifact_ref"] = {
            "id": "rule-unrelated",
            "version": 1,
            "content_hash": "f" * 64,
        }
        graph["nodes"].append(unrelated_rule)
        profile_edge = next(
            edge for edge in graph["edges"]
            if edge["from_node_id"] == "profile"
            and edge["edge_type"] == "PROFILE_SELECTS_RULE"
        )
        profile_edge["to_node_id"] = "rule-unrelated"
        graph["content_hash"] = canonical_graph_hash(graph)
        self.assertIn(
            "EVIDENCE_REQUIRED_PATH_MISSING",
            verify_evidence_chain(graph),
        )


if __name__ == "__main__":
    unittest.main()
