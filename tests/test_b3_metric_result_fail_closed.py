from __future__ import annotations
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from b3_helpers import HASHES, build_chain, build_snapshot
from quantum.domain.states import DataState, TypedValue
from quantum.evidence.metric_result import CalculationMode, ConfidenceLevel, ConfidenceMetadata, EvidenceChain, EvidenceOrigin, EvidenceValidity, EvidenceValidityMetadata, FreshnessMetadata, FreshnessState, RecalculationAudit, RecalculationReason, RecordDisposition, SourceRecordRef, VersionedRef, compute_input_set_hash

class B3MetricResultFailClosedTests(unittest.TestCase):

    def test_actual_rejects_scenario_identifier(self) -> None:
        with self.assertRaisesRegex(ValueError, 'ACTUAL'):
            build_snapshot(mode=CalculationMode.ACTUAL, scenario_id='scenario-1')

    def test_scenario_requires_identifier(self) -> None:
        with self.assertRaisesRegex(ValueError, 'SCENARIO'):
            build_snapshot(mode=CalculationMode.SCENARIO, scenario_id=None)

    def test_cross_tenant_source_reference_is_rejected(self) -> None:
        profile, metric, chain = build_chain(organization_id='other-org')
        with self.assertRaisesRegex(ValueError, 'organization mismatch'):
            from quantum.evidence.metric_result import MetricResultSnapshot
            MetricResultSnapshot.build(organization_id='org-demo', marketplace_account_id='acct-demo', mode=CalculationMode.ACTUAL, scenario_id=None, calculation_instant=datetime(2026, 6, 1, tzinfo=timezone.utc), scope_dimensions={'product_id': 'SKU-1'}, calculation_profile_ref=profile, metric_definition_ref=metric, value=TypedValue.missing(DataState.BLOCKED, reason_code='CROSS_TENANT'), evidence_chain=chain, audit=RecalculationAudit('test', RecalculationReason.INITIAL, datetime(2026, 6, 1, 0, 1, tzinfo=timezone.utc), 'trace-cross-tenant'))

    def test_verified_chain_rejects_broken_event_record_link(self) -> None:
        with self.assertRaisesRegex(ValueError, 'missing source record'):
            build_chain(event_source_record_id='missing-record')

    def test_broken_link_is_preserved_only_as_non_valid_result(self) -> None:
        blocked = TypedValue.missing(DataState.BLOCKED, reason_code='EVIDENCE_LINK_BROKEN')
        snapshot = build_snapshot(validity=EvidenceValidity.BROKEN_LINK, event_source_record_id='missing-record', value=blocked)
        self.assertEqual(snapshot.value.state, DataState.BLOCKED)
        self.assertEqual(snapshot.evidence_chain.validity.status, EvidenceValidity.BROKEN_LINK)
        with self.assertRaisesRegex(ValueError, 'VALID metric result'):
            build_snapshot(validity=EvidenceValidity.BROKEN_LINK, event_source_record_id='missing-record')

    def test_input_set_hash_mismatch_is_rejected(self) -> None:
        profile, metric, chain = build_chain()
        with self.assertRaisesRegex(ValueError, 'input_set_hash mismatch'):
            EvidenceChain(organization_id=chain.organization_id, marketplace_account_id=chain.marketplace_account_id, origin=chain.origin, calculation_profile_ref=profile, metric_definition_ref=metric, rounding_policy_ref=chain.rounding_policy_ref, source_files=chain.source_files, source_records=chain.source_records, canonical_events=chain.canonical_events, included_record_count=1, excluded_record_count=0, typed_state_counts=chain.typed_state_counts, input_set_hash='9' * 64, freshness=chain.freshness, confidence=chain.confidence, validity=chain.validity)

    def test_state_counts_must_reconcile_to_source_records(self) -> None:
        profile, metric, chain = build_chain()
        wrong_counts = dict(chain.typed_state_counts)
        wrong_counts['VALID'] = 0
        with self.assertRaisesRegex(ValueError, 'typed_state_counts total'):
            EvidenceChain(organization_id=chain.organization_id, marketplace_account_id=chain.marketplace_account_id, origin=chain.origin, calculation_profile_ref=profile, metric_definition_ref=metric, rounding_policy_ref=chain.rounding_policy_ref, source_files=chain.source_files, source_records=chain.source_records, canonical_events=chain.canonical_events, included_record_count=1, excluded_record_count=0, typed_state_counts=wrong_counts, input_set_hash=chain.input_set_hash, freshness=chain.freshness, confidence=chain.confidence, validity=chain.validity)
if __name__ == '__main__':
    unittest.main()
