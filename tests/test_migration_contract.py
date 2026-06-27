import unittest
from pathlib import Path


class MigrationContractTests(unittest.TestCase):
    def test_foundation_migration_contains_required_constraints(self):
        root = Path(__file__).resolve().parents[1]
        sql = (root / "migrations/0001_foundation.sql").read_text(encoding="utf-8")
        required = [
            "UNIQUE (",
            "source_file_sha256",
            "idempotency_key",
            "supersedes_event_id",
            "reversal_of_event_id",
            "worker_lease",
            "CHECK (revision >= 1)",
        ]
        for marker in required:
            self.assertIn(marker, sql)

    def test_foundation_migration_is_non_destructive(self):
        root = Path(__file__).resolve().parents[1]
        sql = (root / "migrations/0001_foundation.sql").read_text(encoding="utf-8").upper()
        self.assertNotIn("DROP TABLE", sql)
        self.assertNotIn("TRUNCATE", sql)
        self.assertNotIn("DELETE FROM", sql)


if __name__ == "__main__":
    unittest.main()
