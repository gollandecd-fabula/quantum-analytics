import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATHS = (
    "pyproject.toml",
    "src/quantum/pilot/__init__.py",
    "src/quantum/pilot/local_runner.py",
    "tests/test_local_pilot_runner.py",
    "docs/pilot/LOCAL_PILOT_RUNNER_R1.md",
)


class LocalPilotManifestProbe(unittest.TestCase):
    def test_emit_final_artifact_hashes(self):
        values = {}
        for path in PATHS:
            data = (ROOT / path).read_bytes()
            values[path] = {
                "sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
            }
        self.fail("LOCAL_PILOT_MANIFEST_PROBE=" + json.dumps(values, sort_keys=True))
