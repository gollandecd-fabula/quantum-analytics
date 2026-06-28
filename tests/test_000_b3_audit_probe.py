import hashlib
import io
import json
import subprocess
import unittest
from pathlib import Path

from test_b1a_artifact_manifest import load_effective_manifest

ROOT = Path(__file__).resolve().parents[1]
SELF = "tests/test_000_b3_audit_probe.py"
CONTROL = {
    "docs/evidence/ARTIFACT_MANIFEST.json",
    "docs/evidence/ARTIFACT_MANIFEST_OVERLAY.json",
    SELF,
}


class B3AuditProbe(unittest.TestCase):
    def test_emit_b3_and_manifest_diagnostics(self):
        suite = unittest.defaultTestLoader.loadTestsFromName("test_b3_metric_evidence")
        result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
        print(
            f"B3_PROBE_RESULT tests={result.testsRun} failures={len(result.failures)} errors={len(result.errors)}",
            flush=True,
        )
        for test, detail in result.failures:
            print(f"B3_PROBE_FAILURE test={test.id()} detail={detail.splitlines()[-1]}", flush=True)
        for test, detail in result.errors:
            print(f"B3_PROBE_ERROR test={test.id()} detail={detail.splitlines()[-1]}", flush=True)

        effective = load_effective_manifest()
        recorded = {row[0]: (row[1], row[2]) for row in effective["artifacts"]}
        output = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode("utf-8")
        paths = sorted(path for path in output.split("\0") if path and path not in CONTROL)
        expected = {}
        for path in paths:
            data = (ROOT / path).read_bytes()
            expected[path] = (hashlib.sha256(data).hexdigest(), len(data))

        print(f"B3_MANIFEST_COUNTS recorded={len(recorded)} expected={len(expected)}", flush=True)
        for path in sorted(set(expected) - set(recorded)):
            sha, size = expected[path]
            print(f"B3_MANIFEST_MISSING path={path} sha256={sha} size={size}", flush=True)
        for path in sorted(set(recorded) - set(expected)):
            sha, size = recorded[path]
            print(f"B3_MANIFEST_EXTRA path={path} sha256={sha} size={size}", flush=True)
        for path in sorted(set(expected) & set(recorded)):
            if expected[path] != recorded[path]:
                old_sha, old_size = recorded[path]
                new_sha, new_size = expected[path]
                print(
                    f"B3_MANIFEST_MISMATCH path={path} recorded_sha256={old_sha} recorded_size={old_size} "
                    f"expected_sha256={new_sha} expected_size={new_size}",
                    flush=True,
                )
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
