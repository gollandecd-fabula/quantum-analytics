from __future__ import annotations

from datetime import datetime
import hmac

from quantum.access import TenantContext

from ._admission_access_v2 import _AdmissionAccessMixinV2
from ._admission_contracts_v2 import (
    AdmissionDecision,
    AdmissionError,
    DatasetAdmissionRecord,
    DatasetAdmissionState,
    DatasetControlEvidence,
    DatasetDeclaration,
    DatasetSensitivity,
    StorageControlEvidence,
    _aware_utc,
)
from ._admission_finalize_v2 import finalize_validated_record
from ._admission_registry_base_v2 import _AdmissionRegistryBaseV2
from ._admission_validation_v2 import _AdmissionValidationMixinV2


class RealDatasetAdmissionRegistryV2(
    _AdmissionValidationMixinV2,
    _AdmissionAccessMixinV2,
    _AdmissionRegistryBaseV2,
):
    def get(
        self,
        *,
        tenant: TenantContext,
        dataset_id: str,
    ) -> DatasetAdmissionRecord:
        tenant = self._require_tenant(tenant)
        record = super().get(tenant=tenant, dataset_id=dataset_id)
        if not hmac.compare_digest(
            tenant.account_id.encode("utf-8"),
            record.declaration.uploader_account_id.encode("utf-8"),
        ):
            raise AdmissionError("DATASET_NOT_FOUND")
        return record

    def admit(
        self,
        *,
        tenant: TenantContext,
        dataset_id: str,
        dataset_control_evidence: DatasetControlEvidence,
        storage_evidence: StorageControlEvidence,
        admitted_at: datetime,
    ) -> DatasetAdmissionRecord:
        tenant = self._require_tenant(tenant)
        current = _aware_utc(admitted_at, "DATASET_ADMISSION_TIMEZONE_REQUIRED")
        if not isinstance(dataset_control_evidence, DatasetControlEvidence):
            raise AdmissionError("DATASET_CONTROL_EVIDENCE_REQUIRED")
        if not isinstance(storage_evidence, StorageControlEvidence):
            raise AdmissionError("STORAGE_EVIDENCE_REQUIRED")
        try:
            tenant.require_tenant(dataset_control_evidence.tenant_id)
            tenant.require_tenant(storage_evidence.tenant_id)
        except ValueError as exc:
            raise AdmissionError("DATASET_NOT_FOUND") from exc
        if not dataset_control_evidence.complete:
            raise AdmissionError("DATASET_CONTROLS_INCOMPLETE")
        if not storage_evidence.complete:
            raise AdmissionError("STORAGE_CONTROLS_INCOMPLETE")
        with self._lock:
            record = self.get(tenant=tenant, dataset_id=dataset_id)
            self._require_monotonic_time(record, current)
            return finalize_validated_record(
                self,
                tenant=tenant,
                record=record,
                dataset_control=dataset_control_evidence,
                storage_control=storage_evidence,
                decided_at=current,
            )


RealDatasetAdmissionRegistry = RealDatasetAdmissionRegistryV2

__all__ = [
    "AdmissionDecision",
    "AdmissionError",
    "DatasetAdmissionRecord",
    "DatasetAdmissionState",
    "DatasetControlEvidence",
    "DatasetDeclaration",
    "DatasetSensitivity",
    "RealDatasetAdmissionRegistry",
    "RealDatasetAdmissionRegistryV2",
    "StorageControlEvidence",
]
