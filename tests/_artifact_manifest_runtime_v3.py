from __future__ import annotations
import base64, hashlib, json, subprocess
from pathlib import Path
from tests._artifact_manifest_chain_v3 import OVERLAY_NAMES

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence"
MANIFEST_PATH = EVIDENCE / "ARTIFACT_MANIFEST.json"
CORRECTION_PATH = EVIDENCE / "B1B_RESCUE_MANIFEST_CORRECTION_V1.txt"
OVERLAY_PATHS = tuple(EVIDENCE / name for name in OVERLAY_NAMES)
CONTROL_PATHS = {
    "docs/evidence/ARTIFACT_MANIFEST.json",
    *(f"docs/evidence/{name}" for name in OVERLAY_NAMES),
    str(CORRECTION_PATH.relative_to(ROOT)).replace("\\", "/"),
}
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

def apply_correction(artifacts: dict[str, list], previous: bytes) -> None:
    if not CORRECTION_PATH.exists():
        return
    lines = CORRECTION_PATH.read_text(encoding="utf-8").splitlines()
    prefix = "base_b1b_rescue_overlay_git_blob_sha="
    if not lines or not lines[0].startswith(prefix):
        raise AssertionError("B1B_RESCUE_MANIFEST_CORRECTION_HEADER_INVALID")
    if lines[0][len(prefix):] != git_blob_sha(previous):
        raise AssertionError("B1B_RESCUE_MANIFEST_CORRECTION_BASE_MISMATCH")
    for line in lines[1:]:
        path, digest, size = line.split("|", 2)
        if len(digest) != 64:
            raise AssertionError("B1B_RESCUE_MANIFEST_CORRECTION_DIGEST_INVALID")
        artifacts[path] = [path, digest, int(size)]

def load_effective_manifest() -> dict:
    previous = MANIFEST_PATH.read_bytes()
    current = json.loads(previous)
    artifacts = {row[0]: row for row in current["artifacts"]}
    for path in OVERLAY_PATHS:
        raw = path.read_bytes()
        overlay = json.loads(raw)
        keys = [key for key in overlay if key.startswith("base_") and key.endswith("_git_blob_sha")]
        if len(keys) != 1 or overlay[keys[0]] != git_blob_sha(previous):
            raise AssertionError(f"ARTIFACT_MANIFEST_OVERLAY_BASE_MISMATCH:{path.name}")
        apply_entries(artifacts, overlay)
        previous = raw
    apply_correction(artifacts, previous)
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
