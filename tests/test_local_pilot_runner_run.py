from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from quantum.pilot.runner import run_manifest
from tests.local_pilot_runner_fixtures import RUN_ID, TENANT_ID, write_case


def run_root(workspace: Path) -> Path:
    tenant_hash = hashlib.sha256(TENANT_ID.encode("utf-8")).hexdigest()
    return workspace / "runs" / tenant_hash / RUN_ID


class LocalPilotRunnerRunTests(unittest.TestCase):
    def test_full_run_creates_zones_and_redacted_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = root / "case"
            workspace = root / "workspace"
            case.mkdir()
            manifest_path, payload = write_case(case)
            result = run_manifest(manifest_path, workspace_base=workspace)
            execution_root = run_root(workspace)
            evidence_text = Path(result["evidence_path"]).read_text(encoding="utf-8")
            evidence = json.loads(evidence_text)

            self.assertEqual(result["status"], "RECONCILED")
            self.assertEqual(result["release_state"], "RELEASE_BLOCKED")
            for zone in ("raw", "quarantine", "admitted", "derived", "evidence"):
                self.assertTrue((execution_root / zone).is_dir())
            digest = hashlib.sha256(payload).hexdigest()
            for zone in ("raw", "quarantine", "admitted"):
                self.assertEqual((execution_root / zone / digest).read_bytes(), payload)
            self.assertNotIn(payload.hex(), evidence_text)
            self.assertNotIn("3980.00", evidence_text)
            self.assertEqual(evidence["pilot_state"], "LOCAL_EXECUTION_RECONCILED")
            self.assertEqual(
                evidence["finance"]["synthetic"]["metric_states"]["net_profit_amount"],
                "VALID",
            )


if __name__ == "__main__":
    unittest.main()
