from __future__ import annotations
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from b3_helpers import HASHES, build_chain, build_snapshot
from quantum.domain.states import DataState, TypedValue
from quantum.evidence.metric_result import CalculationMode, ConfidenceLevel, ConfidenceMetadata, EvidenceChain, EvidenceOrigin, EvidenceValidity, EvidenceValidityMetadata, FreshnessMetadata, FreshnessState, RecalculationAudit, RecalculationReason, RecordDisposition, SourceRecordRef, VersionedRef, compute_input_set_hash

class B3MetricResultEvidencePathTests(unittest.TestCase):

    def test_stale_freshness_classification_is_deterministic(self) -> None:
        stale = FreshnessMetadata(FreshnessState.STALE, datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc), datetime(2026, 5, 31, 23, 0, tzinfo=timezone.utc), 1800)
        self.assertEqual(stale.state, FreshnessState.STALE)
        with self.assertRaisesRegex(ValueError, 'does not match'):
            FreshnessMetadata(FreshnessState.CURRENT, datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc), datetime(2026, 5, 31, 23, 0, tzinfo=timezone.utc), 1800)

    def test_confidence_missing_version_and_recalculation_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, 'Decimal'):
            ConfidenceMetadata(ConfidenceLevel.HIGH, 0.9, ('basis',))
        with self.assertRaisesRegex(ValueError, 'positive integer'):
            VersionedRef('metric.net_revenue', 0, HASHES['metric'])
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            VersionedRef('metric.net_revenue', 1, 'not-a-hash')
        with self.assertRaisesRegex(ValueError, 'predecessor'):
            RecalculationAudit('test', RecalculationReason.SOURCE_REVISION, datetime(2026, 6, 1, tzinfo=timezone.utc), 'trace-recalc')

    def test_unavailable_and_conflict_preserve_typed_reasons(self) -> None:
        for state, reason in ((DataState.UNAVAILABLE, 'SOURCE_FIELD_UNAVAILABLE'), (DataState.CONFLICT, 'AUTHORITATIVE_VALUES_CONFLICT')):
            with self.subTest(state=state):
                snapshot = build_snapshot(value=TypedValue.missing(state, reason_code=reason))
                document = snapshot.to_document()
                self.assertEqual(document['value']['state'], state.value)
                self.assertIsNone(document['value']['value'])
                self.assertEqual(document['value']['reason_code'], reason)

    def test_unknown_freshness_and_confidence_do_not_invent_values(self) -> None:
        freshness = FreshnessMetadata(FreshnessState.UNKNOWN, datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc), None, None)
        confidence = ConfidenceMetadata(ConfidenceLevel.UNKNOWN, None, ())
        self.assertIsNone(freshness.data_through)
        self.assertIsNone(freshness.max_age_seconds)
        self.assertIsNone(confidence.score)
        with self.assertRaisesRegex(ValueError, 'must not invent data age'):
            FreshnessMetadata(FreshnessState.UNKNOWN, datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc), datetime(2026, 5, 31, 23, 0, tzinfo=timezone.utc), None)
        with self.assertRaisesRegex(ValueError, 'must not invent a score'):
            ConfidenceMetadata(ConfidenceLevel.UNKNOWN, Decimal('0.5'), ())
if __name__ == '__main__':
    unittest.main()
