from __future__ import annotations

import json

from tests.test_b1a_artifact_manifest import (
    expected_manifest,
    load_effective_manifest,
)


_DIAGNOSTIC_ONLY_PATHS = {
    "src/quantum/scripts/ci.py",
    "docs/evidence/DIAGNOSTIC_P16_R5_FUNCTIONAL_ONLY.md",
    "docs/evidence/DIAGNOSTIC_P16_R5_PR_TRIGGER.md",
}


def without_diagnostic_paths(manifest: dict) -> dict:
    result = dict(manifest)
    result["artifacts"] = [
        row for row in manifest["artifacts"] if row[0] not in _DIAGNOSTIC_ONLY_PATHS
    ]
    result["artifact_count"] = len(result["artifacts"])
    return result


def manifest_diff(current: dict, expected: dict) -> dict:
    current_rows = {row[0]: row for row in current["artifacts"]}
    expected_rows = {row[0]: row for row in expected["artifacts"]}
    return {
        "missing": sorted(set(expected_rows) - set(current_rows)),
        "extra": sorted(set(current_rows) - set(expected_rows)),
        "mismatched": [
            {
                "path": path,
                "manifest": current_rows[path],
                "tracked": expected_rows[path],
            }
            for path in sorted(set(current_rows) & set(expected_rows))
            if current_rows[path] != expected_rows[path]
        ],
        "top_level": {
            key: {"manifest": current.get(key), "tracked": expected.get(key)}
            for key in sorted(set(current) | set(expected))
            if key != "artifacts" and current.get(key) != expected.get(key)
        },
    }


def main() -> None:
    current = without_diagnostic_paths(load_effective_manifest())
    expected = without_diagnostic_paths(expected_manifest(current))
    diff = manifest_diff(current, expected)
    print("MANIFEST_ONLY_DIFF=" + json.dumps(diff, sort_keys=True))
    raise SystemExit(1 if any((
        diff["missing"],
        diff["extra"],
        diff["mismatched"],
        diff["top_level"],
    )) else 0)


if __name__ == "__main__":
    main()
