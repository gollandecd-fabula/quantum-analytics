from __future__ import annotations
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from b3_helpers import HASHES, build_chain
from quantum.domain.states import TypedValue
from quantum.evidence.metric_result import CalculationMode, ConfidenceLevel, ConfidenceMetadata, EvidenceChain, EvidenceOrigin, EvidenceValidity, EvidenceValidityMetadata, FreshnessMetadata, FreshnessState, MetricResultSnapshot, RecalculationAudit, RecalculationReason, RecordDisposition, SourceRecordRef, compute_input_set_hash

class B3MetricResultSystemEvidenceTests(unittest.TestCase):

    def test_system_generated_evidence_is_explicit_and_source_free(self) -> None:
        profile, metric, source_chain = build_chain()
        freshness = FreshnessMetadata(FreshnessState.UNKNOWN, datetime(2026, 6, 1, tzinfo=timezone.utc), None, None)
        confidence = ConfidenceMetadata(ConfidenceLevel.UNKNOWN, None, ())
        chain = EvidenceChain(organization_id='org-demo', marketplace_account_id=None, origin=EvidenceOrigin.SYSTEM_GENERATED, calculation_profile_ref=profile, metric_definition_ref=metric, rounding_policy_ref=source_chain.rounding_policy_ref, source_files=(), source_records=(), canonical_events=(), included_record_count=0, excluded_record_count=0, typed_state_counts={'VALID': 0, 'EMPTY': 0, 'BLOCKED': 0, 'UNAVAILABLE': 0, 'CONFLICT': 0, 'INVALID': 0, 'NOT_APPLICABLE': 0}, input_set_hash=compute_input_set_hash(calculation_profile_ref=profile, metric_definition_ref=metric, rounding_policy_ref=source_chain.rounding_policy_ref, source_files=(), source_records=(), canonical_events=()), freshness=freshness, confidence=confidence, validity=EvidenceValidityMetadata(EvidenceValidity.VERIFIED, datetime(2026, 6, 1, tzinfo=timezone.utc), ()), system_generated_reason='contract-defined constant-free system metric')
        snapshot = MetricResultSnapshot.build(organization_id='org-demo', marketplace_account_id=None, mode=CalculationMode.ACTUAL, scenario_id=None, calculation_instant=datetime(2026, 6, 1, tzinfo=timezone.utc), scope_dimensions={'scope': 'organization'}, calculation_profile_ref=profile, metric_definition_ref=metric, value=TypedValue.valid(Decimal('0'), value_type='decimal', unit='COUNT'), evidence_chain=chain, audit=RecalculationAudit('system', RecalculationReason.INITIAL, datetime(2026, 6, 1, 0, 1, tzinfo=timezone.utc), 'trace-system-generated'))
        document = snapshot.to_document()
        self.assertEqual(document['evidence_chain']['origin'], 'SYSTEM_GENERATED')
        self.assertEqual(document['evidence_chain']['source_files'], [])
        self.assertEqual(document['evidence_chain']['system_generated_reason'], 'contract-defined constant-free system metric')

    def test_verified_chain_rejects_source_record_with_missing_import_batch(self) -> None:
        profile, metric, chain = build_chain()
        record = SourceRecordRef('record-1', 'missing-batch', 'org-demo', 'acct-demo', 'row-1', HASHES['row'], 'VALID', RecordDisposition.INCLUDED)
        input_hash = compute_input_set_hash(calculation_profile_ref=profile, metric_definition_ref=metric, rounding_policy_ref=chain.rounding_policy_ref, source_files=chain.source_files, source_records=(record,), canonical_events=chain.canonical_events)
        with self.assertRaisesRegex(ValueError, 'missing import batch'):
            EvidenceChain(organization_id=chain.organization_id, marketplace_account_id=chain.marketplace_account_id, origin=chain.origin, calculation_profile_ref=profile, metric_definition_ref=metric, rounding_policy_ref=chain.rounding_policy_ref, source_files=chain.source_files, source_records=(record,), canonical_events=chain.canonical_events, included_record_count=1, excluded_record_count=0, typed_state_counts=chain.typed_state_counts, input_set_hash=input_hash, freshness=chain.freshness, confidence=chain.confidence, validity=chain.validity)
if __name__ == '__main__':
    unittest.main()
