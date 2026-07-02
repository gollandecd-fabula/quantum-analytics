from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
import re
from typing import Final
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ._xlsx_contracts import XlsxPackageInspection

_HEX_SHA256: Final = re.compile(r"^[0-9a-f]{64}$")
_SAFE_IDENTIFIER: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")
_ALLOWED_TRANSITIONS: Final = {
    "DECLARED": {"QUARANTINED", "REJECTED"},
    "QUARANTINED": {"VALIDATED", "REJECTED"},
    "VALIDATED": {"ADMITTED", "REJECTED"},
    "ADMITTED": {"REVOKED"},
    "REJECTED": set(),
    "REVOKED": set(),
}


class AdmissionError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class DatasetAdmissionState(StrEnum):
    DECLARED = "DECLARED"
    QUARANTINED = "QUARANTINED"
    VALIDATED = "VALIDATED"
    ADMITTED = "ADMITTED"
    REJECTED = "REJECTED"
    REVOKED = "REVOKED"


class DatasetSensitivity(StrEnum):
    COMMERCIAL_CONFIDENTIAL = "COMMERCIAL_CONFIDENTIAL"
    COMMERCIAL_WITH_PERSONAL_DATA = "COMMERCIAL_WITH_PERSONAL_DATA"
    PUBLIC = "PUBLIC"


def _safe_identifier(value: object, code: str) -> str:
    if not isinstance(value, str) or _SAFE_IDENTIFIER.fullmatch(value) is None:
        raise AdmissionError(code)
    return value


def _aware_utc(value: object, code: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise AdmissionError(code)
    return value.astimezone(UTC)


def _date_only(value: object, code: str) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise AdmissionError(code)
    return value


def _timezone(value: object, code: str) -> str:
    if not isinstance(value, str) or not value:
        raise AdmissionError(code)
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise AdmissionError(code) from exc
    return value


def _uuid(value: object, code: str) -> str:
    if not isinstance(value, str):
        raise AdmissionError(code)
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise AdmissionError(code) from exc


def _sha(value: object, code: str) -> str:
    if not isinstance(value, str) or _HEX_SHA256.fullmatch(value) is None:
        raise AdmissionError(code)
    return value


@dataclass(frozen=True, slots=True)
class DatasetDeclaration:
    dataset_id: str
    tenant_id: str
    uploader_account_id: str
    source_internal_id: str
    marketplace: str
    report_type: str
    reporting_period_start: date
    reporting_period_end: date
    timezone: str
    original_file_sha256: str
    original_size_bytes: int
    expected_row_count: int | None
    control_totals_sha256: str | None
    data_categories: tuple[str, ...]
    sensitivity: DatasetSensitivity
    owner_authority_reference: str
    lawful_authority_attested: bool
    retention_deadline: datetime
    declared_at: datetime

    def __post_init__(self) -> None:
        _uuid(self.dataset_id, "DATASET_ID_INVALID")
        _safe_identifier(self.tenant_id, "DATASET_TENANT_INVALID")
        _safe_identifier(self.uploader_account_id, "DATASET_UPLOADER_INVALID")
        _safe_identifier(self.source_internal_id, "DATASET_SOURCE_ID_INVALID")
        _safe_identifier(self.marketplace, "DATASET_MARKETPLACE_INVALID")
        _safe_identifier(self.report_type, "DATASET_REPORT_TYPE_INVALID")
        start = _date_only(
            self.reporting_period_start,
            "DATASET_REPORTING_PERIOD_INVALID",
        )
        end = _date_only(
            self.reporting_period_end,
            "DATASET_REPORTING_PERIOD_INVALID",
        )
        if end < start:
            raise AdmissionError("DATASET_REPORTING_PERIOD_INVALID")
        _timezone(self.timezone, "DATASET_TIMEZONE_INVALID")
        _sha(self.original_file_sha256, "DATASET_FILE_HASH_INVALID")
        if (
            not isinstance(self.original_size_bytes, int)
            or isinstance(self.original_size_bytes, bool)
            or self.original_size_bytes < 1
        ):
            raise AdmissionError("DATASET_FILE_SIZE_INVALID")
        if self.expected_row_count is not None and (
            not isinstance(self.expected_row_count, int)
            or isinstance(self.expected_row_count, bool)
            or self.expected_row_count < 0
        ):
            raise AdmissionError("DATASET_EXPECTED_ROWS_INVALID")
        if self.control_totals_sha256 is not None:
            _sha(
                self.control_totals_sha256,
                "DATASET_CONTROL_TOTALS_HASH_INVALID",
            )
        if not isinstance(self.data_categories, tuple) or not self.data_categories:
            raise AdmissionError("DATASET_CATEGORIES_REQUIRED")
        categories = tuple(
            _safe_identifier(item, "DATASET_CATEGORY_INVALID")
            for item in self.data_categories
        )
        if len(set(categories)) != len(categories):
            raise AdmissionError("DATASET_CATEGORY_DUPLICATE")
        if not isinstance(self.sensitivity, DatasetSensitivity):
            raise AdmissionError("DATASET_SENSITIVITY_INVALID")
        if self.sensitivity is DatasetSensitivity.COMMERCIAL_WITH_PERSONAL_DATA:
            raise AdmissionError("DATASET_PERSONAL_DATA_NOT_APPROVED")
        _safe_identifier(
            self.owner_authority_reference,
            "DATASET_AUTHORITY_REFERENCE_INVALID",
        )
        if self.lawful_authority_attested is not True:
            raise AdmissionError("DATASET_AUTHORITY_ATTESTATION_REQUIRED")
        retention = _aware_utc(
            self.retention_deadline,
            "DATASET_RETENTION_TIMEZONE_REQUIRED",
        )
        declared = _aware_utc(
            self.declared_at,
            "DATASET_DECLARED_TIMEZONE_REQUIRED",
        )
        if retention <= declared:
            raise AdmissionError("DATASET_RETENTION_DEADLINE_INVALID")


@dataclass(frozen=True, slots=True)
class StorageControlEvidence:
    evidence_id: str
    tenant_id: str
    dataset_id: str
    original_file_sha256: str
    storage_key_sha256: str
    transport_encrypted: bool
    encryption_at_rest: bool
    tenant_scoped_paths: bool
    immutable_original: bool
    separated_quarantine_and_admitted_zones: bool
    least_privilege_credentials: bool
    verified_at: datetime
    verifier_account_id: str

    def __post_init__(self) -> None:
        _safe_identifier(self.evidence_id, "STORAGE_EVIDENCE_ID_INVALID")
        _safe_identifier(self.tenant_id, "STORAGE_EVIDENCE_TENANT_INVALID")
        _uuid(self.dataset_id, "STORAGE_EVIDENCE_DATASET_INVALID")
        _sha(
            self.original_file_sha256,
            "STORAGE_EVIDENCE_FILE_HASH_INVALID",
        )
        _sha(self.storage_key_sha256, "STORAGE_EVIDENCE_KEY_HASH_INVALID")
        _safe_identifier(
            self.verifier_account_id,
            "STORAGE_EVIDENCE_VERIFIER_INVALID",
        )
        _aware_utc(self.verified_at, "STORAGE_EVIDENCE_TIMEZONE_REQUIRED")
        for value in (
            self.transport_encrypted,
            self.encryption_at_rest,
            self.tenant_scoped_paths,
            self.immutable_original,
            self.separated_quarantine_and_admitted_zones,
            self.least_privilege_credentials,
        ):
            if not isinstance(value, bool):
                raise AdmissionError("STORAGE_EVIDENCE_BOOLEAN_INVALID")

    @property
    def complete(self) -> bool:
        return all(
            (
                self.transport_encrypted,
                self.encryption_at_rest,
                self.tenant_scoped_paths,
                self.immutable_original,
                self.separated_quarantine_and_admitted_zones,
                self.least_privilege_credentials,
            )
        )


@dataclass(frozen=True, slots=True)
class DatasetControlEvidence:
    evidence_id: str
    tenant_id: str
    dataset_id: str
    original_file_sha256: str
    owner_authority_reference: str
    reporting_period_start: date
    reporting_period_end: date
    timezone: str
    control_totals_sha256: str | None
    policy_content_hash: str
    workbook_sha256: str
    structural_fingerprint_sha256: str
    matched_schema_id: str
    matched_schema_version: str
    matched_schema_authority_reference: str
    source_authority_verified: bool
    report_period_verified: bool
    control_totals_verified: bool
    direct_identifiers_absent_or_approved: bool
    malware_scan_clean: bool
    malware_scan_evidence_sha256: str
    verified_at: datetime
    verifier_account_id: str

    def __post_init__(self) -> None:
        _safe_identifier(self.evidence_id, "DATASET_EVIDENCE_ID_INVALID")
        _safe_identifier(self.tenant_id, "DATASET_EVIDENCE_TENANT_INVALID")
        _uuid(self.dataset_id, "DATASET_EVIDENCE_DATASET_INVALID")
        _sha(self.original_file_sha256, "DATASET_EVIDENCE_FILE_HASH_INVALID")
        _safe_identifier(
            self.owner_authority_reference,
            "DATASET_EVIDENCE_AUTHORITY_REFERENCE_INVALID",
        )
        start = _date_only(
            self.reporting_period_start,
            "DATASET_EVIDENCE_REPORTING_PERIOD_INVALID",
        )
        end = _date_only(
            self.reporting_period_end,
            "DATASET_EVIDENCE_REPORTING_PERIOD_INVALID",
        )
        if end < start:
            raise AdmissionError("DATASET_EVIDENCE_REPORTING_PERIOD_INVALID")
        _timezone(self.timezone, "DATASET_EVIDENCE_TIMEZONE_INVALID")
        if self.control_totals_sha256 is not None:
            _sha(
                self.control_totals_sha256,
                "DATASET_EVIDENCE_CONTROL_TOTALS_HASH_INVALID",
            )
        _sha(self.policy_content_hash, "DATASET_EVIDENCE_POLICY_HASH_INVALID")
        _sha(self.workbook_sha256, "DATASET_EVIDENCE_WORKBOOK_HASH_INVALID")
        _sha(
            self.structural_fingerprint_sha256,
            "DATASET_EVIDENCE_FINGERPRINT_HASH_INVALID",
        )
        _safe_identifier(
            self.matched_schema_id,
            "DATASET_EVIDENCE_SCHEMA_ID_INVALID",
        )
        _safe_identifier(
            self.matched_schema_version,
            "DATASET_EVIDENCE_SCHEMA_VERSION_INVALID",
        )
        _safe_identifier(
            self.matched_schema_authority_reference,
            "DATASET_EVIDENCE_SCHEMA_AUTHORITY_INVALID",
        )
        _sha(
            self.malware_scan_evidence_sha256,
            "DATASET_EVIDENCE_MALWARE_HASH_INVALID",
        )
        _safe_identifier(
            self.verifier_account_id,
            "DATASET_EVIDENCE_VERIFIER_INVALID",
        )
        _aware_utc(self.verified_at, "DATASET_EVIDENCE_TIMEZONE_REQUIRED")
        for value in (
            self.source_authority_verified,
            self.report_period_verified,
            self.control_totals_verified,
            self.direct_identifiers_absent_or_approved,
            self.malware_scan_clean,
        ):
            if not isinstance(value, bool):
                raise AdmissionError("DATASET_EVIDENCE_BOOLEAN_INVALID")

    @property
    def complete(self) -> bool:
        return all(
            (
                self.source_authority_verified,
                self.report_period_verified,
                self.control_totals_verified,
                self.direct_identifiers_absent_or_approved,
                self.malware_scan_clean,
            )
        )


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    state: DatasetAdmissionState
    actor_account_id: str
    decided_at: datetime
    reason_code: str
    diagnostics: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.state, DatasetAdmissionState):
            raise AdmissionError("DATASET_DECISION_STATE_INVALID")
        _safe_identifier(
            self.actor_account_id,
            "DATASET_DECISION_ACTOR_INVALID",
        )
        _aware_utc(self.decided_at, "DATASET_DECISION_TIMEZONE_REQUIRED")
        _safe_identifier(self.reason_code, "DATASET_DECISION_REASON_INVALID")
        if not isinstance(self.diagnostics, tuple) or any(
            not isinstance(item, str) or not item for item in self.diagnostics
        ):
            raise AdmissionError("DATASET_DECISION_DIAGNOSTICS_INVALID")


@dataclass(frozen=True, slots=True)
class DatasetAdmissionRecord:
    declaration: DatasetDeclaration
    state: DatasetAdmissionState
    policy_id: str | None = None
    policy_version: int | None = None
    policy_content_hash: str | None = None
    inspection: XlsxPackageInspection | None = None
    diagnostics: tuple[str, ...] = ()
    dataset_control_evidence_id: str | None = None
    storage_evidence_id: str | None = None
    storage_key_sha256: str | None = None
    decisions: tuple[AdmissionDecision, ...] = ()

    @property
    def latest_decision(self) -> AdmissionDecision:
        if not self.decisions:
            raise AdmissionError("DATASET_DECISION_HISTORY_MISSING")
        return self.decisions[-1]

    @property
    def reason_code(self) -> str:
        return self.latest_decision.reason_code
