import tempfile
import unittest
from pathlib import Path

from quantum.ingestion.proof_pipeline import (
    build_metric_evidence,
    import_csv_for_proof,
)


class A6ProofPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.valid = cls.root / "tests/contracts/fixtures/a6/wb-synthetic-valid.csv"
        cls.unknown = cls.root / "tests/contracts/fixtures/a6/wb-synthetic-unknown-schema.csv"
        cls.semantic = cls.root / "tests/contracts/fixtures/a6/wb-synthetic-semantic-drift.csv"

    @staticmethod
    def common(base):
        return {
            "raw_storage_root": base / "raw",
            "quarantine_root": base / "quarantine",
            "ledger_path": base / "ledger/events.json",
            "source_records_path": base / "ledger/source-records.jsonl",
        }

    def test_exact_replay_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            first = import_csv_for_proof(source_path=self.valid, **self.common(base))
            replay = import_csv_for_proof(source_path=self.valid, **self.common(base))
            self.assertEqual(first.inserted_events, 4)
            self.assertEqual(replay.inserted_events, 0)
            self.assertEqual(replay.duplicate_events, 4)

    def test_unknown_schema_is_quarantined(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = import_csv_for_proof(
                source_path=self.unknown,
                **self.common(Path(tmp)),
            )
            self.assertTrue(result.quarantined)
            self.assertEqual(result.status, "QUARANTINED")

    def test_semantic_drift_is_quarantined(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = import_csv_for_proof(
                source_path=self.semantic,
                **self.common(Path(tmp)),
            )
            self.assertTrue(result.quarantined)
            self.assertTrue(
                any("quantity: invalid integer" in item for item in result.diagnostics)
            )

    def test_evidence_chain_yields_expected_current_amount(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            imported = import_csv_for_proof(
                source_path=self.valid,
                **self.common(base),
            )
            evidence = build_metric_evidence(
                ledger_path=base / "ledger/events.json",
                source_file_sha256=imported.file_sha256,
                source_records_path=base / "ledger/source-records.jsonl",
            )
            self.assertEqual(evidence["value"], "1400.00")
            self.assertEqual(evidence["active_event_ids"], ["evt-sale-002-r2"])
            self.assertEqual(
                {item["reason"] for item in evidence["excluded_events"]},
                {"REVERSED", "SUPERSEDED"},
            )


if __name__ == "__main__":
    unittest.main()
