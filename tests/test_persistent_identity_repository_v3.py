from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

import tests.test_persistent_identity_repository as _v1
from quantum.pilot.persistence_v2 import (
    AttestedSqlitePilotIdentityRepository,
    PilotPersistenceError,
)


class AttestedRepositoryR3Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "pilot.db"
        self.repo = AttestedSqlitePilotIdentityRepository(self.path)
        self.repo.initialize()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_legacy_digest_argument_is_rejected_with_full_receipt(self):
        receipt = self.repo.save_checkpoint(
            checkpoint_id="checkpoint-a",
            state=_v1.sample_state(),
            created_at=_v1.NOW,
        )
        with self.assertRaisesRegex(
            PilotPersistenceError,
            "LEGACY_DIGEST_ARGUMENT_FORBIDDEN",
        ):
            self.repo.load_checkpoint(
                receipt,
                expected_state_sha256=receipt.state_sha256,
            )

    def test_unexpected_trigger_before_save_is_rejected(self):
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute(
                "CREATE TRIGGER unexpected_copy AFTER INSERT ON pilot_tenants "
                "BEGIN SELECT 1; END"
            )
            conn.commit()
        with self.assertRaisesRegex(
            PilotPersistenceError,
            "SCHEMA_FINGERPRINT_MISMATCH",
        ):
            self.repo.save_checkpoint(
                checkpoint_id="checkpoint-a",
                state=_v1.sample_state(),
                created_at=_v1.NOW,
            )


if __name__ == "__main__":
    unittest.main()
