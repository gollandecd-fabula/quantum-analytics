from __future__ import annotations

from contextlib import closing
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import sqlite3
import tempfile
import unittest

import tests.test_persistent_identity_repository as _v1
from quantum.pilot import persistence as _persistence_v1
from quantum.pilot.persistence_v2 import (
    AttestedSqlitePilotIdentityRepository,
    PilotPersistenceError,
    expected_schema_sha256,
)


class LegacyCompatibleAttestedRepository(
    AttestedSqlitePilotIdentityRepository
):
    """Test-only adapter for running the R1 API contract against R2 internals."""

    def load_checkpoint(
        self,
        receipt,
        *,
        expected_state_sha256=None,
    ):
        if isinstance(receipt, str):
            return _persistence_v1.SqlitePilotIdentityRepository.load_checkpoint(
                self,
                receipt,
                expected_state_sha256=expected_state_sha256,
            )
        return super().load_checkpoint(receipt)


class PersistentIdentityRepositoryV2BehaviorTests(
    _v1.PersistentIdentityRepositoryTests
):
    """Run all 24 R1 repository behaviors against the R2 implementation."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "pilot.db"
        self.repo = LegacyCompatibleAttestedRepository(self.path)
        self.repo.initialize()


class AttestedReceiptSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "pilot.db"
        self.repo = AttestedSqlitePilotIdentityRepository(self.path)
        self.repo.initialize()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_full_receipt_round_trip(self):
        state = _v1.sample_state()
        receipt = self.repo.save_checkpoint(
            checkpoint_id="checkpoint-a",
            state=state,
            created_at=_v1.NOW,
        )
        self.assertEqual(receipt.schema_sha256, expected_schema_sha256())
        self.assertEqual(len(receipt.attestation_sha256), 64)
        self.assertEqual(self.repo.load_checkpoint(receipt), state)

    def test_digest_only_load_is_disabled_by_default(self):
        receipt = self.repo.save_checkpoint(
            checkpoint_id="checkpoint-a",
            state=_v1.sample_state(),
            created_at=_v1.NOW,
        )
        with self.assertRaisesRegex(
            PilotPersistenceError,
            "ATTESTED_CHECKPOINT_RECEIPT_REQUIRED",
        ):
            self.repo.load_checkpoint(
                receipt.checkpoint_id,
                expected_state_sha256=receipt.state_sha256,
            )

    def test_receipt_substitution_with_identical_state_is_rejected(self):
        state = _v1.sample_state()
        first = self.repo.save_checkpoint(
            checkpoint_id="checkpoint-a",
            state=state,
            created_at=_v1.NOW,
        )
        second = self.repo.save_checkpoint(
            checkpoint_id="checkpoint-b",
            state=state,
            created_at=_v1.NOW + timedelta(minutes=1),
        )
        substituted = replace(second, checkpoint_id=first.checkpoint_id)
        with self.assertRaisesRegex(
            PilotPersistenceError,
            "CHECKPOINT_RECEIPT_MISMATCH",
        ):
            self.repo.load_checkpoint(substituted)

    def test_checkpoint_timestamp_rewrite_is_detected(self):
        receipt = self.repo.save_checkpoint(
            checkpoint_id="checkpoint-a",
            state=_v1.sample_state(),
            created_at=_v1.NOW,
        )
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("DROP TRIGGER pilot_checkpoints_immutable_update")
            conn.execute(
                "UPDATE pilot_checkpoints SET created_at = ? "
                "WHERE checkpoint_id = ?",
                (
                    (_v1.NOW + timedelta(days=1))
                    .isoformat()
                    .replace("+00:00", "Z"),
                    receipt.checkpoint_id,
                ),
            )
            conn.executescript(
                _persistence_v1._immutable_trigger_sql("pilot_checkpoints")
            )
            conn.commit()
        with self.assertRaisesRegex(
            PilotPersistenceError,
            "CHECKPOINT_RECEIPT_MISMATCH",
        ):
            self.repo.load_checkpoint(receipt)

    def test_trigger_removal_without_row_change_is_detected(self):
        receipt = self.repo.save_checkpoint(
            checkpoint_id="checkpoint-a",
            state=_v1.sample_state(),
            created_at=_v1.NOW,
        )
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("DROP TRIGGER pilot_tenants_immutable_update")
            conn.commit()
        with self.assertRaisesRegex(
            PilotPersistenceError,
            "SCHEMA_FINGERPRINT_MISMATCH",
        ):
            self.repo.load_checkpoint(receipt)

    def test_altered_preexisting_schema_is_rejected(self):
        path = Path(self.tmp.name) / "altered.db"
        with closing(sqlite3.connect(path)) as conn:
            conn.execute(
                "CREATE TABLE pilot_checkpoints(checkpoint_id TEXT PRIMARY KEY)"
            )
            conn.commit()
        repository = AttestedSqlitePilotIdentityRepository(path)
        with self.assertRaisesRegex(
            PilotPersistenceError,
            "SCHEMA_INITIALIZATION_FAILED|SCHEMA_FINGERPRINT_MISMATCH",
        ):
            repository.initialize()

    def test_backup_restores_with_same_attested_receipt(self):
        state = _v1.sample_state()
        receipt = self.repo.save_checkpoint(
            checkpoint_id="checkpoint-a",
            state=state,
            created_at=_v1.NOW,
        )
        backup = Path(self.tmp.name) / "backup.db"
        self.repo.backup_to(backup)
        restored = AttestedSqlitePilotIdentityRepository(backup)
        self.assertEqual(restored.load_checkpoint(receipt), state)

    def test_database_symlink_is_rejected(self):
        target = Path(self.tmp.name) / "target.db"
        target.touch()
        link = Path(self.tmp.name) / "link.db"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlink not supported")
        repository = AttestedSqlitePilotIdentityRepository(link)
        with self.assertRaisesRegex(
            PilotPersistenceError,
            "DATABASE_SYMLINK_FORBIDDEN",
        ):
            repository.initialize()


if __name__ == "__main__":
    unittest.main()
