from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from quantum.evidence.metric_result import verify_document_hashes


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "metric-result.schema.json"
COMMON_SCHEMA_PATH = ROOT / "schemas" / "metric-result-common.schema.json"
EVIDENCE_SCHEMA_PATH = ROOT / "schemas" / "metric-result-evidence.schema.json"
CONTRACT_PATH = ROOT / "docs" / "data" / "METRIC_RESULT_EVIDENCE_CHAIN_CONTRACT.md"
FIXTURE_DIR = ROOT / "tests" / "contracts" / "fixtures"


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


class B3MetricResultContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.common_schema = json.loads(COMMON_SCHEMA_PATH.read_text(encoding="utf-8"))
        self.evidence_schema = json.loads(EVIDENCE_SCHEMA_PATH.read_text(encoding="utf-8"))
        self.contract = CONTRACT_PATH.read_text(encoding="utf-8")

    def test_schema_has_closed_immutable_snapshot_shape(self) -> None:
        self.assertFalse(self.schema["additionalProperties"])
        required = set(self.schema["required"])
        self.assertTrue(
            {
                "result_id",
                "organization_id",
                "mode",
                "calculation_profile_ref",
                "metric_definition_ref",
                "value",
                "evidence_chain",
                "audit",
                "reproduction_hash",
                "content_hash",
            }.issubset(required)
        )
        self.assertEqual(self.schema["properties"]["result_id"]["pattern"], "^mr_[a-f0-9]{64}$")

    def test_schema_contains_no_hidden_defaults(self) -> None:
        for schema in (self.schema, self.common_schema, self.evidence_schema):
            for node in walk(schema):
                self.assertNotIn("default", node)

    def test_actual_and_scenario_are_explicitly_isolated(self) -> None:
        serialized = json.dumps(self.schema["allOf"], sort_keys=True)
        self.assertIn('"const": "ACTUAL"', serialized)
        self.assertIn('"const": "SCENARIO"', serialized)
        self.assertIn('"scenario_id"', serialized)

    def test_valid_result_requires_verified_evidence(self) -> None:
        serialized = json.dumps(self.schema["allOf"], sort_keys=True)
        self.assertIn('"const": "VALID"', serialized)
        self.assertIn('"const": "VERIFIED"', serialized)

    def test_source_derived_chain_requires_files_records_and_events(self) -> None:
        chain = self.evidence_schema["$defs"]["evidenceChain"]
        serialized = json.dumps(chain["allOf"], sort_keys=True)
        self.assertIn('"const": "SOURCE_DERIVED"', serialized)
        for field in ("source_files", "source_records", "canonical_events"):
            self.assertIn(f'"{field}": {{"minItems": 1}}', serialized)

    def test_all_seven_typed_states_are_recorded(self) -> None:
        state_counts = self.common_schema["$defs"]["stateCounts"]
        expected = {"VALID", "EMPTY", "BLOCKED", "UNAVAILABLE", "CONFLICT", "INVALID", "NOT_APPLICABLE"}
        self.assertEqual(set(state_counts["required"]), expected)
        self.assertEqual(set(state_counts["properties"]), expected)

    def test_contract_forbids_kernel_and_commercial_defaults(self) -> None:
        self.assertIn("No calculation of commission", self.contract)
        self.assertIn("No activation of financial rules", self.contract)
        self.assertIn("B1b calculation implementation", self.contract)
        self.assertIn("remain blocked", self.contract)
        forbidden_examples = (
            r"\b400\s*₽",
            r"\b500\s*₽",
            r"\b40\s*₽",
            r"tax\s*=\s*\d",
            r"commission\s*=\s*\d",
        )
        for pattern in forbidden_examples:
            self.assertIsNone(re.search(pattern, self.contract, re.IGNORECASE))

    def test_contract_declares_two_hashes_and_no_ambient_time(self) -> None:
        self.assertIn("`reproduction_hash`", self.contract)
        self.assertIn("`content_hash`", self.contract)
        self.assertIn("Wall-clock time is not an implicit input", self.contract)
        self.assertIn("Binary floating point", self.contract)

    def test_valid_fixture_hashes_reproduce(self) -> None:
        document = json.loads((FIXTURE_DIR / "b3-valid-metric-result.json").read_text(encoding="utf-8"))
        verify_document_hashes(document)
        self.assertEqual(document["value"]["state"], "VALID")
        self.assertEqual(document["value"]["value"], "0.00")
        self.assertEqual(document["evidence_chain"]["validity"]["status"], "VERIFIED")

    def test_broken_link_fixture_is_blocked_and_auditable(self) -> None:
        document = json.loads((FIXTURE_DIR / "b3-blocked-broken-link-result.json").read_text(encoding="utf-8"))
        verify_document_hashes(document)
        self.assertEqual(document["value"]["state"], "BLOCKED")
        self.assertIsNone(document["value"]["value"])
        self.assertEqual(document["evidence_chain"]["validity"]["status"], "BROKEN_LINK")
        self.assertTrue(document["evidence_chain"]["validity"]["diagnostics"])


if __name__ == "__main__":
    unittest.main()
