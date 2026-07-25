from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from quantum.application import _finance_center_auto_inbox_corrective as corrective
from quantum.application._finance_center_auto_inbox_corrective import (
    AutoInboxController,
    AutoInboxError,
)


ROOT = Path(__file__).resolve().parents[1]


class AutoInboxCorrectiveTests(unittest.TestCase):
    def test_terminal_records_are_pruned_deterministically_at_capacity(self) -> None:
        with tempfile.TemporaryDirectory() as raw, patch.object(
            corrective, "_MAX_RECORDS", 2
        ):
            controller = AutoInboxController(Path(raw) / "auto-inbox")
            first = hashlib.sha256(b"first").hexdigest()
            second = hashlib.sha256(b"second").hexdigest()
            third = hashlib.sha256(b"third").hexdigest()
            controller._record(
                first,
                status="COMPLETED",
                source_name="first.xlsx",
                path=controller.completed_dir / "first.xlsx",
            )
            controller._state["records"][first]["updated_at_unix_ns"] = 1
            controller._record(
                second,
                status="REJECTED",
                source_name="second.xlsx",
                path=controller.rejected_dir / "second.xlsx",
            )
            controller._state["records"][second]["updated_at_unix_ns"] = 2
            controller._write_state()

            controller._record(
                third,
                status="COMPLETED",
                source_name="third.xlsx",
                path=controller.completed_dir / "third.xlsx",
            )

            state = json.loads(controller.state_path.read_text(encoding="utf-8"))
            self.assertEqual(len(state["records"]), 2)
            self.assertNotIn(first, state["records"])
            self.assertIn(second, state["records"])
            self.assertIn(third, state["records"])
            self.assertTrue(
                any(
                    event.get("event") == "RECORD_PRUNED"
                    and event.get("sha256") == first
                    for event in state["events"]
                )
            )

    def test_active_records_are_never_silently_pruned(self) -> None:
        with tempfile.TemporaryDirectory() as raw, patch.object(
            corrective, "_MAX_RECORDS", 2
        ):
            controller = AutoInboxController(Path(raw) / "auto-inbox")
            first = hashlib.sha256(b"first").hexdigest()
            second = hashlib.sha256(b"second").hexdigest()
            third = hashlib.sha256(b"third").hexdigest()
            controller._record(
                first,
                status="CLAIMED",
                source_name="first.xlsx",
                path=controller.processing_dir / "first.xlsx",
            )
            controller._record(
                second,
                status="QUEUED",
                source_name="second.xlsx",
                path=controller.processing_dir / "second.xlsx",
            )
            with self.assertRaises(AutoInboxError) as raised:
                controller._record(
                    third,
                    status="COMPLETED",
                    source_name="third.xlsx",
                    path=controller.completed_dir / "third.xlsx",
                )
            self.assertEqual(
                raised.exception.code,
                "AUTO_INBOX_STATE_CAPACITY_EXHAUSTED",
            )
            self.assertEqual(set(controller._state["records"]), {first, second})

    def test_oversized_record_state_is_rejected_on_load(self) -> None:
        with tempfile.TemporaryDirectory() as raw, patch.object(
            corrective, "_MAX_RECORDS", 1
        ):
            root = Path(raw) / "auto-inbox"
            root.mkdir(parents=True)
            records = {}
            for index in range(2):
                digest = hashlib.sha256(str(index).encode()).hexdigest()
                records[digest] = {
                    "sha256": digest,
                    "status": "COMPLETED",
                    "source_name": f"{index}.xlsx",
                    "internal_path": f"completed/{index}.xlsx",
                    "reason": None,
                    "updated_at_unix_ns": index,
                    "marketplace_write_enabled": False,
                }
            (root / "state.json").write_text(
                json.dumps(
                    {
                        "schema_version": "quantum-auto-inbox-v1",
                        "records": records,
                        "events": [],
                        "marketplace_write_enabled": False,
                        "release_scope": "WB_ONLY",
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(AutoInboxError) as raised:
                AutoInboxController(root)
            self.assertEqual(
                raised.exception.code,
                "AUTO_INBOX_STATE_RECORD_LIMIT_EXCEEDED",
            )

    def test_duplicate_is_rejected_when_post_move_digest_changes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            controller = AutoInboxController(Path(raw) / "auto-inbox")
            source = controller.incoming_dir / "duplicate.xlsx"
            source.write_bytes(b"expected")
            expected = hashlib.sha256(b"expected").hexdigest()
            changed = hashlib.sha256(b"changed").hexdigest()
            with patch.object(
                corrective,
                "_sha256_file",
                side_effect=(expected, changed),
            ):
                with self.assertRaises(AutoInboxError) as raised:
                    controller.archive_duplicate(source, expected)
            self.assertEqual(
                raised.exception.code,
                "AUTO_INBOX_DUPLICATE_HASH_MISMATCH",
            )
            self.assertFalse(any(controller.completed_dir.iterdir()))
            rejected = tuple(controller.rejected_dir.iterdir())
            self.assertEqual(len(rejected), 1)
            state = json.loads(controller.state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["events"][-1]["event"], "DUPLICATE_HASH_MISMATCH")

    def test_desktop_uses_corrective_controller_without_navigation_change(self) -> None:
        center = (ROOT / "src/quantum/application/finance_center.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("_finance_center_auto_inbox_corrective", center)
        self.assertIn("FinanceCenterAutoInboxMixin", center)


if __name__ == "__main__":
    unittest.main()
