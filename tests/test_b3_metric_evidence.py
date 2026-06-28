from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from quantum.evidence import (
    canonical_sha256,
    evidence_input_fingerprint,
    validate_metric_evidence,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/contracts/fixtures/b3-valid-metric-evidence.json"


def load_bundle() -> tuple[dict, dict]:
    bundle = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return bundle["metric_result"], bundle["evidence_chain"]


class B3MetricEvidenceTests(unittest.TestCase):
    def test_schemas_are_machine_readable_and_fail_closed(self) -> None:
        metric = json.loads((ROOT / "schemas/metric-result.schema.json").read_text(encoding="utf-8"))
        chain = json.loads((ROOT / "schemas/evidence-chain.schema.json").read_text(encoding="utf-8"))
        self.assertFalse(metric["additionalProperties"])
        self.assertFalse(chain["additionalProperties"])
        self.assertIn("evidence_chain_ref", metric["required"])
        self.assertIn("recalculation", metric["required"])
        self.assertIn("source_files", chain["required"])
        self.assertIn("links", chain["required"])
        self.assertEqual(chain["properties"]["source_files"]["minItems"], 1)
        self.assertEqual(chain["properties"]["source_records"]["minItems"], 1)

    def test_valid_fixture_reproduces_exact_hashes(self) -> None:
        result, chain = load_bundle()
        self.assertEqual(validate_metric_evidence(result, chain), ())
        self.assertEqual(result["result_hash"], canonical_sha256(result, {"result_hash"}))
        self.assertEqual(
            chain["content_hash"],
            canonical_sha256(chain, {"content_hash", "metric_result_hash"}),
        )
        self.assertEqual(result["input_fingerprint"], evidence_input_fingerprint(chain))
        self.assertEqual(chain["input_fingerprint"], evidence_input_fingerprint(chain))

    def test_hashing_is_acyclic_but_backlink_is_verified(self) -> None:
        result, chain = load_bundle()
        original_chain_hash = canonical_sha256(chain, {"content_hash", "metric_result_hash"})
        chain["metric_result_hash"] = "0" * 64
        self.assertEqual(
            original_chain_hash,
            canonical_sha256(chain, {"content_hash", "metric_result_hash"}),
        )
        self.assertIn("RESULT_CHAIN_HASH_MISMATCH", validate_metric_evidence(result, chain))

    def test_broken_event_record_link_fails_closed(self) -> None:
        result, chain = load_bundle()
        chain["events"][0]["source_record_id"] = "missing-record"
        errors = validate_metric_evidence(result, chain)
        self.assertIn("EVENT_RECORD_MISSING:event-demo", errors)
        self.assertIn("EVIDENCE_CONTENT_HASH_MISMATCH", errors)

    def test_broken_source_file_link_fails_closed(self) -> None:
        result, chain = load_bundle()
        chain["source_records"][0]["source_file_sha256"] = "9" * 64
        errors = validate_metric_evidence(result, chain)
        self.assertIn("SOURCE_RECORD_FILE_MISSING:record-demo", errors)

    def test_dangling_and_duplicate_graph_links_fail_closed(self) -> None:
        result, chain = load_bundle()
        duplicate = copy.deepcopy(chain["links"][0])
        chain["links"].append(duplicate)
        chain["links"].append({
            "from_kind": "EVENT",
            "from_id": "unknown-event",
            "to_kind": "SOURCE_RECORD",
            "to_id": "record-demo",
            "relation": "NORMALIZED_FROM",
        })
        errors = validate_metric_evidence(result, chain)
        self.assertTrue(any(code.startswith("DUPLICATE_LINK:") for code in errors))
        self.assertIn("LINK_FROM_MISSING:EVENT:unknown-event", errors)

    def test_non_valid_state_cannot_carry_value_or_publish(self) -> None:
        result, chain = load_bundle()
        result["result"].update({"state": "BLOCKED", "value": "0", "reason_code": "MISSING_COST"})
        result["validity"].update({"state": "BLOCKED", "diagnostic_codes": ["MISSING_COST"], "publishable": True})
        errors = validate_metric_evidence(result, chain)
        self.assertIn("NON_VALID_RESULT_VALUE_CONTRADICTION", errors)
        self.assertIn("NON_VALID_RESULT_PUBLISHABLE", errors)

    def test_actual_and_scenario_are_isolated(self) -> None:
        result, chain = load_bundle()
        result["scenario_id"] = "scenario-should-not-exist"
        self.assertIn("ACTUAL_SCENARIO_ID_PRESENT", validate_metric_evidence(result, chain))
        result["mode"] = "SCENARIO"
        result["scenario_id"] = None
        self.assertIn("SCENARIO_ID_MISSING", validate_metric_evidence(result, chain))

    def test_freshness_contradictions_fail_closed(self) -> None:
        result, chain = load_bundle()
        result["freshness"].update({"status": "STALE", "age_seconds": 10, "max_age_seconds": 3600})
        self.assertIn("FRESHNESS_STALE_CONTRADICTION", validate_metric_evidence(result, chain))
        result["freshness"].update({"status": "UNKNOWN", "age_seconds": 10, "max_age_seconds": None})
        self.assertIn("FRESHNESS_UNKNOWN_CONTRADICTION", validate_metric_evidence(result, chain))

    def test_recalculation_requires_predecessor_and_ordered_timestamps(self) -> None:
        result, chain = load_bundle()
        result["recalculation"].update({
            "kind": "RECALCULATION",
            "requested_at": "2026-06-28T08:02:00Z",
            "completed_at": "2026-06-28T08:01:00Z",
        })
        errors = validate_metric_evidence(result, chain)
        self.assertIn("RECALC_PREDECESSOR_MISSING", errors)
        self.assertIn("RECALC_TIMESTAMP_INVERSION", errors)

    def test_recalculation_actor_must_match_evidence_actor(self) -> None:
        result, chain = load_bundle()
        chain["actor"] = "different-agent"
        errors = validate_metric_evidence(result, chain)
        self.assertIn("RECALC_ACTOR_MISMATCH", errors)
        self.assertIn("EVIDENCE_CONTENT_HASH_MISMATCH", errors)

    def test_missing_required_result_link_fails_closed(self) -> None:
        result, chain = load_bundle()
        chain["links"] = [
            link for link in chain["links"]
            if link["relation"] != "ROUNDED_WITH"
        ]
        errors = validate_metric_evidence(result, chain)
        self.assertIn(
            "REQUIRED_RESULT_LINK_MISSING:ROUNDING_POLICY|rounding-v1|ROUNDED_WITH",
            errors,
        )

    def test_complete_explicit_source_chain_is_required(self) -> None:
        result, chain = load_bundle()
        chain["links"] = [
            link for link in chain["links"]
            if link["to_kind"] not in {"EVENT", "TRANSFORMATION", "SOURCE_RECORD", "SOURCE_FILE"}
        ]
        errors = validate_metric_evidence(result, chain)
        self.assertIn("REQUIRED_RESULT_EVENT_LINK_MISSING:event-demo", errors)
        self.assertIn("REQUIRED_EVENT_RECORD_LINK_MISSING:event-demo:record-demo", errors)
        self.assertIn("REQUIRED_EVENT_TRANSFORMATION_LINK_MISSING:event-demo", errors)
        self.assertIn("REQUIRED_RECORD_FILE_LINK_MISSING:record-demo:file-demo", errors)
        self.assertIn("ORPHAN_TRANSFORMATION:normalize-demo", errors)

    def test_contract_documents_define_immutable_and_non_write_boundaries(self) -> None:
        metric_contract = (ROOT / "docs/metrics/METRIC_RESULT_CONTRACT.md").read_text(encoding="utf-8")
        evidence_contract = (ROOT / "docs/evidence/EVIDENCE_CHAIN_CONTRACT.md").read_text(encoding="utf-8")
        self.assertIn("never edited in place", metric_contract)
        self.assertIn("fail closed", metric_contract)
        self.assertIn("circular hash dependency", evidence_contract)
        self.assertIn("no write integration", evidence_contract)
        self.assertNotIn("requests.post", metric_contract + evidence_contract)


if __name__ == "__main__":
    unittest.main()
