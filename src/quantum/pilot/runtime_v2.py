from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from .identity_contracts import AccountStatus, InviteStatus, SessionStatus
from .runtime import (
    AcceptedInvite,
    AuditEventType,
    CredentialHasher,
    CredentialVerifierRecord,
    InMemoryPilotIdentityStore,
    IssuedSession,
    PilotAuditEvent,
    PilotIdentityRuntime as PilotIdentityRuntimeV1,
    PilotRuntimeError,
    PilotRuntimeSnapshot,
    VerifierPurpose,
    _aware_utc,
    _pseudonym,
    _secret,
    _session_token,
)


@dataclass(frozen=True, slots=True)
class PilotRuntimeLimits:
    max_tenants: int = 100
    max_accounts: int = 10_000
    max_memberships: int = 10_000
    max_invites: int = 20_000
    max_sessions: int = 50_000
    max_verifiers: int = 30_000
    max_audit_events: int = 100_000
    max_active_sessions_per_account: int = 10

    def __post_init__(self) -> None:
        for value in (
            self.max_tenants,
            self.max_accounts,
            self.max_memberships,
            self.max_invites,
            self.max_sessions,
            self.max_verifiers,
            self.max_audit_events,
            self.max_active_sessions_per_account,
        ):
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 1
            ):
                raise PilotRuntimeError("RUNTIME_LIMIT_INVALID")
        if self.max_active_sessions_per_account > self.max_sessions:
            raise PilotRuntimeError("RUNTIME_LIMIT_INVALID")


class PilotIdentityRuntime(PilotIdentityRuntimeV1):
    """Resource-bounded P2.1 runtime. P2.1 callers must use this version."""

    def __init__(
        self,
        *,
        hasher: CredentialHasher,
        store: InMemoryPilotIdentityStore | None = None,
        session_lifetime=None,
        limits: PilotRuntimeLimits | None = None,
    ) -> None:
        kwargs = {"hasher": hasher, "store": store}
        if session_lifetime is not None:
            kwargs["session_lifetime"] = session_lifetime
        super().__init__(**kwargs)
        self._limits = limits or PilotRuntimeLimits()
        if not isinstance(self._limits, PilotRuntimeLimits):
            raise PilotRuntimeError("RUNTIME_LIMITS_REQUIRED")

    def bootstrap_tenant_with_owner_invite(self, **kwargs):
        with self._store._lock:
            self._capacity(
                len(self._store._tenants),
                1,
                self._limits.max_tenants,
                "TENANT_CAPACITY_EXCEEDED",
            )
            self._capacity(
                len(self._store._invites),
                1,
                self._limits.max_invites,
                "INVITE_CAPACITY_EXCEEDED",
            )
            self._capacity(
                len(self._store._verifiers),
                1,
                self._limits.max_verifiers,
                "VERIFIER_CAPACITY_EXCEEDED",
            )
            self._audit_capacity(2)
            return super().bootstrap_tenant_with_owner_invite(**kwargs)

    def issue_invite(self, **kwargs):
        with self._store._lock:
            self._capacity(
                len(self._store._invites),
                1,
                self._limits.max_invites,
                "INVITE_CAPACITY_EXCEEDED",
            )
            self._capacity(
                len(self._store._verifiers),
                1,
                self._limits.max_verifiers,
                "VERIFIER_CAPACITY_EXCEEDED",
            )
            self._audit_capacity(1)
            return super().issue_invite(**kwargs)

    def accept_invite(self, **kwargs) -> AcceptedInvite:
        invite_id = kwargs.get("invite_id")
        with self._store._lock:
            invite = self._store._invites.get(invite_id)
            if invite is None or invite.status is not InviteStatus.ISSUED:
                return super().accept_invite(**kwargs)
            invite_verifier_id = invite.secret_verifier_record_id
            self._capacity(
                len(self._store._accounts),
                1,
                self._limits.max_accounts,
                "ACCOUNT_CAPACITY_EXCEEDED",
            )
            self._capacity(
                len(self._store._memberships),
                1,
                self._limits.max_memberships,
                "MEMBERSHIP_CAPACITY_EXCEEDED",
            )
            self._capacity(
                len(self._store._verifiers),
                2,
                self._limits.max_verifiers,
                "VERIFIER_CAPACITY_EXCEEDED",
            )
            self._audit_capacity(1)
            accepted = super().accept_invite(**kwargs)
            self._store._verifiers.pop(invite_verifier_id, None)
            return accepted

    def authenticate(self, **kwargs) -> IssuedSession:
        pseudonym = kwargs.get("pseudonym")
        now = kwargs.get("now")
        current = _aware_utc(now, "AUTHENTICATION_TIMEZONE_REQUIRED")
        try:
            normalized = _pseudonym(pseudonym)
        except PilotRuntimeError:
            return super().authenticate(**kwargs)
        with self._store._lock:
            account_id = self._store._pseudonym_owners.get(normalized.casefold())
            account = (
                self._store._accounts.get(account_id)
                if account_id is not None
                else None
            )
            if account is not None and account.status is AccountStatus.ACTIVE:
                self._prune_sessions(current)
                self._capacity(
                    len(self._store._sessions),
                    1,
                    self._limits.max_sessions,
                    "SESSION_CAPACITY_EXCEEDED",
                )
                active_for_account = sum(
                    session.account_id == account.account_id
                    and session.status is SessionStatus.ACTIVE
                    and current < session.expires_at.astimezone(UTC)
                    for session in self._store._sessions.values()
                )
                self._capacity(
                    active_for_account,
                    1,
                    self._limits.max_active_sessions_per_account,
                    "ACCOUNT_ACTIVE_SESSION_CAPACITY_EXCEEDED",
                )
                self._audit_capacity(1)
            return super().authenticate(**kwargs)

    def revoke_session(self, **kwargs):
        token = _session_token(kwargs.get("session_token"))
        with self._store._lock:
            try:
                session = self._session_from_token_locked(token)
            except PilotRuntimeError:
                return super().revoke_session(**kwargs)
            if session.status is SessionStatus.ACTIVE:
                self._audit_capacity(1)
            return super().revoke_session(**kwargs)

    def rotate_credentials_with_recovery(self, **kwargs):
        pseudonym = _pseudonym(kwargs.get("pseudonym"))
        recovery_key = _secret(
            kwargs.get("recovery_key"),
            minimum=1,
            maximum=256,
            code="RECOVERY_FAILED",
        )
        new_password = _secret(
            kwargs.get("new_password"),
            minimum=12,
            maximum=256,
            code="PASSWORD_INVALID",
        )
        new_recovery = _secret(
            kwargs.get("new_recovery_key"),
            minimum=24,
            maximum=256,
            code="RECOVERY_KEY_INVALID",
        )
        with self._store._lock:
            account_id = self._store._pseudonym_owners.get(pseudonym.casefold())
            account = (
                self._store._accounts.get(account_id)
                if account_id is not None
                else None
            )
            if account is None or account.status is not AccountStatus.ACTIVE:
                return super().rotate_credentials_with_recovery(**kwargs)
            old_password = self._active_verifier(
                account.credential_record_id,
                VerifierPurpose.PASSWORD,
                generic_failure="RECOVERY_FAILED",
            )
            old_recovery = self._active_verifier(
                account.recovery_record_id,
                VerifierPurpose.RECOVERY,
                generic_failure="RECOVERY_FAILED",
            )
            if self._verify_secret(old_recovery.verifier, recovery_key):
                if (
                    self._verify_secret(old_password.verifier, new_password)
                    or self._verify_secret(old_recovery.verifier, new_password)
                    or self._verify_secret(old_password.verifier, new_recovery)
                    or self._verify_secret(old_recovery.verifier, new_recovery)
                ):
                    raise PilotRuntimeError("CREDENTIAL_REUSE_FORBIDDEN")
                self._capacity(
                    len(self._store._verifiers),
                    2,
                    self._limits.max_verifiers,
                    "VERIFIER_CAPACITY_EXCEEDED",
                )
                self._audit_capacity(1)
            rotated = super().rotate_credentials_with_recovery(**kwargs)
            self._store._verifiers.pop(old_password.record_id, None)
            self._store._verifiers.pop(old_recovery.record_id, None)
            return rotated

    @staticmethod
    def _capacity(current: int, additional: int, limit: int, code: str) -> None:
        if current + additional > limit:
            raise PilotRuntimeError(code)

    def _audit_capacity(self, additional: int) -> None:
        self._capacity(
            len(self._store._audit_events),
            additional,
            self._limits.max_audit_events,
            "AUDIT_CAPACITY_EXCEEDED",
        )

    def _prune_sessions(self, now: datetime) -> None:
        removable = {
            session_id
            for session_id, session in self._store._sessions.items()
            if session.status is SessionStatus.REVOKED
            or now >= session.expires_at.astimezone(UTC)
        }
        for digest, session_id in tuple(
            self._store._session_digest_owners.items()
        ):
            if session_id in removable:
                self._store._session_digest_owners.pop(digest, None)
        for session_id in removable:
            self._store._sessions.pop(session_id, None)


__all__ = [
    "AcceptedInvite",
    "AuditEventType",
    "CredentialHasher",
    "CredentialVerifierRecord",
    "InMemoryPilotIdentityStore",
    "IssuedSession",
    "PilotAuditEvent",
    "PilotIdentityRuntime",
    "PilotRuntimeError",
    "PilotRuntimeLimits",
    "PilotRuntimeSnapshot",
    "VerifierPurpose",
]
