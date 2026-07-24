from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest

from quantum.application._finance_center_auto_inbox import (
    AutoInboxController,
    AutoInboxError,
)


ROOT = Path(__file__).resolve().parents[1]


def _ready_candidate(controller: AutoInboxController, name: str, payload: bytes):
    source = controller.incoming_dir / name
    source.write_bytes(payload)
    now = source.stat().st_mtime_ns + 1
    controller.scan(now_ns=now)
    return source, controller.scan(now_ns=now)[0]


class AutoInboxControllerTests(unittest.TestCase):
    def test_requires_stable_complete_file_before_ready(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            controller = AutoInboxController(
                Path(raw) / "auto-inbox",
                minimum_age_seconds=1,
                stable_scans_required=2,
            )
            source = controller.incoming_dir / "report.xlsx"
            source.write_bytes(b"first")
            stat = source.stat()
            now = stat.st_mtime_ns + 2_000_000_000
            self.assertEqual(controller.scan(now_ns=now), ())
            source.write_bytes(b"second-version")
            stat = source.stat()
            now = stat.st_mtime_ns + 2_000_000_000
            self.assertEqual(controller.scan(now_ns=now), ())
            ready = controller.scan(now_ns=now)
            self.assertEqual(len(ready), 1)
            self.assertEqual(ready[0].size_bytes, len(b"second-version"))

    def test_ignores_partial_and_unsupported_files(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            controller = AutoInboxController(
                Path(raw) / "auto-inbox",
                minimum_age_seconds=0,
                stable_scans_required=2,
            )
            (controller.incoming_dir / "report.xlsx.part").write_bytes(b"x")
            (controller.incoming_dir / "notes.txt").write_bytes(b"x")
            (controller.incoming_dir / "~$locked.xlsx").write_bytes(b"x")
            controller.scan(now_ns=time.time_ns() + 10_000_000_000)
            self.assertEqual(
                controller.scan(now_ns=time.time_ns() + 10_000_000_000),
                (),
            )

    def test_claim_queue_finalize_and_duplicate_preserve_canonical_record(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            controller = AutoInboxController(
                Path(raw) / "auto-inbox",
                minimum_age_seconds=0,
                stable_scans_required=2,
            )
            payload = b"verified-report"
            source, candidate = _ready_candidate(
                controller, "report.xlsx", payload
            )
            digest = hashlib.sha256(payload).hexdigest()
            processing = controller.claim(candidate, digest)
            controller.mark_queued(digest, processing, source.name)
            final = controller.finalize(
                processing,
                digest,
                success=True,
                reason="ADMISSION_COMPLETE",
                source_name=source.name,
            )
            self.assertTrue(final.is_file())
            self.assertTrue(controller.already_handled(digest))

            duplicate = controller.incoming_dir / "again.xlsx"
            duplicate.write_bytes(payload)
            archived = controller.archive_duplicate(duplicate, digest)
            self.assertTrue(archived.is_file())
            state = json.loads(controller.state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["records"][digest]["status"], "COMPLETED")
            self.assertEqual(state["events"][-1]["event"], "DUPLICATE_ARCHIVED")
            self.assertIs(state["marketplace_write_enabled"], False)
            self.assertEqual(state["release_scope"], "WB_ONLY")

    def test_claim_rejects_changed_source(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            controller = AutoInboxController(
                Path(raw) / "auto-inbox",
                minimum_age_seconds=0,
                stable_scans_required=2,
            )
            source, candidate = _ready_candidate(
                controller, "report.xlsx", b"one"
            )
            source.write_bytes(b"two-two")
            with self.assertRaises(AutoInboxError) as raised:
                controller.claim(
                    candidate,
                    hashlib.sha256(b"one").hexdigest(),
                )
            self.assertEqual(raised.exception.code, "AUTO_INBOX_SOURCE_CHANGED")

    def test_processing_recovery_reopens_queued_digest_for_retry(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "auto-inbox"
            controller = AutoInboxController(
                root,
                minimum_age_seconds=0,
                stable_scans_required=2,
            )
            payload = b"orphan"
            source, candidate = _ready_candidate(controller, "orphan.xlsx", payload)
            digest = hashlib.sha256(payload).hexdigest()
            processing = controller.claim(candidate, digest)
            controller.mark_queued(digest, processing, source.name)

            restarted = AutoInboxController(
                root,
                minimum_age_seconds=0,
                stable_scans_required=2,
            )
            recovered = tuple(restarted.incoming_dir.glob("recovered__*"))
            self.assertEqual(len(recovered), 1)
            self.assertEqual(recovered[0].read_bytes(), payload)
            self.assertFalse(restarted.already_handled(digest))
            state = json.loads(restarted.state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["records"][digest]["status"], "RECOVERED")
            now = recovered[0].stat().st_mtime_ns + 1
            restarted.scan(now_ns=now)
            self.assertEqual(len(restarted.scan(now_ns=now)), 1)

    def test_rejected_outcome_is_preserved_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            controller = AutoInboxController(
                Path(raw) / "auto-inbox",
                minimum_age_seconds=0,
                stable_scans_required=2,
            )
            payload = b"bad-report"
            source, candidate = _ready_candidate(controller, "bad.xlsx", payload)
            digest = hashlib.sha256(payload).hexdigest()
            processing = controller.claim(candidate, digest)
            final = controller.finalize(
                processing,
                digest,
                success=False,
                reason="QUARANTINED_SECURITY",
                source_name=source.name,
            )
            self.assertEqual(final.parent, controller.rejected_dir)
            self.assertEqual(final.read_bytes(), payload)
            self.assertFalse(controller.already_handled(digest))

    def test_state_tamper_is_rejected_fail_closed(self) -> None:
        cases = (
            {"schema_version": "wrong", "records": {}, "events": [], "marketplace_write_enabled": False, "release_scope": "WB_ONLY"},
            {"schema_version": "quantum-auto-inbox-v1", "records": {}, "events": [], "marketplace_write_enabled": True, "release_scope": "WB_ONLY"},
            {"schema_version": "quantum-auto-inbox-v1", "records": {}, "events": [], "marketplace_write_enabled": False, "release_scope": "OZON"},
        )
        for payload in cases:
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as raw:
                root = Path(raw) / "auto-inbox"
                root.mkdir(parents=True)
                (root / "state.json").write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaises(AutoInboxError):
                    AutoInboxController(root)

    def test_internal_path_resolution_rejects_absolute_and_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            controller = AutoInboxController(Path(raw) / "auto-inbox")
            for value in (str(Path(raw).resolve()), "../outside.xlsx"):
                with self.subTest(value=value), self.assertRaises(AutoInboxError):
                    controller.resolve_internal(value)

    def test_symlink_is_never_returned_as_ready(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            controller = AutoInboxController(root / "auto-inbox")
            outside = root / "outside.xlsx"
            outside.write_bytes(b"outside")
            link = controller.incoming_dir / "link.xlsx"
            try:
                link.symlink_to(outside)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            self.assertEqual(controller.scan(now_ns=time.time_ns() + 10**10), ())
            self.assertFalse(link.exists())
            self.assertTrue(any(controller.review_dir.iterdir()))


class AutoInboxIntegrationContractTests(unittest.TestCase):
    def read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_existing_sequential_queue_and_review_are_reused(self) -> None:
        text = self.read("src/quantum/application/_finance_center_auto_inbox.py")
        self.assertIn("self._confirm_authority", text)
        self.assertIn("self._review_source", text)
        self.assertIn("self.import_queue.add", text)
        self.assertIn("self._start_next_if_idle", text)
        self.assertNotIn("run_import(", text)

    def test_desktop_starts_auto_inbox_without_new_navigation(self) -> None:
        shell = self.read("src/quantum/application/_finance_center_shell.py")
        center = self.read("src/quantum/application/finance_center.py")
        shared = self.read("src/quantum/application/_finance_center_shared.py")
        self.assertIn("self._initialize_auto_inbox()", shell)
        self.assertIn("self._schedule_auto_inbox_poll()", shell)
        self.assertIn("FinanceCenterAutoInboxMixin", center)
        self.assertEqual(shared.count('(\"settings\", \"Настройки\")'), 1)

    def test_queue_worker_preserves_and_closes_auto_inbox_transaction(self) -> None:
        text = self.read("src/quantum/application/_finance_center_queue_runtime.py")
        self.assertIn('key == "auto_inbox" or key.startswith("auto_inbox_")', text)
        self.assertIn('getattr(self, "_finalize_auto_inbox_row", None)', text)
        self.assertIn("finalizer(row)", text)
        auto = self.read("src/quantum/application/_finance_center_auto_inbox.py")
        self.assertIn('"auto_inbox_transaction_open": True', auto)
        self.assertIn('row.details["auto_inbox_transaction_open"] = False', auto)

    def test_cancelled_pending_auto_inbox_is_finalized(self) -> None:
        text = self.read("src/quantum/application/_finance_center_queue_runtime.py")
        cancel = text[text.index("def cancel_queue"):text.index("def request_close")]
        self.assertIn("_finalize_auto_inbox_row", cancel)

    def test_row_metadata_uses_relative_internal_paths_only(self) -> None:
        text = self.read("src/quantum/application/_finance_center_auto_inbox.py")
        self.assertIn("self.auto_inbox.relative_internal(processing_path)", text)
        self.assertIn("self.auto_inbox.resolve_internal(", text)
        self.assertNotIn('"auto_inbox_processing_path": str(processing_path)', text)
        self.assertNotIn('row.details["auto_inbox_final_path"] = str(final_path)', text)

    def test_ui_reports_dedicated_incoming_path_without_redesign(self) -> None:
        text = self.read("src/quantum/application/_finance_center_pages.py")
        self.assertIn('"auto-inbox" / "incoming"', text)
        self.assertIn("Автовходящие:", text)
        self.assertNotIn(
            "AUTO_INBOX",
            self.read("src/quantum/application/_finance_center_shared.py"),
        )

    def test_fail_closed_state_does_not_crash_main_desktop(self) -> None:
        auto = self.read("src/quantum/application/_finance_center_auto_inbox.py")
        shell = self.read("src/quantum/application/_finance_center_shell.py")
        self.assertIn("except AutoInboxError as exc:", auto)
        self.assertIn("self.auto_inbox_error = exc.code", auto)
        self.assertIn("Автовходящие отключены fail-closed", shell)


if __name__ == "__main__":
    unittest.main()
