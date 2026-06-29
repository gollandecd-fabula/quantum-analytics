from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import hmac
import secrets
from typing import Final
from uuid import uuid4


INVITE_PREFIX: Final = "QINV-"
ACCOUNT_PREFIX: Final = "QTM-"


class AccessError(ValueError):
    """Fail-closed access-domain error with a stable diagnostic code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class TenantContext:
    tenant_id: str
    account_id: str

    def require_tenant(self, tenant_id: str) -> None:
        if not hmac.compare_digest(self.tenant_id, tenant_id):
            raise AccessError("TENANT_SCOPE_MISMATCH")


@dataclass(frozen=True, slots=True)
class InviteRecord:
    invite_id: str
    code_hash: str
    expires_at: datetime
    feature_profile: str
    activated_at: datetime | None = None

    @property
    def active(self) -> bool:
        now = datetime.now(timezone.utc)
        return self.activated_at is None and now < self.expires_at


@dataclass(frozen=True, slots=True)
class AccountRecord:
    account_id: str
    account_alias: str
    tenant_id: str
    recovery_key_hash: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ActivationResult:
    account: AccountRecord
    tenant: TenantContext
    recovery_key: str


class AccessRegistry:
    """Dependency-free P1 registry.

    This is deliberately in-memory. Durable persistence and approved password
    hashing are separate gated units. Raw invite and recovery secrets are never
    retained.
    """

    def __init__(self) -> None:
        self._invites_by_hash: dict[str, InviteRecord] = {}
        self._accounts: dict[str, AccountRecord] = {}

    @staticmethod
    def _hash_secret(value: str) -> str:
        return sha256(value.encode("utf-8")).hexdigest()

    def issue_invite(
        self,
        *,
        expires_at: datetime,
        feature_profile: str = "PILOT_TESTER",
        now: datetime | None = None,
    ) -> str:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None or current.utcoffset() is None:
            raise AccessError("ISSUE_TIME_TIMEZONE_REQUIRED")
        if expires_at.tzinfo is None or expires_at.utcoffset() is None:
            raise AccessError("INVITE_EXPIRY_TIMEZONE_REQUIRED")
        if expires_at <= current:
            raise AccessError("INVITE_EXPIRY_NOT_FUTURE")
        if not feature_profile.strip():
            raise AccessError("FEATURE_PROFILE_REQUIRED")

        code = INVITE_PREFIX + secrets.token_urlsafe(24)
        code_hash = self._hash_secret(code)
        self._invites_by_hash[code_hash] = InviteRecord(
            invite_id=str(uuid4()),
            code_hash=code_hash,
            expires_at=expires_at.astimezone(timezone.utc),
            feature_profile=feature_profile.strip(),
        )
        return code

    def activate_invite(
        self,
        code: str,
        *,
        now: datetime | None = None,
    ) -> ActivationResult:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None or current.utcoffset() is None:
            raise AccessError("ACTIVATION_TIMEZONE_REQUIRED")

        code_hash = self._hash_secret(code)
        invite = self._invites_by_hash.get(code_hash)
        if invite is None:
            raise AccessError("INVITE_INVALID")
        if invite.activated_at is not None:
            raise AccessError("INVITE_ALREADY_USED")
        if current.astimezone(timezone.utc) >= invite.expires_at:
            raise AccessError("INVITE_EXPIRED")

        account_id = str(uuid4())
        tenant_id = str(uuid4())
        alias = ACCOUNT_PREFIX + secrets.token_hex(8).upper()
        recovery_key = secrets.token_urlsafe(48)
        account = AccountRecord(
            account_id=account_id,
            account_alias=alias,
            tenant_id=tenant_id,
            recovery_key_hash=self._hash_secret(recovery_key),
            created_at=current.astimezone(timezone.utc),
        )
        self._accounts[account_id] = account
        self._invites_by_hash[code_hash] = InviteRecord(
            invite_id=invite.invite_id,
            code_hash=invite.code_hash,
            expires_at=invite.expires_at,
            feature_profile=invite.feature_profile,
            activated_at=current.astimezone(timezone.utc),
        )
        return ActivationResult(
            account=account,
            tenant=TenantContext(tenant_id=tenant_id, account_id=account_id),
            recovery_key=recovery_key,
        )

    def verify_recovery_key(self, account_id: str, recovery_key: str) -> bool:
        account = self._accounts.get(account_id)
        if account is None:
            return False
        return hmac.compare_digest(
            account.recovery_key_hash,
            self._hash_secret(recovery_key),
        )

    def account(self, account_id: str) -> AccountRecord:
        try:
            return self._accounts[account_id]
        except KeyError as exc:
            raise AccessError("ACCOUNT_NOT_FOUND") from exc
