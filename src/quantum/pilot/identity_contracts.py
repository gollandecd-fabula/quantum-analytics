from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
import re
from typing import Final


_SAFE_ID: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")
_PSEUDONYM: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")


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
        _safe_id(
            self.credential_record_id,
            "ACCOUNT_CREDENTIAL_REFERENCE_INVALID",
        )
        _safe_id(self.recovery_record_id, "ACCOUNT_RECOVERY_REFERENCE_INVALID")
        if self.credential_algorithm != "argon2id":
            raise PilotIdentityError("ACCOUNT_CREDENTIAL_ALGORITHM_INVALID")
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
    issued_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        _safe_id(self.session_id, "SESSION_ID_INVALID")
        _safe_id(self.account_id, "SESSION_ACCOUNT_INVALID")
        _safe_id(self.tenant_id, "SESSION_TENANT_INVALID")
        _safe_id(self.membership_id, "SESSION_MEMBERSHIP_INVALID")
        if not isinstance(self.role, TenantRole):
            raise PilotIdentityError("SESSION_ROLE_INVALID")
        issued = _aware_utc(self.issued_at, "SESSION_ISSUED_TIMEZONE_REQUIRED")
        expires = _aware_utc(self.expires_at, "SESSION_EXPIRES_TIMEZONE_REQUIRED")
        if expires <= issued:
            raise PilotIdentityError("SESSION_EXPIRY_INVALID")


def authorize(
    principal: SessionPrincipal,
    *,
    tenant_id: str,
    permission: Permission,
    now: datetime,
) -> None:
    if not isinstance(principal, SessionPrincipal):
        raise PilotIdentityError("SESSION_PRINCIPAL_INVALID")
    requested_tenant = _safe_id(tenant_id, "AUTHORIZATION_TENANT_INVALID")
    if not isinstance(permission, Permission):
        raise PilotIdentityError("AUTHORIZATION_PERMISSION_INVALID")
    current = _aware_utc(now, "AUTHORIZATION_TIMEZONE_REQUIRED")
    if current >= principal.expires_at.astimezone(UTC):
        raise PilotIdentityError("SESSION_EXPIRED")
    if principal.tenant_id != requested_tenant:
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
    "Tenant",
    "TenantInvite",
    "TenantMembership",
    "TenantRole",
    "TenantStatus",
    "authorize",
]
