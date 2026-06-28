from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from quantum.domain.states import TypedValue
from quantum.evidence.metric_result import (
    CalculationMode,
    CanonicalEventRef,
    ConfidenceLevel,
    ConfidenceMetadata,
    EvidenceChain,
    EvidenceOrigin,
    EvidenceValidity,
    EvidenceValidityMetadata,
    FreshnessMetadata,
    FreshnessState,
    MetricResultSnapshot,
    RecalculationAudit,
    RecalculationReason,
    RecordDisposition,
    SourceFileRef,
    SourceRecordRef,
    VersionedRef,
    compute_input_set_hash,
)


HASHES = {
    "profile": "1" * 64,
    "metric": "2" * 64,
    "rounding": "3" * 64,
    "file": "4" * 64,
    "row": "5" * 64,
    "event": "6" * 64,
    "normalization": "7" * 64,
}


def build_chain(
    *,
    organization_id: str = "org-demo",
    marketplace_account_id: str = "acct-demo",
    profile_hash: str = HASHES["profile"],
    event_source_record_id: str = "record-1",
    validity: EvidenceValidity = EvidenceValidity.VERIFIED,
    freshness_state: FreshnessState = FreshnessState.CURRENT,
) -> tuple[VersionedRef, VersionedRef, EvidenceChain]:
    profile = VersionedRef("profile.actual.default", 1, profile_hash)
    metric = VersionedRef("metric.net_revenue", 1, HASHES["metric"])
    rounding = VersionedRef("rounding.standard", 1, HASHES["rounding"])
    normalization = VersionedRef("normalization.synthetic", 1, HASHES["normalization"])
    source_file = SourceFileRef(
        "batch-1",
        organization_id,
        marketplace_account_id,
        HASHES["file"],
        "adapter.synthetic",
        "1.0.0",
        "schema.synthetic.v1",
    )
    source_record = SourceRecordRef(
        "record-1",
        "batch-1",
        organization_id,
        marketplace_account_id,
        "row-1",
        HASHES["row"],
        "VALID",
        RecordDisposition.INCLUDED,
    )
    event = CanonicalEventRef(
        "event-1",
        organization_id,
        marketplace_account_id,
        event_source_record_id,
        1,
        HASHES["event"],
        normalization,
    )
    freshness = FreshnessMetadata(
        freshness_state,
        datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 5, 31, 23, 0, tzinfo=timezone.utc),
        7200 if freshness_state is FreshnessState.CURRENT else 1800,
    )
    confidence = ConfidenceMetadata(
        ConfidenceLevel.HIGH,
        Decimal("0.95"),
        ("complete synthetic source set",),
    )
    validity_metadata = EvidenceValidityMetadata(
        validity,
        datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc),
        () if validity is EvidenceValidity.VERIFIED else ("EVENT_SOURCE_RECORD_LINK_MISSING",),
    )
    input_hash = compute_input_set_hash(
        calculation_profile_ref=profile,
        metric_definition_ref=metric,
        rounding_policy_ref=rounding,
        source_files=(source_file,),
        source_records=(source_record,),
        canonical_events=(event,),
    )
    chain = EvidenceChain(
        organization_id=organization_id,
        marketplace_account_id=marketplace_account_id,
        origin=EvidenceOrigin.SOURCE_DERIVED,
        calculation_profile_ref=profile,
        metric_definition_ref=metric,
        rounding_policy_ref=rounding,
        source_files=(source_file,),
        source_records=(source_record,),
        canonical_events=(event,),
        included_record_count=1,
        excluded_record_count=0,
        typed_state_counts={
            "VALID": 1,
            "EMPTY": 0,
            "BLOCKED": 0,
            "UNAVAILABLE": 0,
            "CONFLICT": 0,
            "INVALID": 0,
            "NOT_APPLICABLE": 0,
        },
        input_set_hash=input_hash,
        freshness=freshness,
        confidence=confidence,
        validity=validity_metadata,
        limitations=("synthetic fixture only",),
    )
    return profile, metric, chain


def build_snapshot(
    *,
    actor: str = "test-harness",
    profile_hash: str = HASHES["profile"],
    mode: CalculationMode = CalculationMode.ACTUAL,
    scenario_id: str | None = None,
    validity: EvidenceValidity = EvidenceValidity.VERIFIED,
    event_source_record_id: str = "record-1",
    value: TypedValue | None = None,
) -> MetricResultSnapshot:
    profile, metric, chain = build_chain(
        profile_hash=profile_hash,
        validity=validity,
        event_source_record_id=event_source_record_id,
    )
    if value is None:
        value = TypedValue.valid(
            Decimal("0.00"),
            value_type="decimal",
            unit="RUB",
            source_record_id="record-1",
            observed_at=datetime(2026, 5, 31, 23, 0, tzinfo=timezone.utc),
        )
    return MetricResultSnapshot.build(
        organization_id="org-demo",
        marketplace_account_id="acct-demo",
        mode=mode,
        scenario_id=scenario_id,
        calculation_instant=datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc),
        scope_dimensions={
            "product_id": "SKU-1",
            "period_start": "2026-05-01",
            "period_end": "2026-06-01",
        },
        calculation_profile_ref=profile,
        metric_definition_ref=metric,
        value=value,
        evidence_chain=chain,
        audit=RecalculationAudit(
            actor,
            RecalculationReason.INITIAL,
            datetime(2026, 6, 1, 0, 1, tzinfo=timezone.utc),
            f"trace-{actor}",
        ),
    )
