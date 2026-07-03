from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from threading import RLock
from typing import Protocol
from uuid import uuid4
import hashlib
import re
import secrets

from .identity_contracts import (
    AccountStatus,
    InviteStatus,
    MembershipStatus,
    Permission,
    PseudonymousAccount,
    SessionPrincipal,
    SessionStatus,
    Tenant,
    TenantInvite,
    TenantMembership,
    TenantRole,
    TenantStatus,
    authorize,
)


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")
_PSEUDONYM = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")
_MIN_INVITE_LIFETIME = timedelta(minutes=1)
_MAX_INVITE_LIFETIME = timedelta(days=7)
_MAX_SESSION_LIFETIME = timedelta(hours=12)


class PilotRuntimeError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class VerifierPurpose(StrEnum):
    INVITE = "INVITE"
    PASSWORD = "PASSWORD"
    RECOVERY = "RECOVERY"


class AuditEventType(StrEnum):
    TENANT_PROVISIONED = "TENANT_PROVISIONED"
    INVITE_ISSUED = "INVITE_ISSUED"
    INVITE_ACCEPTED = "INVITE_ACCEPTED"
    SESSION_ISSUED = "SESSION_ISSUED"
    SESSION_REVOKED = "SESSION_REVOKED"
    CREDENTIALS_ROTATED = "CREDENTIALS_ROTATED"


class CredentialHasher(Protocol):
    algorithm: str

    def hash_secret(self, secret: str) -> str:
        ...

    def verify_secret(self, verifier: str, secret: str) -> bool:
        ...


@dataclass(frozen=True, slots=True)
class CredentialVerifierRecord:
    record_id: str
    purpose: VerifierPurpose
    algorithm: str
    verifier: str
    created_at: datetime
    superseded_at: datetime | None = None

    def __post_init__(self) -> None:
        _safe_id(self.record_id, "VERIFIER_RECORD_ID_INVALID")
        if not isinstance(self.purpose, VerifierPurpose):
            raise PilotRuntimeError("VERIFIER_PURPOSE_INVALID")
        if self.algorithm != "argon2id":
            raise PilotRuntimeError("VERIFIER_ALGORITHM_INVALID")
        if (
            not isinstance(self.verifier, str)
            or not self.verifier.startswith("$argon2id$")
            or len(self.verifier) < 32
            or len(self.verifier) > 4096
        ):
            raise PilotRuntimeError("VERIFIER_ENCODING_INVALID")
        created = _aware_utc(self.created_at, "VERIFIER_CREATED_TIMEZONE_REQUIRED")
        if self.superseded_at is not None:
            superseded = _aware_utc(
                self.superseded_at,
                "VERIFIER_SUPERSEDED_TIMEZONE_REQUIRED",
            )
            if superseded < created:
                raise PilotRuntimeError("VERIFIER_SUPERSEDED_TIME_INVALID")


@dataclass(frozen=True, slots=True)
class PilotAuditEvent:
    event_id: str
    event_type: AuditEventType
    actor_reference: str
    tenant_id: str
    subject_id: str
    occurred_at: datetime
    codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _safe_id(self.event_id, "AUDIT_EVENT_ID_INVALID")
        if not isinstance(self.event_type, AuditEventType):
            raise PilotRuntimeError("AUDIT_EVENT_TYPE_INVALID")
        _safe_id(self.actor_reference, "AUDIT_ACTOR_INVALID")
        _safe_id(self.tenant_id, "AUDIT_TENANT_INVALID")
        _safe_id(self.subject_id, "AUDIT_SUBJECT_INVALID")
        _aware_utc(self.occurred_at, "AUDIT_TIMEZONE_REQUIRED")
        if not isinstance(self.codes, tuple):
            raise PilotRuntimeError("AUDIT_CODES_INVALID")
        for code in self.codes:
            _safe_id(code, "AUDIT_CODE_INVALID")


@dataclass(frozen=True, slots=True)
class AcceptedInvite:
    account: PseudonymousAccount
    membership: TenantMembership
    tenant: Tenant


@dataclass(frozen=True, slots=True)
class IssuedSession:
    session_token: str = field(repr=False)
    account_id: str
    tenant_id: str
    role: TenantRole
    expires_at: datetime

    def __post_init__(self) -> None:
        _session_token(self.session_token)
        _safe_id(self.account_id, "ISSUED_SESSION_ACCOUNT_INVALID")
        _safe_id(self.tenant_id, "ISSUED_SESSION_TENANT_INVALID")
        if not isinstance(self.role, TenantRole):
            raise PilotRuntimeError("ISSUED_SESSION_ROLE_INVALID")
        _aware_utc(
            self.expires_at,
            "ISSUED_SESSION_EXPIRES_TIMEZONE_REQUIRED",
        )


@dataclass(frozen=True, slots=True)
class PilotRuntimeSnapshot:
    tenant_count: int
    account_count: int
    membership_count: int
    invite_count: int
    active_session_count: int
    audit_event_count: int
    credential_backend: str
    persistent: bool = False


class InMemoryPilotIdentityStore:
    """Process-local test/pilot store. It is not a production persistence layer."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._tenants: dict[str, Tenant] = {}
        self._tenant_alias_owners: dict[str, str] = {}
        self._accounts: dict[str, PseudonymousAccount] = {}
        self._pseudonym_owners: dict[str, str] = {}
        self._memberships: dict[str, TenantMembership] = {}
        self._membership_by_tenant_account: dict[tuple[str, str], str] = {}
        self._invites: dict[str, TenantInvite] = {}
        self._sessions: dict[str, SessionPrincipal] = {}
        self._session_digest_owners: dict[str, str] = {}
        self._verifiers: dict[str, CredentialVerifierRecord] = {}
        self._audit_events: list[PilotAuditEvent] = []

    def __repr__(self) -> str:
        with self._lock:
            return (
                "InMemoryPilotIdentityStore("
                f"tenants={len(self._tenants)},"
                f"accounts={len(self._accounts)},"
                f"memberships={len(self._memberships)},"
                f"invites={len(self._invites)},"
                f"sessions={len(self._sessions)},"
                f"verifiers={len(self._verifiers)},"
                f"audit_events={len(self._audit_events)})"
            )


class PilotIdentityRuntime:
    def __init__(
        self,
        *,
        hasher: CredentialHasher,
        store: InMemoryPilotIdentityStore | None = None,
        session_lifetime: timedelta = timedelta(hours=1),
    ) -> None:
        if (
            getattr(hasher, "algorithm", None) != "argon2id"
            or not callable(getattr(hasher, "hash_secret", None))
            or not callable(getattr(hasher, "verify_secret", None))
        ):
            raise PilotRuntimeError("ARGON2ID_BACKEND_REQUIRED")
        if (
            not isinstance(session_lifetime, timedelta)
            or session_lifetime <= timedelta(0)
            or session_lifetime > _MAX_SESSION_LIFETIME
        ):
            raise PilotRuntimeError("SESSION_LIFETIME_CONFIGURATION_INVALID")
        self._hasher = hasher
        self._store = store or InMemoryPilotIdentityStore()
        self._session_lifetime = session_lifetime

    def bootstrap_tenant_with_owner_invite(
        self,
        *,
        operator_reference: str,
        tenant_alias: str,
        invite_secret: str,
        now: datetime,
        invite_expires_at: datetime,
    ) -> tuple[Tenant, TenantInvite]:
        actor = _safe_id(operator_reference, "OPERATOR_REFERENCE_INVALID")
        alias = _safe_id(tenant_alias, "TENANT_ALIAS_INVALID")
        current = _aware_utc(now, "BOOTSTRAP_TIMEZONE_REQUIRED")
        expires = _invite_expiry(current, invite_expires_at)
        secret = _secret(
            invite_secret,
            minimum=24,
            maximum=256,
            code="INVITE_SECRET_INVALID",
        )
        verifier = self._hash_secret(secret)

        with self._store._lock:
            alias_key = alias.casefold()
            if alias_key in self._store._tenant_alias_owners:
                raise PilotRuntimeError("TENANT_ALIAS_CONFLICT")
            tenant = Tenant(
                tenant_id=_new_id("tenant"),
                tenant_alias=alias,
                status=TenantStatus.ACTIVE,
                created_at=current,
            )
            invite = self._new_invite(
                tenant_id=tenant.tenant_id,
                role=TenantRole.TENANT_OWNER,
                verifier=verifier,
                issued_at=current,
                expires_at=expires,
            )
            self._store._tenants[tenant.tenant_id] = tenant
            self._store._tenant_alias_owners[alias_key] = tenant.tenant_id
            self._store._invites[invite.invite_id] = invite
            self._audit(
                AuditEventType.TENANT_PROVISIONED,
                actor=actor,
                tenant_id=tenant.tenant_id,
                subject_id=tenant.tenant_id,
                at=current,
            )
            self._audit(
                AuditEventType.INVITE_ISSUED,
                actor=actor,
                tenant_id=tenant.tenant_id,
                subject_id=invite.invite_id,
                at=current,
                codes=(f"role:{invite.role.value}",),
            )
            return tenant, invite

    def issue_invite(
        self,
        *,
        actor_session_token: str,
        tenant_id: str,
        role: TenantRole,
        invite_secret: str,
        now: datetime,
        expires_at: datetime,
    ) -> TenantInvite:
        actor_token = _session_token(actor_session_token)
        requested_tenant = _safe_id(tenant_id, "TENANT_ID_INVALID")
        if not isinstance(role, TenantRole):
            raise PilotRuntimeError("INVITE_ROLE_INVALID")
        current = _aware_utc(now, "INVITE_ISSUED_TIMEZONE_REQUIRED")
        expiry = _invite_expiry(current, expires_at)
        secret = _secret(
            invite_secret,
            minimum=24,
            maximum=256,
            code="INVITE_SECRET_INVALID",
        )
        with self._store._lock:
            actor = self._authorize_locked(
                session_token=actor_token,
                tenant_id=requested_tenant,
                permission=Permission.MANAGE_MEMBERS,
                now=current,
            )
            verifier = self._hash_secret(secret)
            invite = self._new_invite(
                tenant_id=requested_tenant,
                role=role,
                verifier=verifier,
                issued_at=current,
                expires_at=expiry,
            )
            self._store._invites[invite.invite_id] = invite
            self._audit(
                AuditEventType.INVITE_ISSUED,
                actor=actor.account_id,
                tenant_id=requested_tenant,
                subject_id=invite.invite_id,
                at=current,
                codes=(f"role:{role.value}",),
            )
            return invite

    def accept_invite(
        self,
        *,
        invite_id: str,
        invite_secret: str,
        pseudonym: str,
        password: str,
        recovery_key: str,
        now: datetime,
    ) -> AcceptedInvite:
        normalized_invite_id = _safe_id(invite_id, "INVITE_ID_INVALID")
        current = _aware_utc(now, "INVITE_ACCEPTED_TIMEZONE_REQUIRED")
        normalized_pseudonym = _pseudonym(pseudonym)
        invite_value = _secret(
            invite_secret,
            minimum=24,
            maximum=256,
            code="INVITE_SECRET_INVALID",
        )
        password_value = _secret(
            password,
            minimum=12,
            maximum=256,
            code="PASSWORD_INVALID",
        )
        recovery_value = _secret(
            recovery_key,
            minimum=24,
            maximum=256,
            code="RECOVERY_KEY_INVALID",
        )
        if password_value == recovery_value:
            raise PilotRuntimeError("PASSWORD_RECOVERY_REUSE_FORBIDDEN")

        with self._store._lock:
            invite = self._store._invites.get(normalized_invite_id)
            if invite is None:
                raise PilotRuntimeError("INVITE_NOT_FOUND")
            if invite.status is not InviteStatus.ISSUED:
                raise PilotRuntimeError("INVITE_NOT_ACTIVE")
            if current < invite.issued_at.astimezone(UTC):
                raise PilotRuntimeError("INVITE_NOT_YET_VALID")
            if current >= invite.expires_at.astimezone(UTC):
                self._store._invites[invite.invite_id] = replace(
                    invite,
                    status=InviteStatus.EXPIRED,
                )
                raise PilotRuntimeError("INVITE_EXPIRED")
            tenant = self._store._tenants.get(invite.tenant_id)
            if tenant is None or tenant.status is not TenantStatus.ACTIVE:
                raise PilotRuntimeError("TENANT_NOT_ACTIVE")
            invite_verifier = self._active_verifier(
                invite.secret_verifier_record_id,
                VerifierPurpose.INVITE,
            )
            if not self._verify_secret(invite_verifier.verifier, invite_value):
                raise PilotRuntimeError("INVITE_AUTHENTICATION_FAILED")
            pseudonym_key = normalized_pseudonym.casefold()
            if pseudonym_key in self._store._pseudonym_owners:
                raise PilotRuntimeError("PSEUDONYM_CONFLICT")

            password_verifier = self._hash_secret(password_value)
            recovery_verifier = self._hash_secret(recovery_value)
            password_record = self._new_verifier(
                purpose=VerifierPurpose.PASSWORD,
                verifier=password_verifier,
                at=current,
            )
            recovery_record = self._new_verifier(
                purpose=VerifierPurpose.RECOVERY,
                verifier=recovery_verifier,
                at=current,
            )
            account = PseudonymousAccount(
                account_id=_new_id("account"),
                pseudonym=normalized_pseudonym,
                credential_record_id=password_record.record_id,
                recovery_record_id=recovery_record.record_id,
                credential_algorithm="argon2id",
                authentication_epoch=1,
                status=AccountStatus.ACTIVE,
                created_at=current,
            )
            membership = TenantMembership(
                membership_id=_new_id("membership"),
                tenant_id=tenant.tenant_id,
                account_id=account.account_id,
                role=invite.role,
                status=MembershipStatus.ACTIVE,
                created_at=current,
            )
            membership_key = (tenant.tenant_id, account.account_id)
            if membership_key in self._store._membership_by_tenant_account:
                raise PilotRuntimeError("MEMBERSHIP_CONFLICT")

            self._store._verifiers[password_record.record_id] = password_record
            self._store._verifiers[recovery_record.record_id] = recovery_record
            self._store._accounts[account.account_id] = account
            self._store._pseudonym_owners[pseudonym_key] = account.account_id
            self._store._memberships[membership.membership_id] = membership
            self._store._membership_by_tenant_account[
                membership_key
            ] = membership.membership_id
            self._store._invites[invite.invite_id] = replace(
                invite,
                status=InviteStatus.ACCEPTED,
            )
            self._store._verifiers[invite_verifier.record_id] = replace(
                invite_verifier,
                superseded_at=current,
            )
            self._audit(
                AuditEventType.INVITE_ACCEPTED,
                actor=account.account_id,
                tenant_id=tenant.tenant_id,
                subject_id=membership.membership_id,
                at=current,
                codes=(f"role:{membership.role.value}",),
            )
            return AcceptedInvite(
                account=account,
                membership=membership,
                tenant=tenant,
            )

    def authenticate(
        self,
        *,
        pseudonym: str,
        password: str,
        tenant_id: str,
        now: datetime,
    ) -> IssuedSession:
        try:
            normalized_pseudonym = _pseudonym(pseudonym)
            password_value = _secret(
                password,
                minimum=1,
                maximum=256,
                code="AUTHENTICATION_INPUT_INVALID",
            )
            requested_tenant = _safe_id(
                tenant_id,
                "AUTHENTICATION_INPUT_INVALID",
            )
            current = _aware_utc(now, "AUTHENTICATION_TIMEZONE_REQUIRED")
        except PilotRuntimeError as exc:
            if exc.code == "AUTHENTICATION_TIMEZONE_REQUIRED":
                raise
            raise PilotRuntimeError("AUTHENTICATION_FAILED") from exc

        with self._store._lock:
            account_id = self._store._pseudonym_owners.get(
                normalized_pseudonym.casefold()
            )
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
            if not self._verify_secret(verifier.verifier, password_value):
                raise PilotRuntimeError("AUTHENTICATION_FAILED")
            tenant = self._store._tenants.get(requested_tenant)
            membership_id = self._store._membership_by_tenant_account.get(
                (requested_tenant, account.account_id)
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
            session_token = _new_session_token()
            digest = _session_digest(session_token)
            while digest in self._store._session_digest_owners:
                session_token = _new_session_token()
                digest = _session_digest(session_token)
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
                session_token=session_token,
                account_id=account.account_id,
                tenant_id=tenant.tenant_id,
                role=membership.role,
                expires_at=session.expires_at,
            )

    def authorize_session(
        self,
        *,
        session_token: str,
        tenant_id: str,
        permission: Permission,
        now: datetime,
    ) -> SessionPrincipal:
        token = _session_token(session_token)
        requested_tenant = _safe_id(tenant_id, "TENANT_ID_INVALID")
        current = _aware_utc(now, "AUTHORIZATION_TIMEZONE_REQUIRED")
        with self._store._lock:
            return self._authorize_locked(
                session_token=token,
                tenant_id=requested_tenant,
                permission=permission,
                now=current,
            )

    def revoke_session(
        self,
        *,
        session_token: str,
        now: datetime,
    ) -> SessionPrincipal:
        token = _session_token(session_token)
        current = _aware_utc(now, "SESSION_REVOKED_TIMEZONE_REQUIRED")
        with self._store._lock:
            session = self._session_from_token_locked(token)
            if current < session.issued_at.astimezone(UTC):
                raise PilotRuntimeError("SESSION_REVOCATION_TIME_REGRESSION")
            if session.status is SessionStatus.REVOKED:
                return session
            revoked = replace(session, status=SessionStatus.REVOKED)
            self._store._sessions[session.session_id] = revoked
            self._audit(
                AuditEventType.SESSION_REVOKED,
                actor=session.account_id,
                tenant_id=session.tenant_id,
                subject_id=session.session_id,
                at=current,
            )
            return revoked

    def rotate_credentials_with_recovery(
        self,
        *,
        pseudonym: str,
        recovery_key: str,
        new_password: str,
        new_recovery_key: str,
        now: datetime,
    ) -> PseudonymousAccount:
        normalized_pseudonym = _pseudonym(pseudonym)
        recovery_value = _secret(
            recovery_key,
            minimum=1,
            maximum=256,
            code="RECOVERY_FAILED",
        )
        password_value = _secret(
            new_password,
            minimum=12,
            maximum=256,
            code="PASSWORD_INVALID",
        )
        new_recovery_value = _secret(
            new_recovery_key,
            minimum=24,
            maximum=256,
            code="RECOVERY_KEY_INVALID",
        )
        current = _aware_utc(now, "CREDENTIAL_ROTATION_TIMEZONE_REQUIRED")
        if password_value == new_recovery_value:
            raise PilotRuntimeError("PASSWORD_RECOVERY_REUSE_FORBIDDEN")

        with self._store._lock:
            account_id = self._store._pseudonym_owners.get(
                normalized_pseudonym.casefold()
            )
            account = (
                self._store._accounts.get(account_id)
                if account_id is not None
                else None
            )
            if account is None or account.status is not AccountStatus.ACTIVE:
                raise PilotRuntimeError("RECOVERY_FAILED")
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
            if current < max(
                account.created_at.astimezone(UTC),
                old_password.created_at.astimezone(UTC),
                old_recovery.created_at.astimezone(UTC),
            ):
                raise PilotRuntimeError(
                    "CREDENTIAL_ROTATION_TIME_REGRESSION"
                )
            if not self._verify_secret(old_recovery.verifier, recovery_value):
                raise PilotRuntimeError("RECOVERY_FAILED")
            if self._verify_secret(old_password.verifier, password_value):
                raise PilotRuntimeError("CREDENTIAL_REUSE_FORBIDDEN")
            if self._verify_secret(old_recovery.verifier, new_recovery_value):
                raise PilotRuntimeError("CREDENTIAL_REUSE_FORBIDDEN")

            password_record = self._new_verifier(
                purpose=VerifierPurpose.PASSWORD,
                verifier=self._hash_secret(password_value),
                at=current,
            )
            recovery_record = self._new_verifier(
                purpose=VerifierPurpose.RECOVERY,
                verifier=self._hash_secret(new_recovery_value),
                at=current,
            )
            rotated = replace(
                account,
                credential_record_id=password_record.record_id,
                recovery_record_id=recovery_record.record_id,
                authentication_epoch=account.authentication_epoch + 1,
            )
            self._store._verifiers[old_password.record_id] = replace(
                old_password,
                superseded_at=current,
            )
            self._store._verifiers[old_recovery.record_id] = replace(
                old_recovery,
                superseded_at=current,
            )
            self._store._verifiers[password_record.record_id] = password_record
            self._store._verifiers[recovery_record.record_id] = recovery_record
            self._store._accounts[account.account_id] = rotated
            for session_id, session in tuple(self._store._sessions.items()):
                if (
                    session.account_id == account.account_id
                    and session.status is SessionStatus.ACTIVE
                ):
                    self._store._sessions[session_id] = replace(
                        session,
                        status=SessionStatus.REVOKED,
                    )
            tenant_id = self._first_tenant_for_account(account.account_id)
            self._audit(
                AuditEventType.CREDENTIALS_ROTATED,
                actor=account.account_id,
                tenant_id=tenant_id,
                subject_id=account.account_id,
                at=current,
                codes=(f"epoch:{rotated.authentication_epoch}",),
            )
            return rotated

    def snapshot(self) -> PilotRuntimeSnapshot:
        with self._store._lock:
            active_sessions = sum(
                session.status is SessionStatus.ACTIVE
                for session in self._store._sessions.values()
            )
            return PilotRuntimeSnapshot(
                tenant_count=len(self._store._tenants),
                account_count=len(self._store._accounts),
                membership_count=len(self._store._memberships),
                invite_count=len(self._store._invites),
                active_session_count=active_sessions,
                audit_event_count=len(self._store._audit_events),
                credential_backend=self._hasher.algorithm,
            )

    def audit_events(self) -> tuple[PilotAuditEvent, ...]:
        with self._store._lock:
            return tuple(self._store._audit_events)

    def _new_invite(
        self,
        *,
        tenant_id: str,
        role: TenantRole,
        verifier: str,
        issued_at: datetime,
        expires_at: datetime,
    ) -> TenantInvite:
        verifier_record = self._new_verifier(
            purpose=VerifierPurpose.INVITE,
            verifier=verifier,
            at=issued_at,
        )
        self._store._verifiers[verifier_record.record_id] = verifier_record
        return TenantInvite(
            invite_id=_new_id("invite"),
            tenant_id=tenant_id,
            role=role,
            secret_verifier_record_id=verifier_record.record_id,
            status=InviteStatus.ISSUED,
            issued_at=issued_at,
            expires_at=expires_at,
        )

    def _new_verifier(
        self,
        *,
        purpose: VerifierPurpose,
        verifier: str,
        at: datetime,
    ) -> CredentialVerifierRecord:
        return CredentialVerifierRecord(
            record_id=_new_id("verifier"),
            purpose=purpose,
            algorithm="argon2id",
            verifier=verifier,
            created_at=at,
        )

    def _active_verifier(
        self,
        record_id: str,
        purpose: VerifierPurpose,
        *,
        generic_failure: str | None = None,
    ) -> CredentialVerifierRecord:
        record = self._store._verifiers.get(record_id)
        if (
            record is None
            or record.purpose is not purpose
            or record.superseded_at is not None
        ):
            raise PilotRuntimeError(
                generic_failure or "VERIFIER_RECORD_NOT_ACTIVE"
            )
        return record

    def _authorize_locked(
        self,
        *,
        session_token: str,
        tenant_id: str,
        permission: Permission,
        now: datetime,
    ) -> SessionPrincipal:
        session = self._session_from_token_locked(session_token)
        account = self._store._accounts.get(session.account_id)
        membership = self._store._memberships.get(session.membership_id)
        tenant = self._store._tenants.get(session.tenant_id)
        if account is None or membership is None or tenant is None:
            raise PilotRuntimeError("SESSION_STATE_INCOMPLETE")
        authorize(
            session,
            account=account,
            membership=membership,
            tenant=tenant,
            tenant_id=tenant_id,
            permission=permission,
            now=now,
        )
        return session

    def _session_from_token_locked(
        self,
        session_token: str,
    ) -> SessionPrincipal:
        digest = _session_digest(session_token)
        session_id = self._store._session_digest_owners.get(digest)
        session = (
            self._store._sessions.get(session_id)
            if session_id is not None
            else None
        )
        if session is None:
            raise PilotRuntimeError("SESSION_NOT_FOUND")
        return session

    def _hash_secret(self, secret: str) -> str:
        try:
            verifier = self._hasher.hash_secret(secret)
        except Exception as exc:
            raise PilotRuntimeError("CREDENTIAL_BACKEND_FAILURE") from exc
        if (
            not isinstance(verifier, str)
            or not verifier.startswith("$argon2id$")
            or len(verifier) < 32
            or len(verifier) > 4096
            or secret in verifier
        ):
            raise PilotRuntimeError("CREDENTIAL_BACKEND_INVALID_OUTPUT")
        return verifier

    def _verify_secret(self, verifier: str, secret: str) -> bool:
        try:
            result = self._hasher.verify_secret(verifier, secret)
        except Exception as exc:
            raise PilotRuntimeError("CREDENTIAL_BACKEND_FAILURE") from exc
        if not isinstance(result, bool):
            raise PilotRuntimeError("CREDENTIAL_BACKEND_INVALID_OUTPUT")
        return result

    def _audit(
        self,
        event_type: AuditEventType,
        *,
        actor: str,
        tenant_id: str,
        subject_id: str,
        at: datetime,
        codes: tuple[str, ...] = (),
    ) -> None:
        self._store._audit_events.append(
            PilotAuditEvent(
                event_id=_new_id("audit"),
                event_type=event_type,
                actor_reference=actor,
                tenant_id=tenant_id,
                subject_id=subject_id,
                occurred_at=at,
                codes=codes,
            )
        )

    def _first_tenant_for_account(self, account_id: str) -> str:
        for membership in self._store._memberships.values():
            if membership.account_id == account_id:
                return membership.tenant_id
        raise PilotRuntimeError("ACCOUNT_TENANT_NOT_FOUND")


def _safe_id(value: object, code: str) -> str:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise PilotRuntimeError(code)
    return value


def _aware_utc(value: object, code: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise PilotRuntimeError(code)
    return value.astimezone(UTC)


def _pseudonym(value: object) -> str:
    if (
        not isinstance(value, str)
        or _PSEUDONYM.fullmatch(value) is None
        or "@" in value
    ):
        raise PilotRuntimeError("PSEUDONYM_INVALID")
    return value


def _secret(
    value: object,
    *,
    minimum: int,
    maximum: int,
    code: str,
) -> str:
    if (
        not isinstance(value, str)
        or len(value) < minimum
        or len(value) > maximum
        or "\x00" in value
        or value.isspace()
    ):
        raise PilotRuntimeError(code)
    return value


def _invite_expiry(issued_at: datetime, expires_at: datetime) -> datetime:
    expiry = _aware_utc(expires_at, "INVITE_EXPIRES_TIMEZONE_REQUIRED")
    lifetime = expiry - issued_at
    if lifetime < _MIN_INVITE_LIFETIME or lifetime > _MAX_INVITE_LIFETIME:
        raise PilotRuntimeError("INVITE_LIFETIME_INVALID")
    return expiry


def _session_token(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) < 32
        or len(value) > 512
        or "\x00" in value
        or value.isspace()
    ):
        raise PilotRuntimeError("SESSION_TOKEN_INVALID")
    return value


def _new_session_token() -> str:
    return secrets.token_urlsafe(32)


def _session_digest(session_token: str) -> str:
    return hashlib.sha256(session_token.encode("utf-8")).hexdigest()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


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
    "PilotRuntimeSnapshot",
    "VerifierPurpose",
]
