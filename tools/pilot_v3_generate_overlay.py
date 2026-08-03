from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from tools import m9_maximum_assurance_control_plane as m9

POST_PILOT_TERMS = (
    "ozon", "manager-specialist", "manager–specialist", "multi-agent", "многоагент",
    "sbom", "license", "лиценз", "reproducible", "authenticode",
    "production distribution", "full dpi", "полный dpi", "endurance",
)
REQUIRED_TERMS = (
    "wildberries", "wb_only", "wb only", "xls", "xlsx", "csv",
    "себестоим", "налог", "расход", "прибыл", "возврат", "calculation_blocked",
    "excel export", "экспорт", "центр решений", "аналитик", "рекомендац",
    "installer", "установ", "ярлык", "shortcut", "lnk", "desktopdirectory",
    "repair", "повторный запуск", "second launch", "unique output",
    "marketplace writes", "marketplace_write", "path traversal",
    "formula injection", "macro", "command injection", "powershell injection",
    "l3", "l4", "l5", "run a", "run b", "same artifact",
    "exact head", "work order", "signed work order", "exclusive lock",
    "literal rtm", "manifest", "source regression",
)
P0_TERMS = (
    "marketplace writes", "path traversal", "formula injection", "macro",
    "command injection", "powershell injection", "installer", "ярлык",
    "shortcut", "lnk", "l4", "l5", "same artifact", "run a", "run b",
    "work order", "exclusive lock", "literal rtm", "manifest",
)

def _classify(row: dict[str, Any]) -> tuple[str, str, str]:
    text = " ".join(
        str(row.get(key, ""))
        for key in ("original_text", "source_location", "implementation_action", "milestone")
    ).lower()
    if any(term in text for term in POST_PILOT_TERMS):
        return "POST_PILOT", "P3", "Deferred by the bounded WB pilot prompt; production status is unchanged."
    if any(term in text for term in REQUIRED_TERMS):
        priority = "P0" if any(term in text for term in P0_TERMS) else "P1"
        return "REQUIRED", priority, "Directly affects WB pilot correctness, safety, installation, provenance or the physical user path."
    return "APPLICABLE_REGRESSION", "P2", "Must remain green as a source/product regression on the canonical pilot head."

def generate(repo_root: Path) -> dict[str, Any]:
    ingestion = m9.ingest_literal_rtm(repo_root)
    if ingestion.get("status") != "PASS":
        raise SystemExit("CANONICAL_RTM_INGESTION_FAILED:" + ",".join(ingestion.get("findings", [])))
    rows = ingestion["_rows"]
    entries = []
    for row in rows:
        applicability, priority, justification = _classify(row)
        entries.append(
            {
                "requirement_id": row["requirement_id"],
                "pilot_applicability": applicability,
                "pilot_priority": priority,
                "pilot_dependency": list(row.get("dependencies", [])),
                "pilot_action": row.get("implementation_action") or "Preserve and verify the canonical requirement in the bounded pilot.",
                "pilot_test": sorted(set(row.get("positive_test_ids", []) + row.get("negative_control_ids", []) + row.get("mutation_ids", []))),
                "pilot_target_evidence_level": row.get("target_evidence_level", "L0"),
                "pilot_evidence_ids": [],
                "pilot_status": "NOT_STARTED",
                "justification": justification,
                "production_status_unchanged": True,
            }
        )
    ids = [item["requirement_id"] for item in entries]
    if len(entries) != 712 or len(set(ids)) != 712:
        raise SystemExit(f"PILOT_OVERLAY_CARDINALITY_INVALID:{len(entries)}:{len(set(ids))}")
    counts: dict[str, int] = {}
    for item in entries:
        counts[item["pilot_applicability"]] = counts.get(item["pilot_applicability"], 0) + 1
    return {
        "artifact_type": "PILOT_APPLICABILITY_OVERLAY",
        "schema_version": "3.0.0",
        "protocol_sha256": m9.EXPECTED_PROTOCOL_SHA256,
        "canonical_registry_set_sha256": m9.EXPECTED_REGISTRY_SET_SHA256,
        "canonical_requirement_count": 712,
        "entries": entries,
        "pilot_applicability_counts": counts,
        "production_status_unchanged": True,
        "pilot_decision": "PILOT_BLOCKED",
        "production_release_decision": "RELEASE_BLOCKED",
        "release_authorized": False,
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = generate(Path(args.repo_root).resolve())
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "requirement_count": len(result["entries"]), "counts": result["pilot_applicability_counts"]}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
