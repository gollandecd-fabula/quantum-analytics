#!/usr/bin/env python3
"""CI wrapper for the SHA-locked CP034 ExecuTorch mmap patch.

The actual patch implementation is frozen at commit c44d1516 and verified by
its Git blob SHA before execution. CI additionally stages a Python export
overlay as an independent best-effort artifact; overlay failure cannot mask or
block the native AAR build path.
"""
from __future__ import annotations
import os
import pathlib
import subprocess
import sys
import tempfile
import urllib.request

PINNED_IMPL_URL = "https://raw.githubusercontent.com/gollandecd-fabula/quantum-analytics/c44d151694efd00dc2656cbb6f38f8699a12e356/sindel_cp034/patch_executorch_asset_mmap.py"
PINNED_IMPL_GIT_BLOB = "1985bbcf3ac8aae7d18013b9b0d3e581e5942aec"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="cp034_mmap_impl_") as td:
        impl = pathlib.Path(td) / "patch_impl.py"
        with urllib.request.urlopen(PINNED_IMPL_URL, timeout=60) as r:
            impl.write_bytes(r.read())
        got = subprocess.check_output(["git", "hash-object", str(impl)], text=True).strip()
        if got != PINNED_IMPL_GIT_BLOB:
            raise SystemExit(f"FAIL-CLOSED: pinned mmap implementation drift {got}")
        rc = subprocess.call([sys.executable, str(impl), *sys.argv[1:]])
        if rc != 0:
            return int(rc)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        helper = pathlib.Path(__file__).with_name("ci_stage_executorch_python_overlay.py")
        try:
            subprocess.check_call([sys.executable, str(helper)])
        except Exception as e:
            print(f"CP034_PY_OVERLAY_STAGE_FAILED_NONBLOCKING: {e}", file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
