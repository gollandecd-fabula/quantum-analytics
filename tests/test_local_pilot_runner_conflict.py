from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from quantum.pilot._scope import LocalPilotExecutionError
from quantum.pilot.runner import run_manifest
from tests.local_pilot_runner_fixtures import RUN_ID, TENANT_ID, manifest, write_case


class LocalPilotRunnerConflictTests(unittest.TestCase):
    def test_material_difference_writes_safe_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = root / "case"
            workspace = root / "workspace"
            case.mkdir()
            manifest_path, _ = write_case(
                case,
                document=manifest(source_profit="3979.98"),
            )
            with self.assertRaisesRegex(
                LocalPilotExecutionError,
                "PILOT_RECONCILIATION_CONFLICT",
            ):
                run_manifest(manifest_path, workspace_base=workspace)
            tenant_hash = hashlib.sha256(TENANT_ID.encode("utf-8")).hexdigest()
            failure_path = (
                workspace
                / "runs"
                / tenant_hash
                / RUN_ID
                / "evidence"
                / "failure.json"
            )
            failure = json.loads(failure_path.read_text(encoding="utf-8"))
            self.assertEqual(
                failure,
                {
                    "schema_version": "quantum-local-pilot-failure-v1",
                    "error_code": "PILOT_RECONCILIATION_CONFLICT",
                    "release_state": "RELEASE_BLOCKED",
                },
            )


if __name__ == "__main__":
    unittest.main()
