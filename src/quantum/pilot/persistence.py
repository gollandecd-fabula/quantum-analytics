from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Final
import hashlib
import json
import os
import re
import sqlite3

from .identity_contracts import (
    AccountStatus,
    InviteStatus,
    MembershipStatus,
    PseudonymousAccount,
    SessionPrincipal,
    SessionStatus,
    Tenant,
    TenantInvite,
    TenantMembership,
    TenantRole,
    TenantStatus,
)

_SCHEMA_VERSION: Final = 1
_SHA256: Final = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")
_IMMUTABLE_TABLES: Final = (
    "pilot_schema_metadata",
    "pilot_checkpoints",
    "pilot_verifiers",
    "pilot_tenants",
    "pilot_accounts",
    "pilot_memberships",
    "pilot_invites",
    "pilot_sessions",
    "pilot_session_token_digests",
    "pilot_audit_events",
)


class PilotPersistenceError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class VerifierPurpose(StrEnum):
    INVITE = "INVITE"
    PASSWORD = "PASSWORD"
    RECOVERY = "RECOVERY"


@dataclass(frozen=True, slots=True)
class PersistedVerifier:
    record_id: str
    purpose: VerifierPurpose
    algorithm: str
    verifier: str
    created_at: datetime
    superseded_at: datetime | None = None

    def __post_init__(self) -> None:
        _safe_id(self.record_id, "VERIFIER_ID_INVALID")
        if not isinstance(self.purpose, VerifierPurpose):
            raise PilotPersistenceError("VERIFIER_PURPOSE_INVALID")
        if self.algorithm != "argon2id":
            raise PilotPersistenceError("VERIFIER_ALGORITHM_INVALID")
        if (
            not isinstance(self.verifier, str)
            or not self.verifier.startswith("$argon2id$")
            or len(self.verifier) < 32
            or len(self.verifier) > 4096
        ):
            raise PilotPersistenceError("VERIFIER_ENCODING_INVALID")
        created = _utc(self.created_at, "VERIFIER_CREATED_TIME_INVALID")
        if self.superseded_at is not None:
            superseded = _utc(
                self.superseded_at,
                "VERIFIER_SUPERSEDED_TIME_INVALID",
            )
            if superseded < created:
                raise PilotPersistenceError("VERIFIER_SUPERSEDED_TIME_INVALID")


@dataclass(frozen=True, slots=True)
class SessionTokenDigestRecord:
    session_id: str
    token_sha256: str

    def __post_init__(self) -> None:
        _safe_id(self.session_id, "SESSION_DIGEST_SESSION_INVALID")
        if not isinstance(self.token_sha256, str) or _SHA256.fullmatch(
            self.token_sha256
        ) is None:
            raise PilotPersistenceError("SESSION_DIGEST_INVALID")


@dataclass(frozen=True, slots=True)
class PersistentAuditEvent:
    event_id: str
    event_type: str
    actor_reference: str
    tenant_id: str
    subject_id: str
    occurred_at: datetime
    codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for value, code in (
            (self.event_id, "AUDIT_EVENT_ID_INVALID"),
            (self.event_type, "AUDIT_EVENT_TYPE_INVALID"),
            (self.actor_reference, "AUDIT_ACTOR_INVALID"),
            (self.tenant_id, "AUDIT_TENANT_INVALID"),
            (self.subject_id, "AUDIT_SUBJECT_INVALID"),
        ):
            _safe_id(value, code)
        _utc(self.occurred_at, "AUDIT_TIME_INVALID")
        if not isinstance(self.codes, tuple) or len(self.codes) > 32:
            raise PilotPersistenceError("AUDIT_CODES_INVALID")
        for code in self.codes:
            _safe_id(code, "AUDIT_CODE_INVALID")


@dataclass(frozen=True, slots=True)
class PersistentPilotState:
    tenants: tuple[Tenant, ...] = ()
    accounts: tuple[PseudonymousAccount, ...] = ()
    memberships: tuple[TenantMembership, ...] = ()
    invites: tuple[TenantInvite, ...] = ()
    sessions: tuple[SessionPrincipal, ...] = ()
    verifiers: tuple[PersistedVerifier, ...] = ()
    session_token_digests: tuple[SessionTokenDigestRecord, ...] = ()
    audit_events: tuple[PersistentAuditEvent, ...] = ()

    def __post_init__(self) -> None:
        collections = (
            ("tenants", self.tenants, "tenant_id", Tenant),
            ("accounts", self.accounts, "account_id", PseudonymousAccount),
            ("memberships", self.memberships, "membership_id", TenantMembership),
            ("invites", self.invites, "invite_id", TenantInvite),
            ("sessions", self.sessions, "session_id", SessionPrincipal),
            ("verifiers", self.verifiers, "record_id", PersistedVerifier),
            (
                "session_token_digests",
                self.session_token_digests,
                "session_id",
                SessionTokenDigestRecord,
            ),
            ("audit_events", self.audit_events, "event_id", PersistentAuditEvent),
        )
        for name, value, key, expected_type in collections:
            if not isinstance(value, tuple):
                raise PilotPersistenceError("STATE_COLLECTION_INVALID")
            if any(not isinstance(item, expected_type) for item in value):
                raise PilotPersistenceError("STATE_ITEM_INVALID")
            object.__setattr__(
                self,
                name,
                tuple(sorted(value, key=lambda item: getattr(item, key))),
            )
        _validate_state(self)


@dataclass(frozen=True, slots=True)
class CheckpointReceipt:
    checkpoint_id: str
    state_sha256: str
    created_at: datetime
    schema_version: int
    record_count: int


@dataclass(frozen=True, slots=True)
class RepositoryStatus:
    schema_version: int
    checkpoint_count: int
    integrity_check: str
    production_ready: bool = False
    encryption_at_rest: bool = False


@dataclass(frozen=True, slots=True)
class PersistenceLimits:
    max_checkpoints: int = 1_000
    max_tenants: int = 100
    max_accounts: int = 10_000
    max_memberships: int = 10_000
    max_invites: int = 20_000
    max_sessions: int = 50_000
    max_verifiers: int = 30_000
    max_audit_events: int = 100_000

    def __post_init__(self) -> None:
        for value in asdict(self).values():
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise PilotPersistenceError("PERSISTENCE_LIMIT_INVALID")


class SqlitePilotIdentityRepository:
    """Synthetic/local persistence reference. Not approved for hosted real data."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        limits: PersistenceLimits | None = None,
    ) -> None:
        if not isinstance(database_path, (str, Path)):
            raise PilotPersistenceError("DATABASE_PATH_INVALID")
        path = str(database_path)
        if not path or path == ":memory:":
            raise PilotPersistenceError("FILE_DATABASE_REQUIRED")
        self._path = Path(path)
        self._limits = limits or PersistenceLimits()
        if not isinstance(self._limits, PersistenceLimits):
            raise PilotPersistenceError("PERSISTENCE_LIMITS_REQUIRED")

    @property
    def path(self) -> Path:
        return self._path

    def initialize(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA_SQL)
            for table in _IMMUTABLE_TABLES:
                conn.executescript(_immutable_trigger_sql(table))
            row = conn.execute(
                "SELECT schema_version FROM pilot_schema_metadata WHERE id = 1"
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO pilot_schema_metadata(id, schema_version) VALUES(1, ?)",
                    (_SCHEMA_VERSION,),
                )
            elif row[0] != _SCHEMA_VERSION:
                raise PilotPersistenceError("SCHEMA_VERSION_UNSUPPORTED")
        _restrict_file(self._path)

    def save_checkpoint(
        self,
        *,
        checkpoint_id: str,
        state: PersistentPilotState,
        created_at: datetime,
    ) -> CheckpointReceipt:
        checkpoint = _safe_id(checkpoint_id, "CHECKPOINT_ID_INVALID")
        if not isinstance(state, PersistentPilotState):
            raise PilotPersistenceError("STATE_INVALID")
        created = _utc(created_at, "CHECKPOINT_TIME_INVALID")
        self._enforce_limits(state)
        digest = state_sha256(state)
        record_count = _record_count(state)
        with self._connect() as conn:
            self._require_schema(conn)
            try:
                conn.execute("BEGIN IMMEDIATE")
                checkpoint_count = conn.execute(
                    "SELECT COUNT(*) FROM pilot_checkpoints"
                ).fetchone()[0]
                if checkpoint_count >= self._limits.max_checkpoints:
                    raise PilotPersistenceError("CHECKPOINT_CAPACITY_EXCEEDED")
                conn.execute(
                    "INSERT INTO pilot_checkpoints(checkpoint_id, created_at, state_sha256, schema_version, record_count) VALUES(?, ?, ?, ?, ?)",
                    (
                        checkpoint,
                        _dt(created),
                        digest,
                        _SCHEMA_VERSION,
                        record_count,
                    ),
                )
                _insert_state(conn, checkpoint, state)
                conn.commit()
            except sqlite3.IntegrityError as exc:
                conn.rollback()
                raise PilotPersistenceError("CHECKPOINT_CONFLICT_OR_INVALID") from exc
            except sqlite3.DatabaseError as exc:
                conn.rollback()
                raise PilotPersistenceError("CHECKPOINT_STORAGE_FAILURE") from exc
            except Exception:
                conn.rollback()
                raise
        return CheckpointReceipt(
            checkpoint_id=checkpoint,
            state_sha256=digest,
            created_at=created,
            schema_version=_SCHEMA_VERSION,
            record_count=record_count,
        )

    def load_checkpoint(
        self,
        checkpoint_id: str,
        *,
        expected_state_sha256: str | None = None,
    ) -> PersistentPilotState:
        checkpoint = _safe_id(checkpoint_id, "CHECKPOINT_ID_INVALID")
        if expected_state_sha256 is None:
            raise PilotPersistenceError("EXPECTED_CHECKPOINT_DIGEST_REQUIRED")
        if (
            not isinstance(expected_state_sha256, str)
            or _SHA256.fullmatch(expected_state_sha256) is None
        ):
            raise PilotPersistenceError("EXPECTED_CHECKPOINT_DIGEST_INVALID")
        with self._connect() as conn:
            self._require_schema(conn)
            metadata = conn.execute(
                "SELECT state_sha256, schema_version, record_count FROM pilot_checkpoints WHERE checkpoint_id = ?",
                (checkpoint,),
            ).fetchone()
            if metadata is None:
                raise PilotPersistenceError("CHECKPOINT_NOT_FOUND")
            if metadata[1] != _SCHEMA_VERSION:
                raise PilotPersistenceError("SCHEMA_VERSION_UNSUPPORTED")
            if metadata[0] != expected_state_sha256:
                raise PilotPersistenceError("CHECKPOINT_RECEIPT_MISMATCH")
            try:
                state = _load_state(conn, checkpoint)
            except (
                ValueError,
                TypeError,
                json.JSONDecodeError,
                PilotPersistenceError,
            ) as exc:
                if isinstance(exc, PilotPersistenceError) and exc.code in {
                    "CHECKPOINT_RECORD_COUNT_MISMATCH",
                    "CHECKPOINT_DIGEST_MISMATCH",
                }:
                    raise
                raise PilotPersistenceError("PERSISTED_STATE_INVALID") from exc
            if _record_count(state) != metadata[2]:
                raise PilotPersistenceError("CHECKPOINT_RECORD_COUNT_MISMATCH")
            actual_digest = state_sha256(state)
            if actual_digest != metadata[0]:
                raise PilotPersistenceError("CHECKPOINT_DIGEST_MISMATCH")
            if actual_digest != expected_state_sha256:
                raise PilotPersistenceError("CHECKPOINT_RECEIPT_MISMATCH")
            return state

    def status(self) -> RepositoryStatus:
        with self._connect() as conn:
            self._require_schema(conn)
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            count = conn.execute("SELECT COUNT(*) FROM pilot_checkpoints").fetchone()[0]
            return RepositoryStatus(
                schema_version=_SCHEMA_VERSION,
                checkpoint_count=count,
                integrity_check=integrity,
            )

    def backup_to(self, destination: str | Path) -> Path:
        target = Path(destination)
        if target == self._path:
            raise PilotPersistenceError("BACKUP_DESTINATION_INVALID")
        target.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as source, closing(sqlite3.connect(target)) as backup:
            self._require_schema(source)
            source.backup(backup)
        _restrict_file(target)
        return target

    def _enforce_limits(self, state: PersistentPilotState) -> None:
        checks = (
            (len(state.tenants), self._limits.max_tenants, "TENANT_CAPACITY_EXCEEDED"),
            (len(state.accounts), self._limits.max_accounts, "ACCOUNT_CAPACITY_EXCEEDED"),
            (len(state.memberships), self._limits.max_memberships, "MEMBERSHIP_CAPACITY_EXCEEDED"),
            (len(state.invites), self._limits.max_invites, "INVITE_CAPACITY_EXCEEDED"),
            (len(state.sessions), self._limits.max_sessions, "SESSION_CAPACITY_EXCEEDED"),
            (len(state.verifiers), self._limits.max_verifiers, "VERIFIER_CAPACITY_EXCEEDED"),
            (len(state.audit_events), self._limits.max_audit_events, "AUDIT_CAPACITY_EXCEEDED"),
        )
        for current, limit, code in checks:
            if current > limit:
                raise PilotPersistenceError(code)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self._path)
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout = 5000")
            conn.row_factory = sqlite3.Row
            yield conn
        except Exception:
            conn.rollback()
            raise
        else:
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _require_schema(conn: sqlite3.Connection) -> None:
        try:
            row = conn.execute(
                "SELECT schema_version FROM pilot_schema_metadata WHERE id = 1"
            ).fetchone()
        except sqlite3.DatabaseError as exc:
            raise PilotPersistenceError("SCHEMA_NOT_INITIALIZED") from exc
        if row is None:
            raise PilotPersistenceError("SCHEMA_NOT_INITIALIZED")
        if row[0] != _SCHEMA_VERSION:
            raise PilotPersistenceError("SCHEMA_VERSION_UNSUPPORTED")


def state_sha256(state: PersistentPilotState) -> str:
    payload = _canonical_state(state)
    return hashlib.sha256(payload).hexdigest()


def _validate_state(state: PersistentPilotState) -> None:
    tenants = _unique(state.tenants, "tenant_id", "TENANT_DUPLICATE")
    accounts = _unique(state.accounts, "account_id", "ACCOUNT_DUPLICATE")
    memberships = _unique(
        state.memberships,
        "membership_id",
        "MEMBERSHIP_DUPLICATE",
    )
    invites = _unique(state.invites, "invite_id", "INVITE_DUPLICATE")
    sessions = _unique(state.sessions, "session_id", "SESSION_DUPLICATE")
    verifiers = _unique(state.verifiers, "record_id", "VERIFIER_DUPLICATE")
    digests = _unique(
        state.session_token_digests,
        "session_id",
        "SESSION_DIGEST_DUPLICATE",
    )
    _unique(state.audit_events, "event_id", "AUDIT_EVENT_DUPLICATE")
    token_values = [item.token_sha256 for item in state.session_token_digests]
    if len(token_values) != len(set(token_values)):
        raise PilotPersistenceError("SESSION_DIGEST_VALUE_DUPLICATE")

    for account in state.accounts:
        credential = verifiers.get(account.credential_record_id)
        recovery = verifiers.get(account.recovery_record_id)
        if credential is None or credential.purpose is not VerifierPurpose.PASSWORD:
            raise PilotPersistenceError("ACCOUNT_CREDENTIAL_REFERENCE_INVALID")
        if recovery is None or recovery.purpose is not VerifierPurpose.RECOVERY:
            raise PilotPersistenceError("ACCOUNT_RECOVERY_REFERENCE_INVALID")
        if credential.superseded_at is not None or recovery.superseded_at is not None:
            raise PilotPersistenceError("ACCOUNT_ACTIVE_VERIFIER_REQUIRED")

    membership_pairs: set[tuple[str, str]] = set()
    for membership in state.memberships:
        if membership.tenant_id not in tenants or membership.account_id not in accounts:
            raise PilotPersistenceError("MEMBERSHIP_REFERENCE_INVALID")
        pair = (membership.tenant_id, membership.account_id)
        if pair in membership_pairs:
            raise PilotPersistenceError("MEMBERSHIP_TENANT_ACCOUNT_DUPLICATE")
        membership_pairs.add(pair)

    for invite in state.invites:
        verifier = verifiers.get(invite.secret_verifier_record_id)
        if invite.tenant_id not in tenants:
            raise PilotPersistenceError("INVITE_TENANT_REFERENCE_INVALID")
        if verifier is None or verifier.purpose is not VerifierPurpose.INVITE:
            raise PilotPersistenceError("INVITE_VERIFIER_REFERENCE_INVALID")

    if set(sessions) != set(digests):
        raise PilotPersistenceError("SESSION_DIGEST_CARDINALITY_INVALID")
    for session in state.sessions:
        membership = memberships.get(session.membership_id)
        if (
            session.account_id not in accounts
            or session.tenant_id not in tenants
            or membership is None
            or membership.account_id != session.account_id
            or membership.tenant_id != session.tenant_id
            or membership.role is not session.role
        ):
            raise PilotPersistenceError("SESSION_REFERENCE_INVALID")

    for event in state.audit_events:
        if event.tenant_id not in tenants:
            raise PilotPersistenceError("AUDIT_TENANT_REFERENCE_INVALID")


def _canonical_state(state: PersistentPilotState) -> bytes:
    def normalize(value):
        if isinstance(value, datetime):
            return _dt(value)
        if isinstance(value, StrEnum):
            return value.value
        if isinstance(value, tuple):
            return [normalize(item) for item in value]
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in sorted(value.items())}
        return value

    payload = {
        "tenants": [normalize(asdict(item)) for item in sorted(state.tenants, key=lambda x: x.tenant_id)],
        "accounts": [normalize(asdict(item)) for item in sorted(state.accounts, key=lambda x: x.account_id)],
        "memberships": [normalize(asdict(item)) for item in sorted(state.memberships, key=lambda x: x.membership_id)],
        "invites": [normalize(asdict(item)) for item in sorted(state.invites, key=lambda x: x.invite_id)],
        "sessions": [normalize(asdict(item)) for item in sorted(state.sessions, key=lambda x: x.session_id)],
        "verifiers": [normalize(asdict(item)) for item in sorted(state.verifiers, key=lambda x: x.record_id)],
        "session_token_digests": [normalize(asdict(item)) for item in sorted(state.session_token_digests, key=lambda x: x.session_id)],
        "audit_events": [normalize(asdict(item)) for item in sorted(state.audit_events, key=lambda x: x.event_id)],
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _record_count(state: PersistentPilotState) -> int:
    return sum(
        len(value)
        for value in (
            state.tenants,
            state.accounts,
            state.memberships,
            state.invites,
            state.sessions,
            state.verifiers,
            state.session_token_digests,
            state.audit_events,
        )
    )


def _unique(items: tuple, attribute: str, code: str) -> dict[str, object]:
    result: dict[str, object] = {}
    for item in items:
        key = getattr(item, attribute)
        if key in result:
            raise PilotPersistenceError(code)
        result[key] = item
    return result


def _safe_id(value: object, code: str) -> str:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise PilotPersistenceError(code)
    return value


def _utc(value: object, code: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise PilotPersistenceError(code)
    return value.astimezone(UTC)


def _dt(value: datetime) -> str:
    return _utc(value, "DATETIME_INVALID").isoformat().replace("+00:00", "Z")


def _parse_dt(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except (TypeError, ValueError) as exc:
        raise PilotPersistenceError("PERSISTED_DATETIME_INVALID") from exc


def _restrict_file(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError as exc:
        raise PilotPersistenceError("DATABASE_PERMISSION_HARDENING_FAILED") from exc


def _insert_state(conn: sqlite3.Connection, checkpoint: str, state: PersistentPilotState) -> None:
    conn.executemany(
        "INSERT INTO pilot_verifiers VALUES(?, ?, ?, ?, ?, ?, ?)",
        [
            (
                checkpoint,
                item.record_id,
                item.purpose.value,
                item.algorithm,
                item.verifier,
                _dt(item.created_at),
                _dt(item.superseded_at) if item.superseded_at else None,
            )
            for item in state.verifiers
        ],
    )
    conn.executemany(
        "INSERT INTO pilot_tenants VALUES(?, ?, ?, ?, ?)",
        [
            (checkpoint, item.tenant_id, item.tenant_alias, item.status.value, _dt(item.created_at))
            for item in state.tenants
        ],
    )
    conn.executemany(
        "INSERT INTO pilot_accounts VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                checkpoint,
                item.account_id,
                item.pseudonym,
                item.credential_record_id,
                item.recovery_record_id,
                item.credential_algorithm,
                item.authentication_epoch,
                item.status.value,
                _dt(item.created_at),
            )
            for item in state.accounts
        ],
    )
    conn.executemany(
        "INSERT INTO pilot_memberships VALUES(?, ?, ?, ?, ?, ?, ?)",
        [
            (
                checkpoint,
                item.membership_id,
                item.tenant_id,
                item.account_id,
                item.role.value,
                item.status.value,
                _dt(item.created_at),
            )
            for item in state.memberships
        ],
    )
    conn.executemany(
        "INSERT INTO pilot_invites VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                checkpoint,
                item.invite_id,
                item.tenant_id,
                item.role.value,
                item.secret_verifier_record_id,
                item.status.value,
                _dt(item.issued_at),
                _dt(item.expires_at),
            )
            for item in state.invites
        ],
    )
    conn.executemany(
        "INSERT INTO pilot_sessions VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                checkpoint,
                item.session_id,
                item.account_id,
                item.tenant_id,
                item.membership_id,
                item.role.value,
                item.authentication_epoch,
                item.status.value,
                _dt(item.issued_at),
                _dt(item.expires_at),
            )
            for item in state.sessions
        ],
    )
    conn.executemany(
        "INSERT INTO pilot_session_token_digests VALUES(?, ?, ?)",
        [(checkpoint, item.session_id, item.token_sha256) for item in state.session_token_digests],
    )
    conn.executemany(
        "INSERT INTO pilot_audit_events VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                checkpoint,
                item.event_id,
                item.event_type,
                item.actor_reference,
                item.tenant_id,
                item.subject_id,
                _dt(item.occurred_at),
                json.dumps(item.codes, separators=(",", ":")),
            )
            for item in state.audit_events
        ],
    )


def _load_state(conn: sqlite3.Connection, checkpoint: str) -> PersistentPilotState:
    rows = lambda table: conn.execute(
        f"SELECT * FROM {table} WHERE checkpoint_id = ? ORDER BY 2",
        (checkpoint,),
    ).fetchall()
    return PersistentPilotState(
        verifiers=tuple(
            PersistedVerifier(
                record_id=row["record_id"],
                purpose=VerifierPurpose(row["purpose"]),
                algorithm=row["algorithm"],
                verifier=row["verifier"],
                created_at=_parse_dt(row["created_at"]),
                superseded_at=_parse_dt(row["superseded_at"]) if row["superseded_at"] else None,
            )
            for row in rows("pilot_verifiers")
        ),
        tenants=tuple(
            Tenant(
                tenant_id=row["tenant_id"],
                tenant_alias=row["tenant_alias"],
                status=TenantStatus(row["status"]),
                created_at=_parse_dt(row["created_at"]),
            )
            for row in rows("pilot_tenants")
        ),
        accounts=tuple(
            PseudonymousAccount(
                account_id=row["account_id"],
                pseudonym=row["pseudonym"],
                credential_record_id=row["credential_record_id"],
                recovery_record_id=row["recovery_record_id"],
                credential_algorithm=row["credential_algorithm"],
                authentication_epoch=row["authentication_epoch"],
                status=AccountStatus(row["status"]),
                created_at=_parse_dt(row["created_at"]),
            )
            for row in rows("pilot_accounts")
        ),
        memberships=tuple(
            TenantMembership(
                membership_id=row["membership_id"],
                tenant_id=row["tenant_id"],
                account_id=row["account_id"],
                role=TenantRole(row["role"]),
                status=MembershipStatus(row["status"]),
                created_at=_parse_dt(row["created_at"]),
            )
            for row in rows("pilot_memberships")
        ),
        invites=tuple(
            TenantInvite(
                invite_id=row["invite_id"],
                tenant_id=row["tenant_id"],
                role=TenantRole(row["role"]),
                secret_verifier_record_id=row["secret_verifier_record_id"],
                status=InviteStatus(row["status"]),
                issued_at=_parse_dt(row["issued_at"]),
                expires_at=_parse_dt(row["expires_at"]),
            )
            for row in rows("pilot_invites")
        ),
        sessions=tuple(
            SessionPrincipal(
                session_id=row["session_id"],
                account_id=row["account_id"],
                tenant_id=row["tenant_id"],
                membership_id=row["membership_id"],
                role=TenantRole(row["role"]),
                authentication_epoch=row["authentication_epoch"],
                status=SessionStatus(row["status"]),
                issued_at=_parse_dt(row["issued_at"]),
                expires_at=_parse_dt(row["expires_at"]),
            )
            for row in rows("pilot_sessions")
        ),
        session_token_digests=tuple(
            SessionTokenDigestRecord(
                session_id=row["session_id"],
                token_sha256=row["token_sha256"],
            )
            for row in rows("pilot_session_token_digests")
        ),
        audit_events=tuple(
            PersistentAuditEvent(
                event_id=row["event_id"],
                event_type=row["event_type"],
                actor_reference=row["actor_reference"],
                tenant_id=row["tenant_id"],
                subject_id=row["subject_id"],
                occurred_at=_parse_dt(row["occurred_at"]),
                codes=tuple(json.loads(row["codes_json"])),
            )
            for row in rows("pilot_audit_events")
        ),
    )


def _immutable_trigger_sql(table: str) -> str:
    return f"""
    CREATE TRIGGER IF NOT EXISTS {table}_immutable_update
    BEFORE UPDATE ON {table}
    BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END;
    CREATE TRIGGER IF NOT EXISTS {table}_immutable_delete
    BEFORE DELETE ON {table}
    BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END;
    """


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS pilot_schema_metadata(
    id INTEGER PRIMARY KEY CHECK(id = 1),
    schema_version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS pilot_checkpoints(
    checkpoint_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    state_sha256 TEXT NOT NULL CHECK(length(state_sha256) = 64),
    schema_version INTEGER NOT NULL,
    record_count INTEGER NOT NULL CHECK(record_count >= 0)
);
CREATE TABLE IF NOT EXISTS pilot_verifiers(
    checkpoint_id TEXT NOT NULL,
    record_id TEXT NOT NULL,
    purpose TEXT NOT NULL,
    algorithm TEXT NOT NULL,
    verifier TEXT NOT NULL,
    created_at TEXT NOT NULL,
    superseded_at TEXT,
    PRIMARY KEY(checkpoint_id, record_id),
    FOREIGN KEY(checkpoint_id) REFERENCES pilot_checkpoints(checkpoint_id)
);
CREATE TABLE IF NOT EXISTS pilot_tenants(
    checkpoint_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    tenant_alias TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(checkpoint_id, tenant_id),
    FOREIGN KEY(checkpoint_id) REFERENCES pilot_checkpoints(checkpoint_id)
);
CREATE TABLE IF NOT EXISTS pilot_accounts(
    checkpoint_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    pseudonym TEXT NOT NULL,
    credential_record_id TEXT NOT NULL,
    recovery_record_id TEXT NOT NULL,
    credential_algorithm TEXT NOT NULL,
    authentication_epoch INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(checkpoint_id, account_id),
    FOREIGN KEY(checkpoint_id, credential_record_id) REFERENCES pilot_verifiers(checkpoint_id, record_id),
    FOREIGN KEY(checkpoint_id, recovery_record_id) REFERENCES pilot_verifiers(checkpoint_id, record_id)
);
CREATE TABLE IF NOT EXISTS pilot_memberships(
    checkpoint_id TEXT NOT NULL,
    membership_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    role TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(checkpoint_id, membership_id),
    UNIQUE(checkpoint_id, tenant_id, account_id),
    FOREIGN KEY(checkpoint_id, tenant_id) REFERENCES pilot_tenants(checkpoint_id, tenant_id),
    FOREIGN KEY(checkpoint_id, account_id) REFERENCES pilot_accounts(checkpoint_id, account_id)
);
CREATE TABLE IF NOT EXISTS pilot_invites(
    checkpoint_id TEXT NOT NULL,
    invite_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    role TEXT NOT NULL,
    secret_verifier_record_id TEXT NOT NULL,
    status TEXT NOT NULL,
    issued_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    PRIMARY KEY(checkpoint_id, invite_id),
    FOREIGN KEY(checkpoint_id, tenant_id) REFERENCES pilot_tenants(checkpoint_id, tenant_id),
    FOREIGN KEY(checkpoint_id, secret_verifier_record_id) REFERENCES pilot_verifiers(checkpoint_id, record_id)
);
CREATE TABLE IF NOT EXISTS pilot_sessions(
    checkpoint_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    membership_id TEXT NOT NULL,
    role TEXT NOT NULL,
    authentication_epoch INTEGER NOT NULL,
    status TEXT NOT NULL,
    issued_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    PRIMARY KEY(checkpoint_id, session_id),
    FOREIGN KEY(checkpoint_id, account_id) REFERENCES pilot_accounts(checkpoint_id, account_id),
    FOREIGN KEY(checkpoint_id, tenant_id) REFERENCES pilot_tenants(checkpoint_id, tenant_id),
    FOREIGN KEY(checkpoint_id, membership_id) REFERENCES pilot_memberships(checkpoint_id, membership_id)
);
CREATE TABLE IF NOT EXISTS pilot_session_token_digests(
    checkpoint_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    token_sha256 TEXT NOT NULL,
    PRIMARY KEY(checkpoint_id, session_id),
    UNIQUE(checkpoint_id, token_sha256),
    FOREIGN KEY(checkpoint_id, session_id) REFERENCES pilot_sessions(checkpoint_id, session_id)
);
CREATE TABLE IF NOT EXISTS pilot_audit_events(
    checkpoint_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor_reference TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    codes_json TEXT NOT NULL,
    PRIMARY KEY(checkpoint_id, event_id),
    FOREIGN KEY(checkpoint_id, tenant_id) REFERENCES pilot_tenants(checkpoint_id, tenant_id)
);
"""


__all__ = [
    "CheckpointReceipt",
    "PersistedVerifier",
    "PersistentAuditEvent",
    "PersistentPilotState",
    "PersistenceLimits",
    "PilotPersistenceError",
    "RepositoryStatus",
    "SessionTokenDigestRecord",
    "SqlitePilotIdentityRepository",
    "VerifierPurpose",
    "state_sha256",
]
