from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import hmac
from threading import RLock

from quantum.access import TenantContext

from ._admission_contracts import (
    _ALLOWED_TRANSITIONS,
    AdmissionDecision,
    AdmissionError,
    DatasetAdmissionRecord,
    DatasetAdmissionState,
    DatasetDeclaration,
    _uuid,
)
from .xlsx_inspection import XlsxPackageInspector


class _AdmissionRegistryBase:
    def __init__(self, inspector: XlsxPackageInspector | None = None) -> None:
        self._inspector = inspector or XlsxPackageInspector()
        self._records: dict[tuple[str, str], DatasetAdmissionRecord] = {}
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
        key = (tenant.tenant_id, declaration.dataset_id)
        with self._lock:
            existing = self._records.get(key)
            if existing is not None:
                if existing.declaration == declaration:
                    return existing
                raise AdmissionError("DATASET_DECLARATION_CONFLICT")
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
