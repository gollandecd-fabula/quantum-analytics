from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
import re

from .identity_contracts import (
    AccountStatus,
    InviteStatus,
    MembershipStatus,
    SessionStatus,
    TenantStatus,
)
from .persistence import (
    PersistedVerifier,
    PersistentAuditEvent,
    PersistentPilotState,
    PilotPersistenceError,
    SessionTokenDigestRecord,
    VerifierPurpose as PersistedVerifierPurpose,
    state_sha256,
)
from .persistence_v2 import (
    AttestedCheckpointReceipt,
    AttestedSqlitePilotIdentityRepository,
)
from .runtime import (
    AuditEventType,
    CredentialVerifierRecord,
    InMemoryPilotIdentityStore,
    PilotAuditEvent,
    VerifierPurpose as RuntimeVerifierPurpose,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")
_MAX_RESTORE_AGE = timedelta(days=365)


class RuntimePersistenceBridgeError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class BridgeCheckpoint:
    receipt: AttestedCheckpointReceipt
    external_attestation_sha256: str
    tenant_count: int
    account_count: int
    session_count: int
    excluded_terminal_invite_count: int

    def __post_init__(self) -> None:
        if type(self.receipt) is not AttestedCheckpointReceipt:
            raise RuntimePersistenceBridgeError("ATTESTED_RECEIPT_REQUIRED")
        if (
            not isinstance(self.external_attestation_sha256, str)
            or _SHA256.fullmatch(self.external_attestation_sha256) is None
            or self.external_attestation_sha256
            != self.receipt.attestation_sha256
        ):
            raise RuntimePersistenceBridgeError(
                "BRIDGE_ATTESTATION_DIGEST_INVALID"
            )
        for value in (
            self.tenant_count,
            self.account_count,
            self.session_count,
            self.excluded_terminal_invite_count,
        ):
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 0
            ):
                raise RuntimePersistenceBridgeError(
                    "BRIDGE_CHECKPOINT_COUNT_INVALID"
                )


@dataclass(frozen=True, slots=True)
class DetachedRestoreGuard:
    expected_attestation_sha256: str
    expected_tenant_ids: tuple[str, ...]
    minimum_checkpoint_created_at: datetime
    maximum_checkpoint_age: timedelta

    def __post_init__(self) -> None:
        if (
            not isinstance(self.expected_attestation_sha256, str)
            or _SHA256.fullmatch(self.expected_attestation_sha256) is None
        ):
            raise RuntimePersistenceBridgeError(
                "RESTORE_ATTESTATION_DIGEST_INVALID"
            )
        if (
            not isinstance(self.expected_tenant_ids, tuple)
            or not self.expected_tenant_ids
            or any(
                not isinstance(tenant_id, str)
                or _SAFE_ID.fullmatch(tenant_id) is None
                for tenant_id in self.expected_tenant_ids
            )
            or len(self.expected_tenant_ids)
            != len(set(self.expected_tenant_ids))
        ):
            raise RuntimePersistenceBridgeError(
                "RESTORE_EXPECTED_TENANTS_INVALID"
            )
        _utc(
            self.minimum_checkpoint_created_at,
            "RESTORE_MINIMUM_TIME_INVALID",
        )
        if (
            not isinstance(self.maximum_checkpoint_age, timedelta)
            or self.maximum_checkpoint_age <= timedelta(0)
            or self.maximum_checkpoint_age > _MAX_RESTORE_AGE
        ):
            raise RuntimePersistenceBridgeError(
                "RESTORE_MAXIMUM_AGE_INVALID"
            )


@dataclass(frozen=True, slots=True)
class QuarantinedRestore:
    store: InMemoryPilotIdentityStore = field(repr=False)
    source_receipt: AttestedCheckpointReceipt
    restored_at: datetime
    source_state_sha256: str
    quarantined_state_sha256: str
    suspended_tenant_count: int
    suspended_account_count: int
    suspended_membership_count: int
    revoked_invite_count: int
    revoked_session_count: int

    def __post_init__(self) -> None:
        if type(self.store) is not InMemoryPilotIdentityStore:
            raise RuntimePersistenceBridgeError(
                "RESTORED_STORE_INVALID"
            )
        _utc(self.restored_at, "RESTORE_TIME_INVALID")
        for digest in (
            self.source_state_sha256,
            self.quarantined_state_sha256,
        ):
            if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
                raise RuntimePersistenceBridgeError(
                    "RESTORE_STATE_DIGEST_INVALID"
                )
        for value in (
            self.suspended_tenant_count,
            self.suspended_account_count,
            self.suspended_membership_count,
            self.revoked_invite_count,
            self.revoked_session_count,
        ):
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 0
            ):
                raise RuntimePersistenceBridgeError(
                    "RESTORE_COUNT_INVALID"
                )


class SyntheticRuntimePersistenceBridge:
    """Atomic synthetic checkpoint export and detached quarantine restore.

    It never swaps a live runtime store and never activates restored principals.
    """

    def capture_state(
        self,
        store: InMemoryPilotIdentityStore,
    ) -> PersistentPilotState:
        runtime_store = _store(store)
        with runtime_store._lock:
            self._assert_secondary_indexes(runtime_store)
            try:
                return PersistentPilotState(
                    tenants=tuple(runtime_store._tenants.values()),
                    accounts=tuple(runtime_store._accounts.values()),
                    memberships=tuple(runtime_store._memberships.values()),
                    invites=tuple(
                        item
                        for item in runtime_store._invites.values()
                        if item.status is InviteStatus.ISSUED
                    ),
                    sessions=tuple(runtime_store._sessions.values()),
                    verifiers=tuple(
                        _persisted_verifier(item)
                        for item in runtime_store._verifiers.values()
                    ),
                    session_token_digests=tuple(
                        SessionTokenDigestRecord(
                            session_id=session_id,
                            token_sha256=digest,
                        )
                        for digest, session_id
                        in runtime_store._session_digest_owners.items()
                    ),
                    audit_events=tuple(
                        _persistent_audit(item)
                        for item in runtime_store._audit_events
                    ),
                )
            except PilotPersistenceError as exc:
                raise RuntimePersistenceBridgeError(
                    f"RUNTIME_STATE_INVALID:{exc.code}"
                ) from exc

    def save_checkpoint(
        self,
        *,
        repository: AttestedSqlitePilotIdentityRepository,
        store: InMemoryPilotIdentityStore,
        checkpoint_id: str,
        created_at: datetime,
    ) -> BridgeCheckpoint:
        repo = _repository(repository)
        runtime_store = _store(store)
        with runtime_store._lock:
            excluded_terminal_invites = sum(
                item.status is not InviteStatus.ISSUED
                for item in runtime_store._invites.values()
            )
            state = self.capture_state(runtime_store)
        receipt = repo.save_checkpoint(
            checkpoint_id=checkpoint_id,
            state=state,
            created_at=created_at,
        )
        return BridgeCheckpoint(
            receipt=receipt,
            external_attestation_sha256=receipt.attestation_sha256,
            tenant_count=len(state.tenants),
            account_count=len(state.accounts),
            session_count=len(state.sessions),
            excluded_terminal_invite_count=excluded_terminal_invites,
        )

    def restore_quarantined(
        self,
        *,
        repository: AttestedSqlitePilotIdentityRepository,
        receipt: AttestedCheckpointReceipt,
        guard: DetachedRestoreGuard,
        restored_at: datetime,
    ) -> QuarantinedRestore:
        repo = _repository(repository)
        if type(receipt) is not AttestedCheckpointReceipt:
            raise RuntimePersistenceBridgeError(
                "ATTESTED_RECEIPT_REQUIRED"
            )
        if type(guard) is not DetachedRestoreGuard:
            raise RuntimePersistenceBridgeError("RESTORE_GUARD_REQUIRED")
        current = _utc(restored_at, "RESTORE_TIME_INVALID")
        checkpoint_time = receipt.created_at.astimezone(UTC)
        minimum = guard.minimum_checkpoint_created_at.astimezone(UTC)
        if receipt.attestation_sha256 != guard.expected_attestation_sha256:
            raise RuntimePersistenceBridgeError(
                "RESTORE_ATTESTATION_MISMATCH"
            )
        if checkpoint_time < minimum:
            raise RuntimePersistenceBridgeError(
                "RESTORE_ROLLBACK_GUARD_REJECTED"
            )
        if current < checkpoint_time:
            raise RuntimePersistenceBridgeError(
                "RESTORE_TIME_REGRESSION"
            )
        if current - checkpoint_time > guard.maximum_checkpoint_age:
            raise RuntimePersistenceBridgeError(
                "RESTORE_CHECKPOINT_TOO_OLD"
            )

        state = repo.load_checkpoint(receipt)
        actual_tenants = tuple(
            sorted(tenant.tenant_id for tenant in state.tenants)
        )
        if actual_tenants != tuple(sorted(guard.expected_tenant_ids)):
            raise RuntimePersistenceBridgeError(
                "RESTORE_TENANT_SET_MISMATCH"
            )

        restored_store, counters = self._quarantined_store(state)
        quarantined_state = self.capture_state(restored_store)
        return QuarantinedRestore(
            store=restored_store,
            source_receipt=receipt,
            restored_at=current,
            source_state_sha256=receipt.state_sha256,
            quarantined_state_sha256=state_sha256(quarantined_state),
            suspended_tenant_count=counters["tenants"],
            suspended_account_count=counters["accounts"],
            suspended_membership_count=counters["memberships"],
            revoked_invite_count=counters["invites"],
            revoked_session_count=counters["sessions"],
        )

    @staticmethod
    def _assert_secondary_indexes(
        store: InMemoryPilotIdentityStore,
    ) -> None:
        aliases = _casefold_index(
            store._tenants.values(),
            "tenant_alias",
            "tenant_id",
            "RUNTIME_TENANT_ALIAS_CONFLICT",
        )
        pseudonyms = _casefold_index(
            store._accounts.values(),
            "pseudonym",
            "account_id",
            "RUNTIME_PSEUDONYM_CONFLICT",
        )
        memberships = {
            (item.tenant_id, item.account_id): item.membership_id
            for item in store._memberships.values()
        }
        if len(memberships) != len(store._memberships):
            raise RuntimePersistenceBridgeError(
                "RUNTIME_MEMBERSHIP_INDEX_CONFLICT"
            )
        if aliases != store._tenant_alias_owners:
            raise RuntimePersistenceBridgeError(
                "RUNTIME_TENANT_ALIAS_INDEX_MISMATCH"
            )
        if pseudonyms != store._pseudonym_owners:
            raise RuntimePersistenceBridgeError(
                "RUNTIME_PSEUDONYM_INDEX_MISMATCH"
            )
        if memberships != store._membership_by_tenant_account:
            raise RuntimePersistenceBridgeError(
                "RUNTIME_MEMBERSHIP_INDEX_MISMATCH"
            )
        session_ids = set(store._sessions)
        digest_session_ids = set(store._session_digest_owners.values())
        if session_ids != digest_session_ids:
            raise RuntimePersistenceBridgeError(
                "RUNTIME_SESSION_DIGEST_INDEX_MISMATCH"
            )
        if len(store._session_digest_owners) != len(session_ids):
            raise RuntimePersistenceBridgeError(
                "RUNTIME_SESSION_DIGEST_INDEX_CONFLICT"
            )

    def _quarantined_store(
        self,
        state: PersistentPilotState,
    ) -> tuple[InMemoryPilotIdentityStore, dict[str, int]]:
        store = InMemoryPilotIdentityStore()
        tenants = tuple(
            replace(
                item,
                status=(
                    TenantStatus.SUSPENDED
                    if item.status in {
                        TenantStatus.PROVISIONING,
                        TenantStatus.ACTIVE,
                    }
                    else item.status
                ),
            )
            for item in state.tenants
        )
        accounts = tuple(
            replace(
                item,
                authentication_epoch=item.authentication_epoch + 1,
                status=(
                    AccountStatus.SUSPENDED
                    if item.status in {
                        AccountStatus.INVITED,
                        AccountStatus.ACTIVE,
                    }
                    else item.status
                ),
            )
            for item in state.accounts
        )
        memberships = tuple(
            replace(
                item,
                status=(
                    MembershipStatus.SUSPENDED
                    if item.status is MembershipStatus.ACTIVE
                    else item.status
                ),
            )
            for item in state.memberships
        )
        invites = tuple(
            replace(
                item,
                status=(
                    InviteStatus.REVOKED
                    if item.status is InviteStatus.ISSUED
                    else item.status
                ),
            )
            for item in state.invites
        )
        sessions = tuple(
            replace(item, status=SessionStatus.REVOKED)
            for item in state.sessions
        )
        verifiers = tuple(_runtime_verifier(item) for item in state.verifiers)
        audits = tuple(_runtime_audit(item) for item in state.audit_events)

        with store._lock:
            store._tenants = {item.tenant_id: item for item in tenants}
            store._tenant_alias_owners = _casefold_index(
                tenants,
                "tenant_alias",
                "tenant_id",
                "RESTORE_TENANT_ALIAS_CONFLICT",
            )
            store._accounts = {item.account_id: item for item in accounts}
            store._pseudonym_owners = _casefold_index(
                accounts,
                "pseudonym",
                "account_id",
                "RESTORE_PSEUDONYM_CONFLICT",
            )
            store._memberships = {
                item.membership_id: item for item in memberships
            }
            store._membership_by_tenant_account = {}
            for item in memberships:
                key = (item.tenant_id, item.account_id)
                if key in store._membership_by_tenant_account:
                    raise RuntimePersistenceBridgeError(
                        "RESTORE_MEMBERSHIP_CONFLICT"
                    )
                store._membership_by_tenant_account[
                    key
                ] = item.membership_id
            store._invites = {item.invite_id: item for item in invites}
            store._sessions = {item.session_id: item for item in sessions}
            store._session_digest_owners = {
                item.token_sha256: item.session_id
                for item in state.session_token_digests
            }
            store._verifiers = {
                item.record_id: item for item in verifiers
            }
            store._audit_events = list(audits)

        self._assert_secondary_indexes(store)
        return store, {
            "tenants": sum(
                item.status is TenantStatus.SUSPENDED
                for item in tenants
            ),
            "accounts": sum(
                item.status is AccountStatus.SUSPENDED
                for item in accounts
            ),
            "memberships": sum(
                item.status is MembershipStatus.SUSPENDED
                for item in memberships
            ),
            "invites": sum(
                original.status is InviteStatus.ISSUED
                and restored.status is InviteStatus.REVOKED
                for original, restored in zip(state.invites, invites)
            ),
            "sessions": len(sessions),
        }


def _store(value: object) -> InMemoryPilotIdentityStore:
    if type(value) is not InMemoryPilotIdentityStore:
        raise RuntimePersistenceBridgeError("RUNTIME_STORE_REQUIRED")
    return value


def _repository(
    value: object,
) -> AttestedSqlitePilotIdentityRepository:
    if type(value) is not AttestedSqlitePilotIdentityRepository:
        raise RuntimePersistenceBridgeError(
            "ATTESTED_REPOSITORY_REQUIRED"
        )
    return value


def _utc(value: object, code: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise RuntimePersistenceBridgeError(code)
    return value.astimezone(UTC)


def _casefold_index(
    items,
    value_attribute: str,
    id_attribute: str,
    conflict_code: str,
) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in items:
        key = getattr(item, value_attribute).casefold()
        if key in result:
            raise RuntimePersistenceBridgeError(conflict_code)
        result[key] = getattr(item, id_attribute)
    return result


def _persisted_verifier(
    item: CredentialVerifierRecord,
) -> PersistedVerifier:
    if not isinstance(item, CredentialVerifierRecord):
        raise RuntimePersistenceBridgeError(
            "RUNTIME_VERIFIER_TYPE_INVALID"
        )
    try:
        purpose = PersistedVerifierPurpose(item.purpose.value)
    except (AttributeError, ValueError) as exc:
        raise RuntimePersistenceBridgeError(
            "RUNTIME_VERIFIER_PURPOSE_UNSUPPORTED"
        ) from exc
    return PersistedVerifier(
        record_id=item.record_id,
        purpose=purpose,
        algorithm=item.algorithm,
        verifier=item.verifier,
        created_at=item.created_at,
        superseded_at=item.superseded_at,
    )


def _runtime_verifier(
    item: PersistedVerifier,
) -> CredentialVerifierRecord:
    try:
        purpose = RuntimeVerifierPurpose(item.purpose.value)
    except (AttributeError, ValueError) as exc:
        raise RuntimePersistenceBridgeError(
            "PERSISTED_VERIFIER_PURPOSE_UNSUPPORTED"
        ) from exc
    return CredentialVerifierRecord(
        record_id=item.record_id,
        purpose=purpose,
        algorithm=item.algorithm,
        verifier=item.verifier,
        created_at=item.created_at,
        superseded_at=item.superseded_at,
    )


def _persistent_audit(item: PilotAuditEvent) -> PersistentAuditEvent:
    if not isinstance(item, PilotAuditEvent):
        raise RuntimePersistenceBridgeError(
            "RUNTIME_AUDIT_TYPE_INVALID"
        )
    return PersistentAuditEvent(
        event_id=item.event_id,
        event_type=item.event_type.value,
        actor_reference=item.actor_reference,
        tenant_id=item.tenant_id,
        subject_id=item.subject_id,
        occurred_at=item.occurred_at,
        codes=item.codes,
    )


def _runtime_audit(item: PersistentAuditEvent) -> PilotAuditEvent:
    try:
        event_type = AuditEventType(item.event_type)
    except ValueError as exc:
        raise RuntimePersistenceBridgeError(
            "PERSISTED_AUDIT_EVENT_UNSUPPORTED"
        ) from exc
    return PilotAuditEvent(
        event_id=item.event_id,
        event_type=event_type,
        actor_reference=item.actor_reference,
        tenant_id=item.tenant_id,
        subject_id=item.subject_id,
        occurred_at=item.occurred_at,
        codes=item.codes,
    )


__all__ = [
    "BridgeCheckpoint",
    "DetachedRestoreGuard",
    "QuarantinedRestore",
    "RuntimePersistenceBridgeError",
    "SyntheticRuntimePersistenceBridge",
]
