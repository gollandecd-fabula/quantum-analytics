from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise SystemExit(f"M3_JSON_OBJECT_REQUIRED:{path}")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slot-a", type=Path, required=True)
    parser.add_argument("--slot-b", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-package-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    slots: dict[str, dict[str, Any]] = {}
    installed_hashes: list[str] = []
    for label, root in (("A", args.slot_a), ("B", args.slot_b)):
        evidence_path = root / "L4_INSTALLED_RUNTIME_EVIDENCE.json"
        postcheck_path = root / "L4_INDEPENDENT_POSTCHECK_EVIDENCE.json"
        installed_path = root / "INSTALLED_MANIFEST.json"
        evidence = _load(evidence_path)
        postcheck = _load(postcheck_path)
        installed = _load(installed_path)
        if evidence.get("status") != "L4_INSTALLED_RUNTIME_PASS":
            raise SystemExit(f"M3_L4_STATUS:{label}")
        if postcheck.get("status") != "L4_INDEPENDENT_POSTCHECK_PASS":
            raise SystemExit(f"M3_POSTCHECK_STATUS:{label}")
        if evidence.get("exact_head") != args.expected_head:
            raise SystemExit(f"M3_HEAD_MISMATCH:{label}")
        if evidence.get("validation_slot") != label:
            raise SystemExit(f"M3_SLOT_MISMATCH:{label}")
        source = evidence.get("source_package") or {}
        if source.get("origin") != "PREBUILT_SAME_ARTIFACT":
            raise SystemExit(f"M3_NOT_PREBUILT:{label}")
        if source.get("sha256") != args.expected_package_sha256:
            raise SystemExit(f"M3_PACKAGE_HASH:{label}")
        if evidence.get("marketplace_write_enabled") is not False:
            raise SystemExit(f"M3_WRITES_ENABLED:{label}")
        if evidence.get("physical_user_path_verified") is not False:
            raise SystemExit(f"M3_FALSE_L5:{label}")
        if installed.get("exact_head") != args.expected_head:
            raise SystemExit(f"M3_INSTALLED_HEAD:{label}")
        if installed.get("source_package_sha256") != args.expected_package_sha256:
            raise SystemExit(f"M3_INSTALLED_PACKAGE_HASH:{label}")
        if installed.get("marketplace_write_enabled") is not False:
            raise SystemExit(f"M3_INSTALLED_WRITES:{label}")
        installed_sha = _sha256(installed_path)
        installed_hashes.append(installed_sha)
        slots[label] = {
            "evidence_sha256": _sha256(evidence_path),
            "postcheck_sha256": _sha256(postcheck_path),
            "installed_manifest_sha256": installed_sha,
            "managed_file_count": len(installed.get("managed_files") or []),
        }

    if installed_hashes[0] != installed_hashes[1]:
        raise SystemExit("M3_AB_INSTALLED_MANIFEST_MISMATCH")

    result = {
        "milestone": "M3_CI_CONSOLIDATION",
        "status": "PASS",
        "exact_head": args.expected_head,
        "build_count": 1,
        "validator_count": 2,
        "same_artifact_sha256": args.expected_package_sha256,
        "installed_manifest_identical": True,
        "slots": slots,
        "marketplace_write_enabled": False,
        "release_scope": "WB_ONLY",
        "release_state": "RELEASE_BLOCKED",
        "physical_user_path_verified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("M3_SAME_ARTIFACT_COMPARE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
