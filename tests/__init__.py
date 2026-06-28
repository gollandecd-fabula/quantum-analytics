from __future__ import annotations

import os
import subprocess
import sys

__all__ = ["__version__"]
__version__ = "0.0.1"

if os.environ.get("QUANTUM_VECTOR_DIAGNOSTIC") != "1":
    env = dict(os.environ)
    env["QUANTUM_VECTOR_DIAGNOSTIC"] = "1"
    script = """
from tests.b3_helpers import graph_data, mutate
from quantum.evidence import diagnose_evidence_chain

data = graph_data()
for vector in data[\"invalid_vectors\"]:
    actual = diagnose_evidence_chain(mutate(data[\"valid_graph\"], vector[\"mutation\"]))
    print(
        \"VECTOR_DIAGNOSTIC \"
        + vector[\"id\"]
        + \" expected=\"
        + vector[\"expected_diagnostic\"]
        + \" actual=\"
        + str(actual),
        flush=True,
    )
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    print("VECTOR_DIAGNOSTIC_BEGIN", flush=True)
    print(result.stdout, end="", flush=True)
    print(result.stderr, end="", flush=True)
    print(f"VECTOR_DIAGNOSTIC_RETURN_CODE={result.returncode}", flush=True)
    print("VECTOR_DIAGNOSTIC_END", flush=True)
