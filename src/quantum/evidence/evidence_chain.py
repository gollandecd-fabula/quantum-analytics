from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from quantum.domain.states import DataState

from .canonical import require_hash, require_text, sha256_hex
from .references import (
    CanonicalEventRef,
    ConfidenceMetadata,
    EvidenceOrigin,
    EvidenceValidity,
    EvidenceValidityMetadata,
    FreshnessMetadata,
    RecordDisposition,
    SourceFileRef,
    SourceRecordRef,
    VersionedRef,
)


_CANONICAL_STATES = tuple(state.value for state in DataState)


def compute_input_set_hash(
    *,
    calculation_profile_ref: VersionedRef,
    metric_definition_ref: VersionedRef,
    rounding_policy_ref: VersionedRef,
    source_files: Sequence[SourceFileRef],
    source_records: Sequence[SourceRecordRef],
    canonical_events: Sequence[CanonicalEventRef],
) -> str:
    material = {
        "calculation_profile_ref": calculation_profile_ref,
        "metric_definition_ref": metric_definition_ref,
        "rounding_policy_ref": rounding_policy_ref,
        "source_files": sorted(source_files, key=lambda item: (item.import_batch_id, item.source_file_sha256)),
        "source_records": sorted(source_records, key=lambda item: item.source_record_id),
        "canonical_events": sorted(canonical_events, key=lambda item: (item.event_id, item.revision)),
    }
    return sha256_hex(material)


@dataclass(frozen=True, slots=True)
class EvidenceChain:
    organization_id: str
    marketplace_account_id: str | None
    origin: EvidenceOrigin
    calculation_profile_ref: VersionedRef
    metric_definition_ref: VersionedRef
    rounding_policy_ref: VersionedRef
    source_files: tuple[SourceFileRef, ...]
    source_records: tuple[SourceRecordRef, ...]
    canonical_events: tuple[CanonicalEventRef, ...]
    included_record_count: int
    excluded_record_count: int
    typed_state_counts: Mapping[str, int]
    input_set_hash: str
    freshness: FreshnessMetadata
    confidence: ConfidenceMetadata
    validity: EvidenceValidityMetadata
    limitations: tuple[str, ...] = ()
    system_generated_reason: str | None = None

    def __post_init__(self) -> None:
        require_text(self.organization_id, "EvidenceChain.organization_id")
        if self.marketplace_account_id is not None:
            require_text(self.marketplace_account_id, "EvidenceChain.marketplace_account_id")
        object.__setattr__(self, "source_files", tuple(self.source_files))
        object.__setattr__(self, "source_records", tuple(self.source_records))
        object.__setattr__(self, "canonical_events", tuple(self.canonical_events))
        object.__setattr__(self, "limitations", tuple(self.limitations))
        state_counts = dict(self.typed_state_counts)
        object.__setattr__(self, "typed_state_counts", MappingProxyType(state_counts))
        require_hash(self.input_set_hash, "EvidenceChain.input_set_hash")

        if set(state_counts) != set(_CANONICAL_STATES):
            raise ValueError("typed_state_counts must contain every canonical state exactly once.")
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in state_counts.values()):
            raise ValueError("typed_state_counts values must be non-negative integers.")
        if isinstance(self.included_record_count, bool) or self.included_record_count < 0:
            raise ValueError("included_record_count must be non-negative.")
        if isinstance(self.excluded_record_count, bool) or self.excluded_record_count < 0:
            raise ValueError("excluded_record_count must be non-negative.")

        if self.origin is EvidenceOrigin.SOURCE_DERIVED:
            if self.marketplace_account_id is None:
                raise ValueError("SOURCE_DERIVED evidence requires marketplace_account_id.")
            if not self.source_files or not self.source_records or not self.canonical_events:
                raise ValueError("SOURCE_DERIVED evidence requires file, record, and event references.")
            if self.system_generated_reason is not None:
                raise ValueError("SOURCE_DERIVED evidence must not have system_generated_reason.")
        else:
            if self.source_files or self.source_records or self.canonical_events:
                raise ValueError("SYSTEM_GENERATED evidence must not contain source references.")
            if not self.system_generated_reason:
                raise ValueError("SYSTEM_GENERATED evidence requires a reason.")

        file_ids = [item.import_batch_id for item in self.source_files]
        record_ids = [item.source_record_id for item in self.source_records]
        event_keys = [(item.event_id, item.revision) for item in self.canonical_events]
        if len(file_ids) != len(set(file_ids)):
            raise ValueError("Duplicate source file/import batch reference.")
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("Duplicate source record reference.")
        if len(event_keys) != len(set(event_keys)):
            raise ValueError("Duplicate canonical event revision reference.")

        for item in self.source_files:
            self._require_tenant(item.organization_id, item.marketplace_account_id, "source file")
        for item in self.source_records:
            self._require_tenant(item.organization_id, item.marketplace_account_id, "source record")
        for item in self.canonical_events:
            self._require_tenant(item.organization_id, item.marketplace_account_id, "canonical event")

        if self.origin is EvidenceOrigin.SOURCE_DERIVED:
            file_set = set(file_ids)
            record_set = set(record_ids)
            if any(item.import_batch_id not in file_set for item in self.source_records):
                if self.validity.status is EvidenceValidity.VERIFIED:
                    raise ValueError("Source record references a missing import batch.")
            if any(item.source_record_id not in record_set for item in self.canonical_events):
                if self.validity.status is EvidenceValidity.VERIFIED:
                    raise ValueError("Canonical event references a missing source record.")

        included = sum(item.disposition is RecordDisposition.INCLUDED for item in self.source_records)
        excluded = sum(item.disposition is RecordDisposition.EXCLUDED for item in self.source_records)
        if (included, excluded) != (self.included_record_count, self.excluded_record_count):
            raise ValueError("Included/excluded counts do not match source record dispositions.")
        if sum(state_counts.values()) != len(self.source_records):
            raise ValueError("typed_state_counts total must equal source record count.")

        expected_input_hash = compute_input_set_hash(
            calculation_profile_ref=self.calculation_profile_ref,
            metric_definition_ref=self.metric_definition_ref,
            rounding_policy_ref=self.rounding_policy_ref,
            source_files=self.source_files,
            source_records=self.source_records,
            canonical_events=self.canonical_events,
        )
        if self.input_set_hash != expected_input_hash:
            raise ValueError("EvidenceChain.input_set_hash mismatch.")

    def _require_tenant(self, organization_id: str, account_id: str, label: str) -> None:
        if organization_id != self.organization_id:
            raise ValueError(f"Cross-tenant {label} reference.")
        if account_id != self.marketplace_account_id:
            raise ValueError(f"Cross-account {label} reference.")
