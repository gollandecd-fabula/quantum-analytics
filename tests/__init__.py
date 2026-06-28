from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from pathlib import Path

__all__ = ["__version__"]
__version__ = "0.0.1"


def _manifest_diagnostic() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest_path = root / "docs/evidence/ARTIFACT_MANIFEST.json"
    overlay_path = root / "docs/evidence/ARTIFACT_MANIFEST_OVERLAY.json"
    runtime_path = root / "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_B3_RUNTIME.json"
    controls = {
        "docs/evidence/ARTIFACT_MANIFEST.json",
        "docs/evidence/ARTIFACT_MANIFEST_OVERLAY.json",
        "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_B3_RUNTIME.json",
    }
    try:
        current = json.loads(manifest_path.read_text(encoding="utf-8"))
        overlays = [
            json.loads(overlay_path.read_text(encoding="utf-8")),
            json.loads(runtime_path.read_text(encoding="utf-8")),
        ]
        rows = {row[0]: row for row in current["artifacts"]}
        for overlay in overlays:
            encoding = overlay.get("hash_encoding", "sha256-hex")
            for path, digest, size in overlay["entries"]:
                if encoding == "sha256-base64":
                    digest = base64.b64decode(digest, validate=True).hex()
                rows[path] = [path, digest, size]
            for path in overlay.get("remove_paths", []):
                rows.pop(path, None)
        listed = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode("utf-8")
        expected = {}
        for path in sorted(item for item in listed.split("\0") if item and item not in controls):
            data = (root / path).read_bytes()
            expected[path] = [path, hashlib.sha256(data).hexdigest(), len(data)]
        shared = sorted(rows.keys() & expected.keys())
        diff = {
            "missing": sorted(expected.keys() - rows.keys()),
            "extra": sorted(rows.keys() - expected.keys()),
            "mismatched": [
                {"path": path, "manifest": rows[path], "tracked": expected[path]}
                for path in shared if rows[path] != expected[path]
            ],
        }
        print("MANIFEST_DIFF=" + json.dumps(diff, sort_keys=True), flush=True)
    except Exception as exc:
        print("MANIFEST_DIAGNOSTIC_ERROR=" + repr(exc), flush=True)


_manifest_diagnostic()
