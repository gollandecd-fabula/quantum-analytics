from __future__ import annotations

import unittest
from datetime import datetime, timezone
from decimal import Decimal

from b3_helpers import HASHES, build_chain, build_snapshot
from quantum.domain.states import TypedValue
from quantum.evidence.metric_result import (
    CalculationMode,
    MetricResultSnapshot,
    RecalculationAudit,
    RecalculationReason,
    canonical_json_bytes,
    verify_document_hashes,
)


class B3MetricResultHashingTests(unittest.TestCase):
    def test_exact_rebuild_is_deterministic(self) -> None:
        first = build_snapshot().to_document()
        second = build_snapshot().to_document()
        self.assertEqual(first, second)
        verify_document_hashes(first)

    def test_actor_changes_content_but_not_reproduction_hash(self) -> None:
        first = build_snapshot(actor="actor-a")
        second = build_snapshot(actor="actor-b")
        self.assertEqual(first.reproduction_hash, second.reproduction_hash)
        self.assertNotEqual(first.content_hash, second.content_hash)
        self.assertNotEqual(first.result_id, second.result_id)

    def test_profile_content_change_changes_reproduction_identity(self) -> None:
        first = build_snapshot(profile_hash=HASHES["profile"])
        second = build_snapshot(profile_hash="8" * 64)
        self.assertNotEqual(first.reproduction_hash, second.reproduction_hash)
        self.assertNotEqual(first.result_id, second.result_id)

    def test_mutated_document_hash_is_rejected(self) -> None:
        document = build_snapshot().to_document()
        document["scope_dimensions"]["product_id"] = "SKU-2"
        with self.assertRaisesRegex(ValueError, "reproduction_hash mismatch"):
            verify_document_hashes(document)

    def test_binary_float_is_forbidden_in_hash_material(self) -> None:
        with self.assertRaisesRegex(TypeError, "floating point"):
            canonical_json_bytes({"amount": 0.1})

    def test_actual_and_scenario_identity_are_isolated(self) -> None:
        actual = build_snapshot()
        scenario = build_snapshot(mode=CalculationMode.SCENARIO, scenario_id="scenario-1")
        self.assertNotEqual(actual.reproduction_hash, scenario.reproduction_hash)
        self.assertNotEqual(actual.result_id, scenario.result_id)

    def test_recalculation_records_predecessor_and_new_content_identity(self) -> None:
        original = build_snapshot()
        profile, metric, chain = build_chain()
        recalculated = MetricResultSnapshot.build(
            organization_id="org-demo",
            marketplace_account_id="acct-demo",
            mode=CalculationMode.ACTUAL,
            scenario_id=None,
            calculation_instant=datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc),
            scope_dimensions={
                "product_id": "SKU-1",
                "period_start": "2026-05-01",
                "period_end": "2026-06-01",
            },
            calculation_profile_ref=profile,
            metric_definition_ref=metric,
            value=TypedValue.valid(
                Decimal("0.00"),
                value_type="decimal",
                unit="RUB",
                source_record_id="record-1",
                observed_at=datetime(2026, 5, 31, 23, 0, tzinfo=timezone.utc),
            ),
            evidence_chain=chain,
            audit=RecalculationAudit(
                "auditor",
                RecalculationReason.SOURCE_REVISION,
                datetime(2026, 6, 1, 0, 2, tzinfo=timezone.utc),
                "trace-recalculated",
                predecessor_result_id=original.result_id,
            ),
        )
        self.assertEqual(recalculated.reproduction_hash, original.reproduction_hash)
        self.assertNotEqual(recalculated.content_hash, original.content_hash)
        self.assertEqual(recalculated.audit.predecessor_result_id, original.result_id)

    def test_snapshot_defensively_freezes_nested_value_and_metadata(self) -> None:
        payload = {"components": [1, 2]}
        metadata = {"labels": ["source-a"]}
        value = TypedValue.valid(payload, value_type="json", metadata=metadata)
        snapshot = build_snapshot(value=value)
        before = snapshot.to_document()
        payload["components"].append(3)
        metadata["labels"].append("source-b")
        after = snapshot.to_document()
        self.assertEqual(before, after)
        self.assertEqual(after["value"]["value"]["components"], [1, 2])
        self.assertEqual(after["value"]["metadata"]["labels"], ["source-a"])


if __name__ == "__main__":
    unittest.main()
