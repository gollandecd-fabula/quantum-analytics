from __future__ import annotations

import copy
import csv
import io
import json
import unittest
from datetime import UTC, datetime

from quantum.evidence import canonical_graph_hash
from quantum.reporting import (
    ReportingError,
    build_export_bundle,
    build_report_record,
    export_records_csv,
    export_records_jsonl,
    import_records_csv,
    import_records_jsonl,
    validate_report_record,
)
from tests.b3_helpers import graph_data, valid_snapshot


GENERATED_AT = datetime(2026, 6, 30, 16, 0, tzinfo=UTC)


class P14ReportingAdversarialTests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = valid_snapshot()
        self.record = build_report_record(
            self.snapshot,
            report_record_id="report-secure",
            generated_at=GENERATED_AT,
        )

    @staticmethod
    def graph_for_snapshot(snapshot):
        graph = copy.deepcopy(graph_data()["valid_graph"])
        reference = {
            "id": snapshot["metric_snapshot_id"],
            "version": snapshot["snapshot_revision"],
            "content_hash": snapshot["content_hash"],
        }
        graph["root_metric_snapshot_ref"] = copy.deepcopy(reference)
        root = next(
            node for node in graph["nodes"]
            if node["node_type"] == "METRIC_SNAPSHOT"
        )
        root["artifact_ref"] = copy.deepcopy(reference)
        graph["content_hash"] = canonical_graph_hash(graph)
        return graph

    def test_csv_formula_injection_is_neutralized_and_round_trips(self) -> None:
        record = build_report_record(
            self.snapshot,
            report_record_id="=2+3",
            generated_at=GENERATED_AT,
        )
        payload = export_records_csv([record])
        row = next(csv.DictReader(io.StringIO(payload.decode("utf-8"))))
        self.assertEqual(row["report_record_id"], "'=2+3")
        self.assertEqual(import_records_csv(payload), (record,))

    def test_unknown_expense_boundary_is_rejected(self) -> None:
        record = copy.deepcopy(self.record)
        record["expense_boundary"].append("HIDDEN_FEE")
        with self.assertRaisesRegex(
            ReportingError,
            "REPORT_EXPENSE_BOUNDARY_INVALID",
        ):
            validate_report_record(record)

    def test_rounding_requires_exact_nested_contract(self) -> None:
        record = copy.deepcopy(self.record)
        record["rounding"]["hidden_default"] = 2
        with self.assertRaisesRegex(ReportingError, "REPORT_ROUNDING_INVALID"):
            validate_report_record(record)

    def test_freshness_requires_valid_timestamp_and_shape(self) -> None:
        record = copy.deepcopy(self.record)
        record["freshness"]["deadline"] = "not-a-time"
        with self.assertRaisesRegex(ReportingError, "REPORT_FRESHNESS_INVALID"):
            validate_report_record(record)

    def test_confidence_reasons_must_be_unique_strings(self) -> None:
        record = copy.deepcopy(self.record)
        record["confidence"]["reasons"].append(
            record["confidence"]["reasons"][0]
        )
        with self.assertRaisesRegex(ReportingError, "REPORT_CONFIDENCE_INVALID"):
            validate_report_record(record)

    def test_money_requires_normalized_decimal_string(self) -> None:
        record = copy.deepcopy(self.record)
        record["value"] = "01.00"
        with self.assertRaisesRegex(ReportingError, "REPORT_VALUE_INVALID"):
            validate_report_record(record)

    def test_boolean_is_not_an_integer_metric(self) -> None:
        record = copy.deepcopy(self.record)
        record.update({
            "value_type": "INTEGER",
            "value": True,
            "unit": "COUNT",
            "currency": None,
        })
        with self.assertRaisesRegex(ReportingError, "REPORT_VALUE_INVALID"):
            validate_report_record(record)

    def test_duplicate_report_ids_are_rejected(self) -> None:
        duplicate = copy.deepcopy(self.record)
        with self.assertRaisesRegex(ReportingError, "EXPORT_RECORD_DUPLICATE"):
            build_export_bundle(
                [self.record, duplicate],
                bundle_id="bundle-duplicate",
                generated_at=GENERATED_AT,
            )

    def test_standalone_jsonl_tampering_is_detected(self) -> None:
        payload = export_records_jsonl([self.record])
        document = json.loads(payload.decode("utf-8"))
        document["limitations"].append("tampered")
        tampered = (
            json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        with self.assertRaisesRegex(
            ReportingError,
            "REPORT_RECORD_HASH_MISMATCH",
        ):
            import_records_jsonl(tampered)

    def test_verified_label_requires_evidence_content_hash(self) -> None:
        record = copy.deepcopy(self.record)
        record["publication_state"] = "EVIDENCE_VERIFIED"
        record["limitations"].remove("EVIDENCE_NOT_VERIFIED_FOR_PUBLICATION")
        with self.assertRaisesRegex(
            ReportingError,
            "REPORT_PUBLICATION_STATE_INVALID",
        ):
            validate_report_record(record)

    def test_valid_evidence_chain_hash_is_preserved(self) -> None:
        graph = self.graph_for_snapshot(self.snapshot)
        record = build_report_record(
            self.snapshot,
            report_record_id="report-verified",
            generated_at=GENERATED_AT,
            evidence_chain=graph,
        )
        self.assertEqual(record["publication_state"], "EVIDENCE_VERIFIED")
        self.assertEqual(
            record["evidence_chain_content_hash"],
            graph["content_hash"],
        )
        self.assertNotIn(
            "EVIDENCE_NOT_VERIFIED_FOR_PUBLICATION",
            record["limitations"],
        )

    def test_evidence_chain_must_reference_exact_snapshot(self) -> None:
        graph = self.graph_for_snapshot(self.snapshot)
        graph["root_metric_snapshot_ref"]["content_hash"] = "f" * 64
        root = next(
            node for node in graph["nodes"]
            if node["node_type"] == "METRIC_SNAPSHOT"
        )
        root["artifact_ref"]["content_hash"] = "f" * 64
        graph["content_hash"] = canonical_graph_hash(graph)

        with self.assertRaisesRegex(
            ReportingError,
            "REPORT_EVIDENCE_BINDING_MISMATCH",
        ):
            build_report_record(
                self.snapshot,
                report_record_id="report-wrong-root",
                generated_at=GENERATED_AT,
                evidence_chain=graph,
            )


if __name__ == "__main__":
    unittest.main()
