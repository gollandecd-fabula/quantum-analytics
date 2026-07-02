from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
import hmac
from threading import RLock

from quantum.access import TenantContext

from ._admission_contracts_v2 import (
    _ALLOWED_TRANSITIONS,
    AdmissionDecision,
    AdmissionError,
    DatasetAdmissionRecord,
    DatasetAdmissionState,
    DatasetDeclaration,
    _uuid,
)
from .xlsx_inspection import XlsxPackageInspector


class _AdmissionRegistryBaseV2:
    def __init__(self, inspector: XlsxPackageInspector | None = None) -> None:
        self._inspector = inspector or XlsxPackageInspector()
        self._records: dict[tuple[str, str], DatasetAdmissionRecord] = {}
        self._original_digest_owners: dict[tuple[str, str], str] = {}
        self._source_identity_owners: dict[
            tuple[str, str, str, str, str, date, date],
            str,
        ] = {}
        self._workbook_digest_owners: dict[tuple[str, str], str] = {}
        self._dataset_evidence_id_owners: dict[tuple[str, str], str] = {}
        self._storage_evidence_id_owners: dict[tuple[str, str], str] = {}
        self._lock = RLock()

    @staticmethod
    def _require_tenant(tenant: TenantContext) -> TenantContext:
        if not isinstance(tenant, TenantContext):
            raise AdmissionError("TENANT_CONTEXT_REQUIRED")
        return tenant

    @staticmethod
    def _decision(
        *,
        state: DatasetAdmissionState,
        actor: str,
        at: datetime,
        reason: str,
        diagnostics: tuple[str, ...] = (),
    ) -> AdmissionDecision:
        return AdmissionDecision(
            state=state,
            actor_account_id=actor,
            decided_at=at,
            reason_code=reason,
            diagnostics=diagnostics,
        )

    @classmethod
    def _transition(
        cls,
        record: DatasetAdmissionRecord,
        state: DatasetAdmissionState,
        *,
        actor: str,
        at: datetime,
        reason: str,
        diagnostics: tuple[str, ...] = (),
        **changes: object,
    ) -> DatasetAdmissionRecord:
        if state.value not in _ALLOWED_TRANSITIONS[record.state.value]:
            raise AdmissionError("DATASET_STATE_TRANSITION_INVALID")
        decision = cls._decision(
            state=state,
            actor=actor,
            at=at,
            reason=reason,
            diagnostics=diagnostics,
        )
        return replace(
            record,
            state=state,
            diagnostics=diagnostics,
            decisions=(*record.decisions, decision),
            **changes,
        )

    @classmethod
    def _record_same_state_decision(
        cls,
        record: DatasetAdmissionRecord,
        *,
        actor: str,
        at: datetime,
        reason: str,
        diagnostics: tuple[str, ...],
        **changes: object,
    ) -> DatasetAdmissionRecord:
        decision = cls._decision(
            state=record.state,
            actor=actor,
            at=at,
            reason=reason,
            diagnostics=diagnostics,
        )
        return replace(
            record,
            diagnostics=diagnostics,
            decisions=(*record.decisions, decision),
            **changes,
        )

    @staticmethod
    def _require_monotonic_time(
        record: DatasetAdmissionRecord,
        at: datetime,
    ) -> None:
        if at < record.latest_decision.decided_at:
            raise AdmissionError("DATASET_DECISION_TIME_REGRESSION")

    def _claim_workbook_digest(
        self,
        *,
        tenant_id: str,
        dataset_id: str,
        workbook_sha256: str,
    ) -> bool:
        key = (tenant_id, workbook_sha256)
        existing = self._workbook_digest_owners.get(key)
        if existing is not None and existing != dataset_id:
            return False
        self._workbook_digest_owners[key] = dataset_id
        return True

    def declare(
        self,
        *,
        tenant: TenantContext,
        declaration: DatasetDeclaration,
    ) -> DatasetAdmissionRecord:
        tenant = self._require_tenant(tenant)
        if not isinstance(declaration, DatasetDeclaration):
            raise AdmissionError("DATASET_DECLARATION_REQUIRED")
        try:
            tenant.require_tenant(declaration.tenant_id)
        except ValueError as exc:
            raise AdmissionError("DATASET_NOT_FOUND") from exc
        if not hmac.compare_digest(
            tenant.account_id.encode("utf-8"),
            declaration.uploader_account_id.encode("utf-8"),
        ):
            raise AdmissionError("DATASET_UPLOADER_SCOPE_MISMATCH")
        normalized_dataset_id = _uuid(
            declaration.dataset_id,
            "DATASET_ID_INVALID",
        )
        if declaration.dataset_id != normalized_dataset_id:
            declaration = replace(
                declaration,
                dataset_id=normalized_dataset_id,
            )
        key = (tenant.tenant_id, normalized_dataset_id)
        digest_key = (tenant.tenant_id, declaration.original_file_sha256)
        source_key = (
            tenant.tenant_id,
            declaration.uploader_account_id,
            declaration.marketplace,
            declaration.report_type,
            declaration.source_internal_id,
            declaration.reporting_period_start,
            declaration.reporting_period_end,
        )
        with self._lock:
            existing = self._records.get(key)
            if existing is not None:
                if existing.declaration == declaration:
                    return existing
                raise AdmissionError("DATASET_DECLARATION_CONFLICT")
            digest_owner = self._original_digest_owners.get(digest_key)
            if digest_owner is not None and digest_owner != normalized_dataset_id:
                raise AdmissionError("DATASET_ORIGINAL_REPLAY_DETECTED")
            source_owner = self._source_identity_owners.get(source_key)
            if source_owner is not None and source_owner != normalized_dataset_id:
                raise AdmissionError("DATASET_SOURCE_REPLAY_DETECTED")
            decision = self._decision(
                state=DatasetAdmissionState.DECLARED,
                actor=tenant.account_id,
                at=declaration.declared_at,
                reason="DATASET_DECLARED",
            )
            record = DatasetAdmissionRecord(
                declaration=declaration,
                state=DatasetAdmissionState.DECLARED,
                decisions=(decision,),
            )
            self._records[key] = record
            self._original_digest_owners[digest_key] = normalized_dataset_id
            self._source_identity_owners[source_key] = normalized_dataset_id
            return record

    def get(
        self,
        *,
        tenant: TenantContext,
        dataset_id: str,
    ) -> DatasetAdmissionRecord:
        tenant = self._require_tenant(tenant)
        normalized = _uuid(dataset_id, "DATASET_ID_INVALID")
        with self._lock:
            record = self._records.get((tenant.tenant_id, normalized))
        if record is None:
            raise AdmissionError("DATASET_NOT_FOUND")
        return record
