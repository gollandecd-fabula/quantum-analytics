from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from .canonical import ID_RE, require_aware, require_hash, require_text


class CalculationMode(StrEnum):
    ACTUAL = "ACTUAL"
    SCENARIO = "SCENARIO"


class EvidenceOrigin(StrEnum):
    SOURCE_DERIVED = "SOURCE_DERIVED"
    SYSTEM_GENERATED = "SYSTEM_GENERATED"


class RecordDisposition(StrEnum):
    INCLUDED = "INCLUDED"
    EXCLUDED = "EXCLUDED"


class FreshnessState(StrEnum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class ConfidenceLevel(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class EvidenceValidity(StrEnum):
    VERIFIED = "VERIFIED"
    BROKEN_LINK = "BROKEN_LINK"
    MISSING_VERSION = "MISSING_VERSION"
    HASH_MISMATCH = "HASH_MISMATCH"
    CROSS_TENANT = "CROSS_TENANT"
    UNVERIFIED = "UNVERIFIED"


class RecalculationReason(StrEnum):
    INITIAL = "INITIAL"
    SOURCE_REVISION = "SOURCE_REVISION"
    PROFILE_CHANGE = "PROFILE_CHANGE"
    METRIC_DEFINITION_CHANGE = "METRIC_DEFINITION_CHANGE"
    ROUNDING_POLICY_CHANGE = "ROUNDING_POLICY_CHANGE"
    MANUAL_CORRECTION = "MANUAL_CORRECTION"
    RESTATEMENT = "RESTATEMENT"


@dataclass(frozen=True, slots=True)
class VersionedRef:
    id: str
    version: int
    content_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not ID_RE.fullmatch(self.id):
            raise ValueError("VersionedRef.id has invalid format.")
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 1:
            raise ValueError("VersionedRef.version must be a positive integer.")
        require_hash(self.content_hash, "VersionedRef.content_hash")


@dataclass(frozen=True, slots=True)
class SourceFileRef:
    import_batch_id: str
    organization_id: str
    marketplace_account_id: str
    source_file_sha256: str
    adapter_id: str
    adapter_version: str
    source_schema_id: str

    def __post_init__(self) -> None:
        for name in (
            "import_batch_id",
            "organization_id",
            "marketplace_account_id",
            "adapter_id",
            "adapter_version",
            "source_schema_id",
        ):
            require_text(getattr(self, name), f"SourceFileRef.{name}")
        require_hash(self.source_file_sha256, "SourceFileRef.source_file_sha256")


@dataclass(frozen=True, slots=True)
class SourceRecordRef:
    source_record_id: str
    import_batch_id: str
    organization_id: str
    marketplace_account_id: str
    source_row_key: str
    raw_row_hash: str
    validation_status: str
    disposition: RecordDisposition
    reason_code: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "source_record_id",
            "import_batch_id",
            "organization_id",
            "marketplace_account_id",
            "source_row_key",
        ):
            require_text(getattr(self, name), f"SourceRecordRef.{name}")
        require_hash(self.raw_row_hash, "SourceRecordRef.raw_row_hash")
        if self.validation_status not in {"VALID", "QUARANTINED", "INVALID"}:
            raise ValueError("SourceRecordRef.validation_status is invalid.")
        if self.disposition is RecordDisposition.INCLUDED:
            if self.validation_status != "VALID":
                raise ValueError("Included source records must be VALID.")
            if self.reason_code is not None:
                raise ValueError("Included source records must not have reason_code.")
        elif not self.reason_code:
            raise ValueError("Excluded source records require reason_code.")


@dataclass(frozen=True, slots=True)
class CanonicalEventRef:
    event_id: str
    organization_id: str
    marketplace_account_id: str
    source_record_id: str
    revision: int
    event_hash: str
    normalization_rule_ref: VersionedRef

    def __post_init__(self) -> None:
        for name in (
            "event_id",
            "organization_id",
            "marketplace_account_id",
            "source_record_id",
        ):
            require_text(getattr(self, name), f"CanonicalEventRef.{name}")
        if not isinstance(self.revision, int) or isinstance(self.revision, bool) or self.revision < 1:
            raise ValueError("CanonicalEventRef.revision must be positive.")
        require_hash(self.event_hash, "CanonicalEventRef.event_hash")


@dataclass(frozen=True, slots=True)
class FreshnessMetadata:
    state: FreshnessState
    evaluated_at: datetime
    data_through: datetime | None
    max_age_seconds: int | None

    def __post_init__(self) -> None:
        require_aware(self.evaluated_at, "FreshnessMetadata.evaluated_at")
        if self.state is FreshnessState.UNKNOWN:
            if self.data_through is not None or self.max_age_seconds is not None:
                raise ValueError("UNKNOWN freshness must not invent data age.")
            return
        if self.data_through is None or self.max_age_seconds is None:
            raise ValueError("CURRENT/STALE freshness requires data_through and max_age_seconds.")
        require_aware(self.data_through, "FreshnessMetadata.data_through")
        if isinstance(self.max_age_seconds, bool) or self.max_age_seconds < 0:
            raise ValueError("max_age_seconds must be non-negative.")
        age = (self.evaluated_at - self.data_through).total_seconds()
        if age < 0:
            raise ValueError("data_through cannot be after evaluated_at.")
        expected = FreshnessState.CURRENT if age <= self.max_age_seconds else FreshnessState.STALE
        if self.state is not expected:
            raise ValueError("Freshness state does not match recorded timestamps and threshold.")


@dataclass(frozen=True, slots=True)
class ConfidenceMetadata:
    level: ConfidenceLevel
    score: Decimal | None
    basis: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "basis", tuple(self.basis))
        if self.level is ConfidenceLevel.UNKNOWN:
            if self.score is not None:
                raise ValueError("UNKNOWN confidence must not invent a score.")
            return
        if self.score is None or not isinstance(self.score, Decimal):
            raise ValueError("Known confidence requires a Decimal score.")
        if not self.score.is_finite() or self.score < 0 or self.score > 1:
            raise ValueError("Confidence score must be between 0 and 1.")
        if not self.basis or any(not item for item in self.basis):
            raise ValueError("Known confidence requires non-empty basis entries.")


@dataclass(frozen=True, slots=True)
class EvidenceValidityMetadata:
    status: EvidenceValidity
    checked_at: datetime
    diagnostics: tuple[str, ...]

    def __post_init__(self) -> None:
        require_aware(self.checked_at, "EvidenceValidityMetadata.checked_at")
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        if self.status is EvidenceValidity.VERIFIED:
            if self.diagnostics:
                raise ValueError("VERIFIED evidence must not contain diagnostics.")
        elif not self.diagnostics or any(not item for item in self.diagnostics):
            raise ValueError("Non-verified evidence requires diagnostics.")


@dataclass(frozen=True, slots=True)
class RecalculationAudit:
    actor: str
    reason: RecalculationReason
    calculated_at: datetime
    trace_id: str
    predecessor_result_id: str | None = None

    def __post_init__(self) -> None:
        require_text(self.actor, "RecalculationAudit.actor")
        require_text(self.trace_id, "RecalculationAudit.trace_id")
        require_aware(self.calculated_at, "RecalculationAudit.calculated_at")
        if self.reason is RecalculationReason.INITIAL:
            if self.predecessor_result_id is not None:
                raise ValueError("INITIAL result must not have a predecessor.")
        else:
            if not self.predecessor_result_id:
                raise ValueError("Recalculation requires predecessor_result_id.")
            if not re.fullmatch(r"mr_[a-f0-9]{64}", self.predecessor_result_id):
                raise ValueError("predecessor_result_id has invalid format.")
