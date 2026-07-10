from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
import re
from typing import Final


_SAFE_ID: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")
_PSEUDONYM: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")
_MAX_SESSION_LIFETIME: Final = timedelta(hours=12)


class PilotIdentityError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _safe_id(value: object, code: str) -> str:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise PilotIdentityError(code)
    return value


def _aware_utc(value: object, code: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise PilotIdentityError(code)
    return value.astimezone(UTC)


def _positive_epoch(value: object, code: str) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 1
    ):
        raise PilotIdentityError(code)
    return value


class AccountStatus(StrEnum):
    INVITED = "INVITED"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"
    DELETED = "DELETED"


class TenantStatus(StrEnum):
    PROVISIONING = "PROVISIONING"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    CLOSED = "CLOSED"


class InviteStatus(StrEnum):
    ISSUED = "ISSUED"
    ACCEPTED = "ACCEPTED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class MembershipStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"


class SessionStatus(StrEnum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


class TenantRole(StrEnum):
    TENANT_OWNER = "TENANT_OWNER"
    TENANT_ANALYST = "TENANT_ANALYST"
    TENANT_VIEWER = "TENANT_VIEWER"


class Permission(StrEnum):
    VIEW_ANALYTICS = "VIEW_ANALYTICS"
    UPLOAD_DATASET = "UPLOAD_DATASET"
    RUN_ANALYSIS = "RUN_ANALYSIS"
    MANAGE_MEMBERS = "MANAGE_MEMBERS"
    MANAGE_TENANT_DATA = "MANAGE_TENANT_DATA"


_ROLE_PERMISSIONS: Final[dict[TenantRole, frozenset[Permission]]] = {
    TenantRole.TENANT_OWNER: frozenset(Permission),
    TenantRole.TENANT_ANALYST: frozenset(
        {
            Permission.VIEW_ANALYTICS,
            Permission.UPLOAD_DATASET,
            Permission.RUN_ANALYSIS,
        }
    ),
    TenantRole.TENANT_VIEWER: frozenset({Permission.VIEW_ANALYTICS}),
}


@dataclass(frozen=True, slots=True)
class PseudonymousAccount:
    account_id: str
    pseudonym: str
    credential_record_id: str
    recovery_record_id: str
    credential_algorithm: str
    authentication_epoch: int
    status: AccountStatus
    created_at: datetime

    def __post_init__(self) -> None:
        _safe_id(self.account_id, "ACCOUNT_ID_INVALID")
        if (
            not isinstance(self.pseudonym, str)
            or _PSEUDONYM.fullmatch(self.pseudonym) is None
            or "@" in self.pseudonym
        ):
            raise PilotIdentityError("ACCOUNT_PSEUDONYM_INVALID")
        credential_reference = _safe_id(
            self.credential_record_id,
            "ACCOUNT_CREDENTIAL_REFERENCE_INVALID",
        )
        recovery_reference = _safe_id(
            self.recovery_record_id,
            "ACCOUNT_RECOVERY_REFERENCE_INVALID",
        )
        if credential_reference == recovery_reference:
            raise PilotIdentityError("ACCOUNT_RECOVERY_REFERENCE_REUSED")
        if self.credential_algorithm != "argon2id":
            raise PilotIdentityError("ACCOUNT_CREDENTIAL_ALGORITHM_INVALID")
        _positive_epoch(
            self.authentication_epoch,
            "ACCOUNT_AUTHENTICATION_EPOCH_INVALID",
        )
        if not isinstance(self.status, AccountStatus):
            raise PilotIdentityError("ACCOUNT_STATUS_INVALID")
        _aware_utc(self.created_at, "ACCOUNT_CREATED_TIMEZONE_REQUIRED")


@dataclass(frozen=True, slots=True)
class Tenant:
    tenant_id: str
    tenant_alias: str
    status: TenantStatus
    created_at: datetime

    def __post_init__(self) -> None:
        _safe_id(self.tenant_id, "TENANT_ID_INVALID")
        _safe_id(self.tenant_alias, "TENANT_ALIAS_INVALID")
        if not isinstance(self.status, TenantStatus):
            raise PilotIdentityError("TENANT_STATUS_INVALID")
        _aware_utc(self.created_at, "TENANT_CREATED_TIMEZONE_REQUIRED")


@dataclass(frozen=True, slots=True)
class TenantInvite:
    invite_id: str
    tenant_id: str
    role: TenantRole
    secret_verifier_record_id: str
    status: InviteStatus
    issued_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        _safe_id(self.invite_id, "INVITE_ID_INVALID")
        _safe_id(self.tenant_id, "INVITE_TENANT_INVALID")
        _safe_id(
            self.secret_verifier_record_id,
            "INVITE_SECRET_REFERENCE_INVALID",
        )
        if not isinstance(self.role, TenantRole):
            raise PilotIdentityError("INVITE_ROLE_INVALID")
        if not isinstance(self.status, InviteStatus):
            raise PilotIdentityError("INVITE_STATUS_INVALID")
        issued = _aware_utc(self.issued_at, "INVITE_ISSUED_TIMEZONE_REQUIRED")
        expires = _aware_utc(self.expires_at, "INVITE_EXPIRES_TIMEZONE_REQUIRED")
        if expires <= issued:
            raise PilotIdentityError("INVITE_EXPIRY_INVALID")


@dataclass(frozen=True, slots=True)
class TenantMembership:
    membership_id: str
    tenant_id: str
    account_id: str
    role: TenantRole
    status: MembershipStatus
    created_at: datetime

    def __post_init__(self) -> None:
        _safe_id(self.membership_id, "MEMBERSHIP_ID_INVALID")
        _safe_id(self.tenant_id, "MEMBERSHIP_TENANT_INVALID")
        _safe_id(self.account_id, "MEMBERSHIP_ACCOUNT_INVALID")
        if not isinstance(self.role, TenantRole):
            raise PilotIdentityError("MEMBERSHIP_ROLE_INVALID")
        if not isinstance(self.status, MembershipStatus):
            raise PilotIdentityError("MEMBERSHIP_STATUS_INVALID")
        _aware_utc(self.created_at, "MEMBERSHIP_CREATED_TIMEZONE_REQUIRED")


@dataclass(frozen=True, slots=True)
class SessionPrincipal:
    session_id: str
    account_id: str
    tenant_id: str
    membership_id: str
    role: TenantRole
    authentication_epoch: int
    status: SessionStatus
    issued_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        _safe_id(self.session_id, "SESSION_ID_INVALID")
        _safe_id(self.account_id, "SESSION_ACCOUNT_INVALID")
        _safe_id(self.tenant_id, "SESSION_TENANT_INVALID")
        _safe_id(self.membership_id, "SESSION_MEMBERSHIP_INVALID")
        if not isinstance(self.role, TenantRole):
            raise PilotIdentityError("SESSION_ROLE_INVALID")
        _positive_epoch(
            self.authentication_epoch,
            "SESSION_AUTHENTICATION_EPOCH_INVALID",
        )
        if not isinstance(self.status, SessionStatus):
            raise PilotIdentityError("SESSION_STATUS_INVALID")
        issued = _aware_utc(self.issued_at, "SESSION_ISSUED_TIMEZONE_REQUIRED")
        expires = _aware_utc(self.expires_at, "SESSION_EXPIRES_TIMEZONE_REQUIRED")
        if expires <= issued:
            raise PilotIdentityError("SESSION_EXPIRY_INVALID")
        if expires - issued > _MAX_SESSION_LIFETIME:
            raise PilotIdentityError("SESSION_LIFETIME_EXCEEDED")


def authorize(
    principal: SessionPrincipal,
    *,
    account: PseudonymousAccount,
    membership: TenantMembership,
    tenant: Tenant,
    tenant_id: str,
    permission: Permission,
    now: datetime,
) -> None:
    if not isinstance(principal, SessionPrincipal):
        raise PilotIdentityError("SESSION_PRINCIPAL_INVALID")
    if not isinstance(account, PseudonymousAccount):
        raise PilotIdentityError("AUTHORIZATION_ACCOUNT_INVALID")
    if not isinstance(membership, TenantMembership):
        raise PilotIdentityError("AUTHORIZATION_MEMBERSHIP_INVALID")
    if not isinstance(tenant, Tenant):
        raise PilotIdentityError("AUTHORIZATION_TENANT_STATE_INVALID")
    requested_tenant = _safe_id(tenant_id, "AUTHORIZATION_TENANT_INVALID")
    if not isinstance(permission, Permission):
        raise PilotIdentityError("AUTHORIZATION_PERMISSION_INVALID")

    current = _aware_utc(now, "AUTHORIZATION_TIMEZONE_REQUIRED")
    issued = principal.issued_at.astimezone(UTC)
    expires = principal.expires_at.astimezone(UTC)
    if current < issued:
        raise PilotIdentityError("SESSION_NOT_YET_VALID")
    if current >= expires:
        raise PilotIdentityError("SESSION_EXPIRED")
    if principal.status is not SessionStatus.ACTIVE:
        raise PilotIdentityError("SESSION_NOT_ACTIVE")

    if account.status is not AccountStatus.ACTIVE:
        raise PilotIdentityError("ACCOUNT_NOT_ACTIVE")
    if membership.status is not MembershipStatus.ACTIVE:
        raise PilotIdentityError("MEMBERSHIP_NOT_ACTIVE")
    if tenant.status is not TenantStatus.ACTIVE:
        raise PilotIdentityError("TENANT_NOT_ACTIVE")

    if account.account_id != principal.account_id:
        raise PilotIdentityError("SESSION_ACCOUNT_MISMATCH")
    if account.authentication_epoch != principal.authentication_epoch:
        raise PilotIdentityError("SESSION_AUTHENTICATION_STALE")
    if membership.membership_id != principal.membership_id:
        raise PilotIdentityError("SESSION_MEMBERSHIP_MISMATCH")
    if membership.account_id != principal.account_id:
        raise PilotIdentityError("MEMBERSHIP_ACCOUNT_MISMATCH")
    if membership.role is not principal.role:
        raise PilotIdentityError("SESSION_ROLE_STALE")
    if (
        principal.tenant_id != requested_tenant
        or membership.tenant_id != requested_tenant
        or tenant.tenant_id != requested_tenant
    ):
        raise PilotIdentityError("TENANT_SCOPE_MISMATCH")
    if permission not in _ROLE_PERMISSIONS[principal.role]:
        raise PilotIdentityError("PERMISSION_DENIED")


__all__ = [
    "AccountStatus",
    "InviteStatus",
    "MembershipStatus",
    "Permission",
    "PilotIdentityError",
    "PseudonymousAccount",
    "SessionPrincipal",
    "SessionStatus",
    "Tenant",
    "TenantInvite",
    "TenantMembership",
    "TenantRole",
    "TenantStatus",
    "authorize",
]
