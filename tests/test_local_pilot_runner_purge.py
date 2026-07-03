from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from quantum.pilot.purge import purge_workspace
from quantum.pilot.runner import run_manifest
from tests.local_pilot_runner_fixtures import RUN_ID, TENANT_ID, write_case


class LocalPilotRunnerPurgeTests(unittest.TestCase):
    def test_purge_removes_run_root_and_preserves_external_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = root / "case"
            workspace = root / "workspace"
            case.mkdir()
            manifest_path, _ = write_case(case)
            run_manifest(manifest_path, workspace_base=workspace)
            source = case / "sample.zip"
            tenant_hash = hashlib.sha256(TENANT_ID.encode("utf-8")).hexdigest()
            execution_root = workspace / "runs" / tenant_hash / RUN_ID

            receipt = purge_workspace(
                workspace_base=workspace,
                tenant_id=TENANT_ID,
                run_id=RUN_ID,
                purged_at="2026-07-02T00:02:00Z",
            )

            self.assertFalse(execution_root.exists())
            self.assertTrue(source.is_file())
            self.assertTrue(Path(receipt["receipt_path"]).is_file())
            self.assertGreater(receipt["deleted_file_count"], 0)
            self.assertGreater(receipt["deleted_byte_count"], 0)
            self.assertFalse(receipt["source_file_outside_workspace_deleted"])
            self.assertEqual(receipt["release_state"], "RELEASE_BLOCKED")


if __name__ == "__main__":
    unittest.main()
