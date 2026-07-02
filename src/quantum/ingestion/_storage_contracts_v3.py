from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ._admission_contracts_v2 import AdmissionError, _aware_utc, _safe_identifier, _sha, _uuid


class StorageEnvironment(StrEnum):
    LOCAL_SINGLE_USER = "LOCAL_SINGLE_USER"
    HOSTED_EXTERNAL = "HOSTED_EXTERNAL"


@dataclass(frozen=True, slots=True)
class StorageControlEvidence:
    evidence_id: str
    tenant_id: str
    dataset_id: str
    original_file_sha256: str
    storage_key_sha256: str
    storage_environment: StorageEnvironment
    loopback_only: bool
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
        if not isinstance(self.storage_environment, StorageEnvironment):
            raise AdmissionError("STORAGE_EVIDENCE_ENVIRONMENT_INVALID")
        _safe_identifier(
            self.verifier_account_id,
            "STORAGE_EVIDENCE_VERIFIER_INVALID",
        )
        _aware_utc(self.verified_at, "STORAGE_EVIDENCE_TIMEZONE_REQUIRED")
        for value in (
            self.loopback_only,
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
        common_controls = all(
            (
                self.tenant_scoped_paths,
                self.immutable_original,
                self.separated_quarantine_and_admitted_zones,
                self.least_privilege_credentials,
            )
        )
        if not common_controls:
            return False
        if self.storage_environment is StorageEnvironment.LOCAL_SINGLE_USER:
            return self.loopback_only
        if self.storage_environment is StorageEnvironment.HOSTED_EXTERNAL:
            return (
                not self.loopback_only
                and self.transport_encrypted
                and self.encryption_at_rest
            )
        return False


__all__ = ["StorageControlEvidence", "StorageEnvironment"]
