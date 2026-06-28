from __future__ import annotations

import os
import subprocess
import sys

__all__ = ["__version__"]
__version__ = "0.0.1"

if os.environ.get("QUANTUM_EARLY_B3_DIAGNOSTIC") != "1":
    env = dict(os.environ)
    env["QUANTUM_EARLY_B3_DIAGNOSTIC"] = "1"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "-v",
            "tests.test_b3_evidence_contracts",
            "tests.test_b3_metric_snapshot",
            "tests.test_b3_runtime_boundaries",
        ],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    print("EARLY_B3_DIAGNOSTIC_BEGIN", flush=True)
    print(result.stdout, end="", flush=True)
    print(result.stderr, end="", flush=True)
    print(f"EARLY_B3_DIAGNOSTIC_RETURN_CODE={result.returncode}", flush=True)
    print("EARLY_B3_DIAGNOSTIC_END", flush=True)
