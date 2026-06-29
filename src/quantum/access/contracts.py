from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import hmac
import secrets
from threading import RLock
from typing import Final
from uuid import uuid4


INVITE_PREFIX: Final = "QINV-"
ACCOUNT_PREFIX: Final = "QTM-"


class AccessError(ValueError):
    """Fail-closed access-domain error with a stable diagnostic code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _aware_utc(value: datetime, code: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise AccessError(code)
    return value.astimezone(timezone.utc)


def _feature_profile(value: str) -> str:
    if not isinstance(value, str):
        raise AccessError("FEATURE_PROFILE_INVALID")
    normalized = value.strip()
    if not normalized or len(normalized) > 64:
        raise AccessError("FEATURE_PROFILE_INVALID")
    return normalized


@dataclass(frozen=True, slots=True)
class TenantContext:
    tenant_id: str
    account_id: str
    feature_profile: str = "PILOT_TESTER"

    def __post_init__(self) -> None:
        if not isinstance(self.tenant_id, str) or not self.tenant_id:
            raise AccessError("TENANT_ID_INVALID")
        if not isinstance(self.account_id, str) or not self.account_id:
            raise AccessError("ACCOUNT_ID_INVALID")
        _feature_profile(self.feature_profile)

    def require_tenant(self, tenant_id: str) -> None:
        if not isinstance(tenant_id, str) or not tenant_id:
            raise AccessError("TENANT_ID_INVALID")
        if not hmac.compare_digest(
            self.tenant_id.encode("utf-8"),
            tenant_id.encode("utf-8"),
        ):
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
    feature_profile: str
    recovery_key_hash: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ActivationResult:
    account: AccountRecord
    tenant: TenantContext
    recovery_key: str


class AccessRegistry:
    """Dependency-free, thread-safe P1 access registry.

    This registry is deliberately in-memory. Durable persistence and approved
    password hashing are separate gated units. Raw invite and recovery secrets
    are never retained.
    """

    def __init__(self) -> None:
        self._invites_by_hash: dict[str, InviteRecord] = {}
        self._accounts: dict[str, AccountRecord] = {}
        self._lock = RLock()

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
        current = _aware_utc(
            now or datetime.now(timezone.utc),
            "ISSUE_TIME_TIMEZONE_REQUIRED",
        )
        expiry = _aware_utc(expires_at, "INVITE_EXPIRY_TIMEZONE_REQUIRED")
        profile = _feature_profile(feature_profile)
        if expiry <= current:
            raise AccessError("INVITE_EXPIRY_NOT_FUTURE")

        with self._lock:
            while True:
                code = INVITE_PREFIX + secrets.token_urlsafe(24)
                code_hash = self._hash_secret(code)
                if code_hash not in self._invites_by_hash:
                    break
            self._invites_by_hash[code_hash] = InviteRecord(
                invite_id=str(uuid4()),
                code_hash=code_hash,
                expires_at=expiry,
                feature_profile=profile,
            )
        return code

    def activate_invite(
        self,
        code: str,
        *,
        now: datetime | None = None,
    ) -> ActivationResult:
        current = _aware_utc(
            now or datetime.now(timezone.utc),
            "ACTIVATION_TIMEZONE_REQUIRED",
        )
        if not isinstance(code, str) or not code.startswith(INVITE_PREFIX):
            raise AccessError("INVITE_INVALID")
        code_hash = self._hash_secret(code)

        with self._lock:
            invite = self._invites_by_hash.get(code_hash)
            if invite is None:
                raise AccessError("INVITE_INVALID")
            if invite.activated_at is not None:
                raise AccessError("INVITE_ALREADY_USED")
            if current >= invite.expires_at:
                raise AccessError("INVITE_EXPIRED")

            account_id = str(uuid4())
            while account_id in self._accounts:
                account_id = str(uuid4())
            tenant_id = str(uuid4())
            alias = ACCOUNT_PREFIX + secrets.token_hex(8).upper()
            recovery_key = secrets.token_urlsafe(48)
            account = AccountRecord(
                account_id=account_id,
                account_alias=alias,
                tenant_id=tenant_id,
                feature_profile=invite.feature_profile,
                recovery_key_hash=self._hash_secret(recovery_key),
                created_at=current,
            )
            self._accounts[account_id] = account
            self._invites_by_hash[code_hash] = InviteRecord(
                invite_id=invite.invite_id,
                code_hash=invite.code_hash,
                expires_at=invite.expires_at,
                feature_profile=invite.feature_profile,
                activated_at=current,
            )

        return ActivationResult(
            account=account,
            tenant=TenantContext(
                tenant_id=tenant_id,
                account_id=account_id,
                feature_profile=invite.feature_profile,
            ),
            recovery_key=recovery_key,
        )

    def verify_recovery_key(self, account_id: str, recovery_key: str) -> bool:
        if (
            not isinstance(account_id, str)
            or not account_id
            or not isinstance(recovery_key, str)
            or not recovery_key
        ):
            return False
        with self._lock:
            account = self._accounts.get(account_id)
        if account is None:
            return False
        return hmac.compare_digest(
            account.recovery_key_hash,
            self._hash_secret(recovery_key),
        )

    def account(self, account_id: str) -> AccountRecord:
        if not isinstance(account_id, str) or not account_id:
            raise AccessError("ACCOUNT_ID_INVALID")
        with self._lock:
            account = self._accounts.get(account_id)
        if account is None:
            raise AccessError("ACCOUNT_NOT_FOUND")
        return account
