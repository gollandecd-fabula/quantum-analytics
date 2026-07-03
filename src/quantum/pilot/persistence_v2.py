from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import sqlite3

from . import persistence as _v1
from .persistence import (
    PersistedVerifier,
    PersistentAuditEvent,
    PersistentPilotState,
    PersistenceLimits,
    PilotPersistenceError,
    SessionTokenDigestRecord,
    VerifierPurpose,
)


@dataclass(frozen=True, slots=True)
class AttestedCheckpointReceipt:
    checkpoint_id: str
    state_sha256: str
    schema_sha256: str
    created_at: datetime
    schema_version: int
    record_count: int

    def __post_init__(self) -> None:
        _v1._safe_id(self.checkpoint_id, "CHECKPOINT_RECEIPT_ID_INVALID")
        for value, code in (
            (self.state_sha256, "CHECKPOINT_RECEIPT_STATE_DIGEST_INVALID"),
            (self.schema_sha256, "CHECKPOINT_RECEIPT_SCHEMA_DIGEST_INVALID"),
        ):
            if not isinstance(value, str) or _v1._SHA256.fullmatch(value) is None:
                raise PilotPersistenceError(code)
        _v1._utc(self.created_at, "CHECKPOINT_RECEIPT_TIME_INVALID")
        if self.schema_version != _v1._SCHEMA_VERSION:
            raise PilotPersistenceError("CHECKPOINT_RECEIPT_SCHEMA_VERSION_INVALID")
        if (
            not isinstance(self.record_count, int)
            or isinstance(self.record_count, bool)
            or self.record_count < 0
        ):
            raise PilotPersistenceError("CHECKPOINT_RECEIPT_RECORD_COUNT_INVALID")

    @property
    def attestation_sha256(self) -> str:
        payload = {
            "checkpoint_id": self.checkpoint_id,
            "state_sha256": self.state_sha256,
            "schema_sha256": self.schema_sha256,
            "created_at": _v1._dt(self.created_at),
            "schema_version": self.schema_version,
            "record_count": self.record_count,
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class AttestedRepositoryStatus:
    schema_version: int
    schema_sha256: str
    checkpoint_count: int
    integrity_check: str
    production_ready: bool = False
    encryption_at_rest: bool = False


def schema_sha256(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        """
        SELECT type, name, tbl_name, sql
        FROM sqlite_master
        WHERE sql IS NOT NULL
          AND type IN ('table', 'trigger', 'index')
          AND (name LIKE 'pilot_%' OR tbl_name LIKE 'pilot_%')
        ORDER BY type, name, tbl_name
        """
    ).fetchall()
    payload = [
        [row[0], row[1], row[2], " ".join(row[3].split())]
        for row in rows
    ]
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@lru_cache(maxsize=1)
def expected_schema_sha256() -> str:
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(_v1._SCHEMA_SQL)
        for table in _v1._IMMUTABLE_TABLES:
            conn.executescript(_v1._immutable_trigger_sql(table))
        return schema_sha256(conn)
    finally:
        conn.close()


def _assert_expected_schema(conn: sqlite3.Connection) -> str:
    actual = schema_sha256(conn)
    if actual != expected_schema_sha256():
        raise PilotPersistenceError("SCHEMA_FINGERPRINT_MISMATCH")
    return actual


class AttestedSqlitePilotIdentityRepository(_v1.SqlitePilotIdentityRepository):
    """P2.2 R2 repository with full receipt and schema attestation.

    The legacy digest-only load path is disabled. Compatibility coverage is
    provided only by a test-local adapter and is not part of this API.
    """

    def __init__(
        self,
        database_path: str | Path,
        *,
        limits: PersistenceLimits | None = None,
    ) -> None:
        super().__init__(database_path, limits=limits)

    def initialize(self) -> None:
        if self.path.is_symlink():
            raise PilotPersistenceError("DATABASE_SYMLINK_FORBIDDEN")
        try:
            super().initialize()
        except sqlite3.DatabaseError as exc:
            raise PilotPersistenceError("SCHEMA_INITIALIZATION_FAILED") from exc
        with self._connect() as conn:
            self._require_schema(conn)
            _assert_expected_schema(conn)

    def save_checkpoint(
        self,
        *,
        checkpoint_id: str,
        state: PersistentPilotState,
        created_at: datetime,
    ) -> AttestedCheckpointReceipt:
        with self._connect() as conn:
            self._require_schema(conn)
            schema_digest = _assert_expected_schema(conn)
        receipt = super().save_checkpoint(
            checkpoint_id=checkpoint_id,
            state=state,
            created_at=created_at,
        )
        return AttestedCheckpointReceipt(
            checkpoint_id=receipt.checkpoint_id,
            state_sha256=receipt.state_sha256,
            schema_sha256=schema_digest,
            created_at=receipt.created_at,
            schema_version=receipt.schema_version,
            record_count=receipt.record_count,
        )

    def load_checkpoint(
        self,
        receipt: AttestedCheckpointReceipt | str | None,
        *,
        expected_state_sha256: str | None = None,
    ) -> PersistentPilotState:
        if not isinstance(receipt, AttestedCheckpointReceipt):
            raise PilotPersistenceError("ATTESTED_CHECKPOINT_RECEIPT_REQUIRED")

        checkpoint = receipt.checkpoint_id
        with self._connect() as conn:
            self._require_schema(conn)
            conn.execute("BEGIN")
            schema_digest = _assert_expected_schema(conn)
            if schema_digest != receipt.schema_sha256:
                raise PilotPersistenceError("CHECKPOINT_SCHEMA_MISMATCH")
            metadata = conn.execute(
                "SELECT created_at, state_sha256, schema_version, record_count "
                "FROM pilot_checkpoints WHERE checkpoint_id = ?",
                (checkpoint,),
            ).fetchone()
            if metadata is None:
                raise PilotPersistenceError("CHECKPOINT_NOT_FOUND")
            if metadata["schema_version"] != _v1._SCHEMA_VERSION:
                raise PilotPersistenceError("SCHEMA_VERSION_UNSUPPORTED")
            if (
                metadata["state_sha256"] != receipt.state_sha256
                or metadata["schema_version"] != receipt.schema_version
                or metadata["record_count"] != receipt.record_count
                or _v1._parse_dt(metadata["created_at"])
                != receipt.created_at.astimezone(UTC)
            ):
                raise PilotPersistenceError("CHECKPOINT_RECEIPT_MISMATCH")
            try:
                state = _v1._load_state(conn, checkpoint)
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
            if _v1._record_count(state) != receipt.record_count:
                raise PilotPersistenceError("CHECKPOINT_RECORD_COUNT_MISMATCH")
            actual_digest = _v1.state_sha256(state)
            if actual_digest != metadata["state_sha256"]:
                raise PilotPersistenceError("CHECKPOINT_DIGEST_MISMATCH")
            if actual_digest != receipt.state_sha256:
                raise PilotPersistenceError("CHECKPOINT_RECEIPT_MISMATCH")
            return state

    def status(self) -> AttestedRepositoryStatus:
        with self._connect() as conn:
            self._require_schema(conn)
            schema_digest = _assert_expected_schema(conn)
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            count = conn.execute(
                "SELECT COUNT(*) FROM pilot_checkpoints"
            ).fetchone()[0]
            return AttestedRepositoryStatus(
                schema_version=_v1._SCHEMA_VERSION,
                schema_sha256=schema_digest,
                checkpoint_count=count,
                integrity_check=integrity,
            )

    def backup_to(self, destination: str | Path) -> Path:
        target = Path(destination)
        if target.is_symlink():
            raise PilotPersistenceError("BACKUP_DESTINATION_INVALID")
        with self._connect() as conn:
            self._require_schema(conn)
            _assert_expected_schema(conn)
        return super().backup_to(target)


__all__ = [
    "AttestedCheckpointReceipt",
    "AttestedRepositoryStatus",
    "AttestedSqlitePilotIdentityRepository",
    "PersistedVerifier",
    "PersistentAuditEvent",
    "PersistentPilotState",
    "PersistenceLimits",
    "PilotPersistenceError",
    "SessionTokenDigestRecord",
    "VerifierPurpose",
    "expected_schema_sha256",
    "schema_sha256",
]
