from __future__ import annotations
import base64, hashlib, json, subprocess
from pathlib import Path
from tests._artifact_manifest_chain_v3 import CORRECTION_NAME, OVERLAY_NAMES

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence"
MANIFEST_PATH = EVIDENCE / "ARTIFACT_MANIFEST.json"
ALL_OVERLAY_NAMES = (*OVERLAY_NAMES, CORRECTION_NAME)
CONTROL_PATHS = {"docs/evidence/ARTIFACT_MANIFEST.json", *(f"docs/evidence/{name}" for name in ALL_OVERLAY_NAMES)}
ARTIFACT_FIELDS = ["path", "sha256", "size_bytes"]
B1A_SCHEMAS = {
    "schemas/calculation-profile.schema.json",
    "schemas/configuration-rule.schema.json",
    "schemas/metric-definition.schema.json",
    "schemas/rounding-policy.schema.json",
    "schemas/rule-resolution-result.schema.json",
    "schemas/safe-expression.schema.json",
}

def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()

def tracked_paths() -> list[str]:
    output = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode()
    return sorted(path for path in output.split("\0") if path and path not in CONTROL_PATHS)

def apply_entries(artifacts: dict[str, list], overlay: dict) -> None:
    encoding = overlay.get("hash_encoding", "sha256-hex")
    for path, digest, size in overlay["entries"]:
        if encoding == "sha256-base64":
            digest = base64.b64decode(digest, validate=True).hex()
        elif encoding != "sha256-hex":
            raise AssertionError("ARTIFACT_MANIFEST_HASH_ENCODING_UNSUPPORTED")
        artifacts[path] = [path, digest, size]
    for path in overlay.get("remove_paths", []):
        artifacts.pop(path, None)

def _overlay_paths() -> list[Path]:
    names = list(OVERLAY_NAMES)
    if (EVIDENCE / CORRECTION_NAME).exists():
        names.append(CORRECTION_NAME)
    return [EVIDENCE / name for name in names]

def load_effective_manifest() -> dict:
    previous = MANIFEST_PATH.read_bytes()
    current = json.loads(previous)
    artifacts = {row[0]: row for row in current["artifacts"]}
    for path in _overlay_paths():
        raw = path.read_bytes()
        overlay = json.loads(raw)
        keys = [key for key in overlay if key.startswith("base_") and key.endswith("_git_blob_sha")]
        if len(keys) != 1 or overlay[keys[0]] != git_blob_sha(previous):
            raise AssertionError(f"ARTIFACT_MANIFEST_OVERLAY_BASE_MISMATCH:{path.name}")
        apply_entries(artifacts, overlay)
        previous = raw
    result = dict(current)
    result["artifacts"] = [artifacts[path] for path in sorted(artifacts)]
    result["artifact_count"] = len(result["artifacts"])
    return result

def expected_manifest(current: dict) -> dict:
    artifacts = []
    for path in tracked_paths():
        data = (ROOT / path).read_bytes()
        artifacts.append([path, hashlib.sha256(data).hexdigest(), len(data)])
    return {
        "project": current["project"],
        "generated_on": "2026-06-27",
        "package_version": "6",
        "source_constitution_file": current["source_constitution_file"],
        "source_constitution_sha256": current["source_constitution_sha256"],
        "artifact_count": len(artifacts),
        "artifact_fields": ARTIFACT_FIELDS,
        "artifacts": artifacts,
    }
