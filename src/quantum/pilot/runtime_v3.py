from __future__ import annotations

from datetime import UTC

from .identity_contracts import (
    AccountStatus,
    InviteStatus,
    MembershipStatus,
    Permission,
    SessionPrincipal,
    SessionStatus,
    TenantRole,
    TenantStatus,
)
from .runtime import (
    AcceptedInvite,
    AuditEventType,
    CredentialHasher,
    CredentialVerifierRecord,
    InMemoryPilotIdentityStore,
    IssuedSession,
    PilotAuditEvent,
    PilotRuntimeError,
    PilotRuntimeSnapshot,
    VerifierPurpose,
    _aware_utc,
    _invite_expiry,
    _new_id,
    _new_session_token,
    _pseudonym,
    _safe_id,
    _secret,
    _session_digest,
    _session_token,
)
from .runtime_v2 import (
    PilotIdentityRuntime as PilotIdentityRuntimeV2,
    PilotRuntimeLimits,
)


class PilotIdentityRuntime(PilotIdentityRuntimeV2):
    """P2.1 R4 runtime: authenticate first, then apply capacity limits."""

    def issue_invite(self, **kwargs):
        actor_token = _session_token(kwargs.get("actor_session_token"))
        tenant_id = _safe_id(kwargs.get("tenant_id"), "TENANT_ID_INVALID")
        role = kwargs.get("role")
        if not isinstance(role, TenantRole):
            raise PilotRuntimeError("INVITE_ROLE_INVALID")
        current = _aware_utc(
            kwargs.get("now"),
            "INVITE_ISSUED_TIMEZONE_REQUIRED",
        )
        _invite_expiry(current, kwargs.get("expires_at"))
        _secret(
            kwargs.get("invite_secret"),
            minimum=24,
            maximum=256,
            code="INVITE_SECRET_INVALID",
        )
        with self._store._lock:
            self._authorize_locked(
                session_token=actor_token,
                tenant_id=tenant_id,
                permission=Permission.MANAGE_MEMBERS,
                now=current,
            )
            return super().issue_invite(**kwargs)

    def accept_invite(self, **kwargs) -> AcceptedInvite:
        invite_id = _safe_id(kwargs.get("invite_id"), "INVITE_ID_INVALID")
        current = _aware_utc(
            kwargs.get("now"),
            "INVITE_ACCEPTED_TIMEZONE_REQUIRED",
        )
        _pseudonym(kwargs.get("pseudonym"))
        invite_secret = _secret(
            kwargs.get("invite_secret"),
            minimum=24,
            maximum=256,
            code="INVITE_SECRET_INVALID",
        )
        password = _secret(
            kwargs.get("password"),
            minimum=12,
            maximum=256,
            code="PASSWORD_INVALID",
        )
        recovery = _secret(
            kwargs.get("recovery_key"),
            minimum=24,
            maximum=256,
            code="RECOVERY_KEY_INVALID",
        )
        if password == recovery:
            raise PilotRuntimeError("PASSWORD_RECOVERY_REUSE_FORBIDDEN")
        with self._store._lock:
            invite = self._store._invites.get(invite_id)
            if invite is None:
                raise PilotRuntimeError("INVITE_NOT_FOUND")
            if invite.status is not InviteStatus.ISSUED:
                raise PilotRuntimeError("INVITE_NOT_ACTIVE")
            if current < invite.issued_at.astimezone(UTC):
                raise PilotRuntimeError("INVITE_NOT_YET_VALID")
            if current >= invite.expires_at.astimezone(UTC):
                return super().accept_invite(**kwargs)
            tenant = self._store._tenants.get(invite.tenant_id)
            if tenant is None or tenant.status is not TenantStatus.ACTIVE:
                raise PilotRuntimeError("TENANT_NOT_ACTIVE")
            verifier = self._active_verifier(
                invite.secret_verifier_record_id,
                VerifierPurpose.INVITE,
            )
            if not self._verify_secret(verifier.verifier, invite_secret):
                raise PilotRuntimeError("INVITE_AUTHENTICATION_FAILED")
            return super().accept_invite(**kwargs)

    def authenticate(self, **kwargs) -> IssuedSession:
        try:
            pseudonym = _pseudonym(kwargs.get("pseudonym"))
            password = _secret(
                kwargs.get("password"),
                minimum=1,
                maximum=256,
                code="AUTHENTICATION_INPUT_INVALID",
            )
            tenant_id = _safe_id(
                kwargs.get("tenant_id"),
                "AUTHENTICATION_INPUT_INVALID",
            )
            current = _aware_utc(
                kwargs.get("now"),
                "AUTHENTICATION_TIMEZONE_REQUIRED",
            )
        except PilotRuntimeError as exc:
            if exc.code == "AUTHENTICATION_TIMEZONE_REQUIRED":
                raise
            raise PilotRuntimeError("AUTHENTICATION_FAILED") from exc

        with self._store._lock:
            account_id = self._store._pseudonym_owners.get(pseudonym.casefold())
            account = (
                self._store._accounts.get(account_id)
                if account_id is not None
                else None
            )
            if account is None or account.status is not AccountStatus.ACTIVE:
                raise PilotRuntimeError("AUTHENTICATION_FAILED")
            verifier = self._active_verifier(
                account.credential_record_id,
                VerifierPurpose.PASSWORD,
                generic_failure="AUTHENTICATION_FAILED",
            )
            if not self._verify_secret(verifier.verifier, password):
                raise PilotRuntimeError("AUTHENTICATION_FAILED")
            tenant = self._store._tenants.get(tenant_id)
            membership_id = self._store._membership_by_tenant_account.get(
                (tenant_id, account.account_id)
            )
            membership = (
                self._store._memberships.get(membership_id)
                if membership_id is not None
                else None
            )
            if (
                tenant is None
                or tenant.status is not TenantStatus.ACTIVE
                or membership is None
                or membership.status is not MembershipStatus.ACTIVE
            ):
                raise PilotRuntimeError("AUTHENTICATION_FAILED")
            if current < max(
                account.created_at.astimezone(UTC),
                membership.created_at.astimezone(UTC),
                tenant.created_at.astimezone(UTC),
            ):
                raise PilotRuntimeError("AUTHENTICATION_FAILED")

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

            session = SessionPrincipal(
                session_id=_new_id("session"),
                account_id=account.account_id,
                tenant_id=tenant.tenant_id,
                membership_id=membership.membership_id,
                role=membership.role,
                authentication_epoch=account.authentication_epoch,
                status=SessionStatus.ACTIVE,
                issued_at=current,
                expires_at=current + self._session_lifetime,
            )
            token = _new_session_token()
            digest = _session_digest(token)
            while digest in self._store._session_digest_owners:
                token = _new_session_token()
                digest = _session_digest(token)
            self._store._sessions[session.session_id] = session
            self._store._session_digest_owners[digest] = session.session_id
            self._audit(
                AuditEventType.SESSION_ISSUED,
                actor=account.account_id,
                tenant_id=tenant.tenant_id,
                subject_id=session.session_id,
                at=current,
            )
            return IssuedSession(
                session_token=token,
                account_id=account.account_id,
                tenant_id=tenant.tenant_id,
                role=membership.role,
                expires_at=session.expires_at,
            )


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
