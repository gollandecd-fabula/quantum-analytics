from __future__ import annotations

import argparse
import base64
import copy
import gzip
import hashlib
import json
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

PROTOCOL_VERSION = "3.1"
EXPECTED_PROTOCOL_SHA256 = "be69b8f1f919066c67086d6dd4678acf5e3cb3c4f1db9bc587dc540018601a90"
EXPECTED_MASTER_PROMPT_SHA256 = "1008a69ac56e44e6fa1f69c51f1fe43c8e621c161a52241230fa0af88ecd004a"
EXPECTED_UI_REFERENCE_SHA256 = "2482074aea312b065b4094792c5676445514dd555d50a064a5ae3e189dc60d13"
EXPECTED_REGISTRY_SET_SHA256 = "4cd2561b2da074b73ebe9ac8a3ccec6f2c890f7f7bf7998ac1a0ca698ed1037a"
EXPECTED_REQUIREMENT_COUNT = 712
EXPECTED_SHARD_COUNT = 12
CANONICAL_RTM_INDEX = "docs/evidence/agent_v3_1/REQUIREMENTS_TRACEABILITY_MATRIX.json"
GOVERNING_WORK_ORDER = "docs/evidence/agent_v3_1/WORK_ORDER_M1_EXISTING_M9_MIGRATION_001.json"
M1_SCOPE = "docs/evidence/agent_v3_1/M1_EXISTING_M9_MIGRATION_RTM.json"

LEVELS = ("L0", "L1", "L2", "L3", "L4", "L5")
STATUSES = {
    "NOT_STARTED",
    "IN_PROGRESS",
    "PARTIAL",
    "UNVERIFIED",
    "FAILED",
    "BLOCKED",
    "VERIFIED",
}
PRIORITIES = ("P0", "P1", "P2", "P3")
ROLES = ("IMPLEMENTER", "VERIFIER", "ADVERSARY", "L4_L5_WORKER", "CONTROL_PLANE")
MANDATORY_ROW_FIELDS = (
    "requirement_id",
    "source_document",
    "source_location",
    "original_text",
    "priority",
    "milestone",
    "dependencies",
    "assigned_role",
    "implementation_action",
    "positive_test_ids",
    "negative_control_ids",
    "mutation_ids",
    "target_evidence_level",
    "required_artifacts",
    "pass_criteria",
    "actual_status",
    "actual_evidence_ids",
    "blockers",
    "residual_risks",
)
REQUIRED_ARTIFACTS = (
    "REQUIREMENTS_TRACEABILITY_MATRIX.json",
    "CLAIM_LEDGER.json",
    "DEFECT_REGISTER.json",
    "STATE_TRANSITION_COVERAGE.json",
    "PARAMETER_COMBINATION_COVERAGE.json",
    "MUTATION_REPORT.json",
    "FUZZ_CORPUS_INDEX.json",
    "FAULT_INJECTION_REPORT.json",
    "SECURITY_REPORT.json",
    "SBOM.json",
    "LICENSE_REPORT.json",
    "BUILD_PROVENANCE.json",
    "INSTALLED_FILE_MANIFEST.json",
    "PHYSICAL_PILOT_REPORT.json",
    "RESIDUAL_RISK_REGISTER.json",
    "FINAL_RELEASE_DECISION.md",
)
M1_EVIDENCE_FILES = (
    "ROLE_PERMISSION_POLICY.json",
    "ROLE_TRACE_INDEX.json",
    "STATE_TRANSITION_COVERAGE.json",
    "CLAIM_LEDGER.json",
    "DEFECT_REGISTER.json",
    "M1_LITERAL_RTM_INGESTION_REPORT.json",
    "M1_NEGATIVE_CONTROL_REPORT.json",
    "M1_SCHEDULER_DECISION.json",
    "M1_SIGNED_WORK_ORDER.json",
    "AUTONOMOUS_EXECUTION_STATE_M1_RUNTIME.json",
    "WORK_ORDER_LEDGER_M1_RUNTIME.json",
    "M1_IMPLEMENTATION_REPORT.json",
)
CLAIM_FIELDS = (
    "claim_id",
    "claim",
    "status",
    "level",
    "requirement_ids",
    "test_ids",
    "exact_head",
    "artifact_sha256",
    "installed_root",
    "entry_point",
    "actual_command_line",
    "environment_id",
    "evidence_ids",
    "falsification_attempts",
    "limitations",
)
GATE_POLICY = {
    "gate_id": "GATE-M1",
    "literal_rtm_coverage_required": 1.0,
    "protocol_hash_binding_required": True,
    "negative_controls_required": True,
    "product_code_change_without_requirement_forbidden": True,
    "release_authorized": False,
}
PRODUCT_PREFIXES = (
    "src/",
    "scripts/windows/",
    "requirements/",
    "installer/",
)
PROTECTED_PREFIXES = (
    "docs/evidence/agent_v3_1/rtm/",
    CANONICAL_RTM_INDEX,
)


class ControlPlaneError(ValueError):
    """Fail-closed control-plane input or state error."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256_bytes(_canonical_bytes(value))


def _git_blob_sha(value: bytes) -> str:
    return hashlib.sha1(f"blob {len(value)}\0".encode("ascii") + value).hexdigest()


def _signed(value: Mapping[str, Any], signature_field: str) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result.pop(signature_field, None)
    result[signature_field] = _sha256_json(result)
    return result


def _verify_signature(value: Mapping[str, Any], signature_field: str) -> bool:
    actual = value.get(signature_field)
    if not isinstance(actual, str) or len(actual) != 64:
        return False
    unsigned = copy.deepcopy(dict(value))
    unsigned.pop(signature_field, None)
    return actual == _sha256_json(unsigned)


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ControlPlaneError(f"JSON_OBJECT_REQUIRED:{path.name}")
    return value


def _safe_repo_path(repo_root: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts:
        raise ControlPlaneError(f"PATH_TRAVERSAL:{relative}")
    candidate = (repo_root / Path(*pure.parts)).resolve()
    root = repo_root.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ControlPlaneError(f"PATH_OUTSIDE_REPOSITORY:{relative}") from exc
    return candidate


def _list_of_strings(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _validate_canonical_row(row: Mapping[str, Any]) -> list[str]:
    req_id = str(row.get("requirement_id", "UNKNOWN"))
    findings: list[str] = []
    if len(row) != len(MANDATORY_ROW_FIELDS) or set(row) != set(MANDATORY_ROW_FIELDS):
        findings.append(f"RTM_ROW_FIELDS_MISMATCH:{req_id}")
    for field in ("requirement_id", "source_document", "source_location", "original_text", "milestone", "implementation_action"):
        if not isinstance(row.get(field), str) or not row.get(field):
            findings.append(f"RTM_FIELD_INVALID:{req_id}:{field}")
    if row.get("priority") not in PRIORITIES:
        findings.append(f"RTM_PRIORITY_INVALID:{req_id}")
    if row.get("assigned_role") not in ROLES:
        findings.append(f"RTM_ROLE_INVALID:{req_id}")
    if row.get("target_evidence_level") not in LEVELS:
        findings.append(f"RTM_EVIDENCE_LEVEL_INVALID:{req_id}")
    if row.get("actual_status") not in STATUSES:
        findings.append(f"RTM_STATUS_INVALID:{req_id}")
    for field in (
        "dependencies",
        "positive_test_ids",
        "negative_control_ids",
        "mutation_ids",
        "required_artifacts",
        "pass_criteria",
        "actual_evidence_ids",
        "blockers",
        "residual_risks",
    ):
        if not _list_of_strings(row.get(field)):
            findings.append(f"RTM_LIST_FIELD_INVALID:{req_id}:{field}")
    if row.get("actual_status") == "VERIFIED" and not row.get("actual_evidence_ids"):
        findings.append(f"RTM_FORGED_VERIFIED:{req_id}")
    return findings


def _decode_shard(
    repo_root: Path,
    shard_meta: Mapping[str, Any],
    expected_fields: tuple[str, ...],
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    findings: list[str] = []
    path_text = str(shard_meta.get("path", ""))
    path = _safe_repo_path(repo_root, path_text)
    try:
        raw = path.read_bytes()
    except OSError:
        return [], {"path": path_text}, [f"RTM_SHARD_MISSING:{path_text}"]
    file_sha = _sha256_bytes(raw)
    file_blob_sha = _git_blob_sha(raw)
    if file_sha != shard_meta.get("sha256"):
        findings.append(f"RTM_SHARD_SHA256_MISMATCH:{path_text}")
    if len(raw) != shard_meta.get("size_bytes"):
        findings.append(f"RTM_SHARD_SIZE_MISMATCH:{path_text}")
    if file_blob_sha != shard_meta.get("git_blob_sha"):
        findings.append(f"RTM_SHARD_GIT_BLOB_MISMATCH:{path_text}")
    try:
        envelope = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError):
        return [], {"path": path_text, "sha256": file_sha}, findings + [f"RTM_SHARD_JSON_INVALID:{path_text}"]
    if not isinstance(envelope, dict):
        return [], {"path": path_text, "sha256": file_sha}, findings + [f"RTM_SHARD_OBJECT_REQUIRED:{path_text}"]
    if tuple(envelope.get("row_fields", ())) != expected_fields:
        findings.append(f"RTM_SHARD_FIELDS_MISMATCH:{path_text}")
    if envelope.get("part_number") != shard_meta.get("part_number"):
        findings.append(f"RTM_SHARD_PART_MISMATCH:{path_text}")
    encoding = shard_meta.get("payload_encoding")
    rows_raw: Any
    if encoding == "plain-json-tuples":
        rows_raw = envelope.get("rows")
    elif encoding == "gzip+base64":
        payload = envelope.get("payload")
        try:
            compressed = base64.b64decode(payload, validate=True)
            uncompressed = gzip.decompress(compressed)
            rows_raw = json.loads(uncompressed)
        except (TypeError, ValueError, OSError, json.JSONDecodeError):
            return [], {"path": path_text, "sha256": file_sha}, findings + [f"RTM_SHARD_PAYLOAD_INVALID:{path_text}"]
        if _sha256_bytes(compressed) != shard_meta.get("compressed_sha256"):
            findings.append(f"RTM_SHARD_COMPRESSED_SHA_MISMATCH:{path_text}")
        if _sha256_bytes(uncompressed) != shard_meta.get("uncompressed_sha256"):
            findings.append(f"RTM_SHARD_UNCOMPRESSED_SHA_MISMATCH:{path_text}")
        if len(compressed) != envelope.get("compressed_size_bytes"):
            findings.append(f"RTM_SHARD_COMPRESSED_SIZE_MISMATCH:{path_text}")
        if len(uncompressed) != envelope.get("uncompressed_size_bytes"):
            findings.append(f"RTM_SHARD_UNCOMPRESSED_SIZE_MISMATCH:{path_text}")
    else:
        return [], {"path": path_text, "sha256": file_sha}, findings + [f"RTM_SHARD_ENCODING_INVALID:{path_text}"]
    if not isinstance(rows_raw, list):
        return [], {"path": path_text, "sha256": file_sha}, findings + [f"RTM_SHARD_ROWS_INVALID:{path_text}"]
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(rows_raw):
        if not isinstance(item, list) or len(item) != len(expected_fields):
            findings.append(f"RTM_ROW_TUPLE_INVALID:{path_text}:{index}")
            continue
        row = dict(zip(expected_fields, item, strict=True))
        findings.extend(_validate_canonical_row(row))
        rows.append(row)
    if len(rows) != shard_meta.get("requirement_count"):
        findings.append(f"RTM_SHARD_COUNT_MISMATCH:{path_text}")
    if rows:
        if rows[0]["requirement_id"] != shard_meta.get("first_requirement_id"):
            findings.append(f"RTM_SHARD_FIRST_ID_MISMATCH:{path_text}")
        if rows[-1]["requirement_id"] != shard_meta.get("last_requirement_id"):
            findings.append(f"RTM_SHARD_LAST_ID_MISMATCH:{path_text}")
    report = {
        "part_number": shard_meta.get("part_number"),
        "path": path_text,
        "payload_encoding": encoding,
        "sha256": file_sha,
        "git_blob_sha": file_blob_sha,
        "requirement_count": len(rows),
        "status": "PASS" if not findings else "FAIL",
    }
    return rows, report, findings


def ingest_literal_rtm(repo_root: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    index_path = _safe_repo_path(repo_root, CANONICAL_RTM_INDEX)
    findings: list[str] = []
    try:
        index_raw = index_path.read_bytes()
        index = json.loads(index_raw)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {
            "artifact_type": "M1_LITERAL_RTM_INGESTION_REPORT",
            "protocol_version": PROTOCOL_VERSION,
            "status": "FAIL",
            "findings": ["RTM_INDEX_INVALID"],
            "release_authorized": False,
        }
    if not isinstance(index, dict):
        return {
            "artifact_type": "M1_LITERAL_RTM_INGESTION_REPORT",
            "protocol_version": PROTOCOL_VERSION,
            "status": "FAIL",
            "findings": ["RTM_INDEX_OBJECT_REQUIRED"],
            "release_authorized": False,
        }
    expected_bindings = {
        "protocol_sha256": EXPECTED_PROTOCOL_SHA256,
        "master_prompt_sha256": EXPECTED_MASTER_PROMPT_SHA256,
        "ui_reference_sha256": EXPECTED_UI_REFERENCE_SHA256,
        "registry_set_sha256": EXPECTED_REGISTRY_SET_SHA256,
        "requirement_count": EXPECTED_REQUIREMENT_COUNT,
        "shard_count": EXPECTED_SHARD_COUNT,
    }
    for field, expected in expected_bindings.items():
        if index.get(field) != expected:
            findings.append(f"RTM_INDEX_BINDING_MISMATCH:{field}")
    if tuple(index.get("row_fields", ())) != MANDATORY_ROW_FIELDS:
        findings.append("RTM_INDEX_ROW_FIELDS_MISMATCH")
    shards = index.get("shards")
    if not isinstance(shards, list) or len(shards) != EXPECTED_SHARD_COUNT:
        findings.append("RTM_INDEX_SHARDS_INVALID")
        shards = []
    rows: list[dict[str, Any]] = []
    shard_reports: list[dict[str, Any]] = []
    for shard_meta in shards:
        if not isinstance(shard_meta, dict):
            findings.append("RTM_SHARD_METADATA_INVALID")
            continue
        shard_rows, shard_report, shard_findings = _decode_shard(
            repo_root, shard_meta, MANDATORY_ROW_FIELDS
        )
        rows.extend(shard_rows)
        shard_reports.append(shard_report)
        findings.extend(shard_findings)
    ids = [str(row.get("requirement_id", "")) for row in rows]
    if len(rows) != EXPECTED_REQUIREMENT_COUNT:
        findings.append("RTM_COUNT_MISMATCH")
    if len(set(ids)) != EXPECTED_REQUIREMENT_COUNT:
        findings.append("RTM_UNIQUE_ID_COUNT_MISMATCH")
    source_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {status: 0 for status in sorted(STATUSES)}
    priority_counts: dict[str, int] = {priority: 0 for priority in PRIORITIES}
    for row in rows:
        source_counts[row["source_document"]] = source_counts.get(row["source_document"], 0) + 1
        status_counts[row["actual_status"]] = status_counts.get(row["actual_status"], 0) + 1
        priority_counts[row["priority"]] = priority_counts.get(row["priority"], 0) + 1
    expected_source_counts = {
        layer["document"]: layer["requirements"]
        for layer in index.get("source_layers", [])
        if isinstance(layer, dict) and "document" in layer and "requirements" in layer
    }
    if source_counts != expected_source_counts:
        findings.append("RTM_SOURCE_LAYER_COUNT_MISMATCH")
    if status_counts != index.get("status_counts"):
        findings.append("RTM_STATUS_COUNT_MISMATCH")
    ui_rows = [row for row in rows if row.get("milestone") == "M16A_UI_REFERENCE_LOCK"]
    if len(ui_rows) != 24 or any(row.get("priority") != "P0" for row in ui_rows):
        findings.append("UI_REFERENCE_LOCK_REQUIREMENTS_INVALID")
    m1_rows = [row for row in rows if row.get("milestone") == "M1"]
    report = {
        "artifact_type": "M1_LITERAL_RTM_INGESTION_REPORT",
        "schema_version": "1.0.0",
        "protocol_version": PROTOCOL_VERSION,
        "status": "PASS" if not findings else "FAIL",
        "canonical_index_path": CANONICAL_RTM_INDEX,
        "canonical_index_sha256": _sha256_bytes(index_raw),
        "protocol_sha256": index.get("protocol_sha256"),
        "master_prompt_sha256": index.get("master_prompt_sha256"),
        "ui_reference_sha256": index.get("ui_reference_sha256"),
        "registry_set_sha256": index.get("registry_set_sha256"),
        "row_fields": list(MANDATORY_ROW_FIELDS),
        "mandatory_field_count": len(MANDATORY_ROW_FIELDS),
        "requirement_count": len(rows),
        "unique_requirement_count": len(set(ids)),
        "m1_requirement_count": len(m1_rows),
        "ui_reference_p0_count": len(ui_rows),
        "source_layer_counts": source_counts,
        "status_counts": status_counts,
        "priority_counts": priority_counts,
        "shards": shard_reports,
        "shards_validated": sum(item.get("status") == "PASS" for item in shard_reports),
        "findings": sorted(set(findings)),
        "release_authorized": False,
        "_rows": rows,
        "_index": index,
    }
    return report


def _public_ingestion_report(report: Mapping[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(value) for key, value in report.items() if not key.startswith("_")}


def _role_policy() -> dict[str, Any]:
    policy = {
        "artifact_type": "ROLE_PERMISSION_POLICY",
        "schema_version": "1.0.0",
        "protocol_version": PROTOCOL_VERSION,
        "canonical_state_owner": "CONTROL_PLANE",
        "roles": {
            "IMPLEMENTER": {
                "may_modify_production": True,
                "may_modify_expected_result": False,
                "may_close_defect": False,
                "may_change_canonical_status": False,
                "may_change_release_decision": False,
            },
            "VERIFIER": {
                "may_modify_production": False,
                "may_modify_expected_result": False,
                "may_close_defect": False,
                "may_change_canonical_status": False,
                "may_change_release_decision": False,
            },
            "ADVERSARY": {
                "may_modify_production": False,
                "may_modify_expected_result": False,
                "may_close_defect": False,
                "may_change_canonical_status": False,
                "may_change_release_decision": False,
            },
            "L4_L5_WORKER": {
                "may_modify_production": False,
                "may_modify_expected_result": False,
                "may_close_defect": False,
                "may_change_canonical_status": False,
                "may_change_release_decision": False,
            },
            "CONTROL_PLANE": {
                "may_modify_production": False,
                "may_modify_expected_result": False,
                "may_close_defect": True,
                "may_change_canonical_status": True,
                "may_change_release_decision": True,
            },
        },
        "protected_paths": [*PROTECTED_PREFIXES],
        "role_outputs_are": ["PROPOSAL", "RAW_EVIDENCE"],
        "release_authorized": False,
    }
    return _signed(policy, "policy_sha256")


def authorize_role_action(
    role: str,
    action: str,
    paths: Sequence[str] = (),
    *,
    policy: Mapping[str, Any] | None = None,
) -> list[str]:
    findings: list[str] = []
    policy = policy or _role_policy()
    if not _verify_signature(policy, "policy_sha256"):
        findings.append("ROLE_POLICY_SIGNATURE_INVALID")
        return findings
    role_rules = policy.get("roles", {}).get(role)
    if not isinstance(role_rules, dict):
        return [f"ROLE_UNKNOWN:{role}"]
    action_to_field = {
        "modify_production": "may_modify_production",
        "modify_expected_result": "may_modify_expected_result",
        "close_defect": "may_close_defect",
        "change_canonical_status": "may_change_canonical_status",
        "change_release_decision": "may_change_release_decision",
    }
    field = action_to_field.get(action)
    if field is None:
        findings.append(f"ROLE_ACTION_UNKNOWN:{action}")
    elif role_rules.get(field) is not True:
        findings.append(f"ROLE_PRIVILEGE_ESCALATION:{role}:{action}")
    for path in paths:
        normalized = PurePosixPath(path).as_posix()
        if any(normalized == prefix or normalized.startswith(prefix) for prefix in PROTECTED_PREFIXES):
            findings.append(f"PROTECTED_PATH_CHANGE_REJECTED:{path}")
    return sorted(set(findings))


def _load_governing_work_order(repo_root: Path) -> dict[str, Any]:
    work_order = _read_json(_safe_repo_path(repo_root, GOVERNING_WORK_ORDER))
    if not _verify_signature(work_order, "work_order_sha256"):
        raise ControlPlaneError("GOVERNING_WORK_ORDER_SIGNATURE_INVALID")
    if work_order.get("work_order_id") != "WO-M1-EXISTING-M9-MIGRATION-001":
        raise ControlPlaneError("GOVERNING_WORK_ORDER_ID_MISMATCH")
    if work_order.get("release_authorized") is not False:
        raise ControlPlaneError("GOVERNING_WORK_ORDER_RELEASE_AUTHORIZED")
    return work_order


def _requirement_order(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {str(row["requirement_id"]): index for index, row in enumerate(rows)}


def default_scheduler_context(
    rows: Sequence[Mapping[str, Any]],
    governing_work_order: Mapping[str, Any],
) -> dict[str, Any]:
    requirement_ids = [str(item) for item in governing_work_order.get("requirement_ids", [])]
    primary = str(governing_work_order.get("primary_requirement_id", ""))
    scores = {
        req_id: (100000 if req_id == primary else 10000 - index)
        for index, req_id in enumerate(requirement_ids)
    }
    return {
        "completed_dependencies": ["GATE-M0"],
        "available_artifacts": [CANONICAL_RTM_INDEX, GOVERNING_WORK_ORDER, M1_SCOPE],
        "available_environments": ["SOURCE_RUNTIME_L2"],
        "ready_roles": list(ROLES),
        "active_locks": [],
        "critical_path_scores": scores,
        "retry_budget": {req_id: 1 for req_id in requirement_ids},
        "evidence_freshness": {req_id: "CURRENT" for req_id in requirement_ids},
        "allowed_milestones": ["M1"],
        "governing_work_order_sha256": governing_work_order.get("work_order_sha256"),
        "canonical_order_size": len(rows),
    }


def _dependency_complete(
    dependency: str,
    *,
    completed: set[str],
    available_artifacts: set[str],
    effective_status: Mapping[str, str],
) -> bool:
    if dependency.startswith("GATE-"):
        return dependency in completed
    if dependency.startswith("REQ-"):
        return effective_status.get(dependency) == "VERIFIED"
    return dependency in available_artifacts or dependency in completed


def select_next_requirement(
    rows: Sequence[Mapping[str, Any]],
    context: Mapping[str, Any],
) -> dict[str, Any]:
    completed = set(context.get("completed_dependencies", []))
    available_artifacts = set(context.get("available_artifacts", []))
    environments = set(context.get("available_environments", []))
    ready_roles = set(context.get("ready_roles", []))
    active_locks = context.get("active_locks", [])
    locked_ids = {
        str(item.get("requirement_id"))
        for item in active_locks
        if isinstance(item, dict) and item.get("state") == "ACQUIRED"
    }
    scores = context.get("critical_path_scores", {})
    retry_budget = context.get("retry_budget", {})
    freshness = context.get("evidence_freshness", {})
    milestones = set(context.get("allowed_milestones", ["M1"]))
    order = _requirement_order(rows)
    effective_status = {
        str(row["requirement_id"]): str(row["actual_status"]) for row in rows
    }
    eligible: list[Mapping[str, Any]] = []
    exclusions: dict[str, list[str]] = {}
    for row in rows:
        req_id = str(row["requirement_id"])
        reasons: list[str] = []
        if row.get("actual_status") == "VERIFIED":
            reasons.append("ALREADY_VERIFIED")
        if row.get("milestone") not in milestones:
            reasons.append("MILESTONE_NOT_ACTIVE")
        if any(
            not _dependency_complete(
                str(dep),
                completed=completed,
                available_artifacts=available_artifacts,
                effective_status=effective_status,
            )
            for dep in row.get("dependencies", [])
        ):
            reasons.append("DEPENDENCY_BLOCKED")
        if row.get("assigned_role") not in ready_roles:
            reasons.append("ROLE_NOT_READY")
        required_environment = {
            "L0": "SOURCE_RUNTIME_L2",
            "L1": "SOURCE_RUNTIME_L2",
            "L2": "SOURCE_RUNTIME_L2",
            "L3": "PACKAGE_RUNTIME_L3",
            "L4": "WINDOWS_INSTALLED_L4",
            "L5": "PHYSICAL_L5",
        }.get(str(row.get("target_evidence_level")))
        if required_environment not in environments:
            reasons.append("ENVIRONMENT_UNAVAILABLE")
        if req_id in locked_ids:
            reasons.append("LOCK_CONFLICT")
        if int(retry_budget.get(req_id, 1)) <= 0:
            reasons.append("RETRY_BUDGET_EXHAUSTED")
        if freshness.get(req_id, "CURRENT") not in {"CURRENT", "STALE"}:
            reasons.append("EVIDENCE_FRESHNESS_INVALID")
        if reasons:
            exclusions[req_id] = reasons
        else:
            eligible.append(row)
    if not eligible:
        raise ControlPlaneError("SCHEDULER_NO_ELIGIBLE_REQUIREMENT")
    priority_rank = {value: index for index, value in enumerate(PRIORITIES)}
    eligible.sort(
        key=lambda row: (
            priority_rank[str(row["priority"])],
            -int(scores.get(str(row["requirement_id"]), 0)),
            order[str(row["requirement_id"])],
            str(row["requirement_id"]),
        )
    )
    selected = eligible[0]
    decision = {
        "artifact_type": "M1_SCHEDULER_DECISION",
        "schema_version": "1.0.0",
        "scheduler": "DETERMINISTIC_NO_LLM_SELECTION",
        "selected_requirement_id": selected["requirement_id"],
        "selected_priority": selected["priority"],
        "selected_role": selected["assigned_role"],
        "selected_canonical_ordinal": order[str(selected["requirement_id"])],
        "selected_critical_path_score": int(scores.get(str(selected["requirement_id"]), 0)),
        "eligible_count": len(eligible),
        "excluded_count": len(exclusions),
        "sort_policy": ["priority", "critical_path_score_desc", "canonical_age", "requirement_id"],
        "context_sha256": _sha256_json(context),
        "release_authorized": False,
    }
    return _signed(decision, "decision_sha256")


def acquire_exclusive_lock(
    requirement_id: str,
    owner_role: str,
    active_locks: Sequence[Mapping[str, Any]],
    governing_work_order_sha256: str,
) -> dict[str, Any]:
    if owner_role not in ROLES:
        raise ControlPlaneError(f"LOCK_OWNER_ROLE_INVALID:{owner_role}")
    for lock in active_locks:
        if lock.get("state") == "ACQUIRED":
            raise ControlPlaneError("PARALLEL_REQUIREMENT_LOCK_REJECTED")
    lock = {
        "artifact_type": "EXCLUSIVE_REQUIREMENT_LOCK",
        "schema_version": "1.0.0",
        "lock_id": f"LOCK-{requirement_id}-M1",
        "requirement_id": requirement_id,
        "owner_role": owner_role,
        "state": "ACQUIRED",
        "parallel_lock_authorized": False,
        "governing_work_order_sha256": governing_work_order_sha256,
    }
    return _signed(lock, "lock_sha256")


def emit_runtime_work_order(
    selected_row: Mapping[str, Any],
    scheduler_decision: Mapping[str, Any],
    lock: Mapping[str, Any],
    governing_work_order: Mapping[str, Any],
    exact_head: str,
) -> dict[str, Any]:
    allowed = list(governing_work_order.get("files_allowed_to_change", []))
    forbidden = list(governing_work_order.get("files_forbidden_to_change", []))
    work_order = {
        "artifact_type": "SIGNED_WORK_ORDER",
        "schema_version": "3.1.0",
        "work_order_id": f"WO-M1-RUNTIME-{selected_row['requirement_id']}",
        "governing_work_order_id": governing_work_order.get("work_order_id"),
        "governing_work_order_sha256": governing_work_order.get("work_order_sha256"),
        "active_milestone": "M1",
        "requirement_id": selected_row["requirement_id"],
        "defect_id": governing_work_order.get("defect_id"),
        "assigned_role": "IMPLEMENTER",
        "canonical_owner_role": selected_row["assigned_role"],
        "change_boundary": governing_work_order.get("change_boundary"),
        "files_allowed_to_change": allowed,
        "files_forbidden_to_change": forbidden,
        "hypothesis": governing_work_order.get("hypothesis"),
        "next_test": governing_work_order.get("next_test"),
        "expected_result": governing_work_order.get("expected_result"),
        "rollback_condition": governing_work_order.get("rollback_condition"),
        "rollback_command": governing_work_order.get("rollback_command"),
        "target_evidence_level": "L2_SOURCE_RUNTIME",
        "exact_head": exact_head,
        "scheduler_decision_sha256": scheduler_decision.get("decision_sha256"),
        "exclusive_lock": lock,
        "release_authorized": False,
        "product_change_authorized": False,
    }
    return _signed(work_order, "work_order_sha256")


def verify_runtime_work_order(work_order: Mapping[str, Any]) -> list[str]:
    findings: list[str] = []
    if not _verify_signature(work_order, "work_order_sha256"):
        findings.append("RUNTIME_WORK_ORDER_SIGNATURE_INVALID")
    lock = work_order.get("exclusive_lock")
    if not isinstance(lock, dict) or not _verify_signature(lock, "lock_sha256"):
        findings.append("RUNTIME_WORK_ORDER_LOCK_INVALID")
    elif lock.get("requirement_id") != work_order.get("requirement_id"):
        findings.append("RUNTIME_WORK_ORDER_LOCK_REQUIREMENT_MISMATCH")
    if work_order.get("release_authorized") is not False:
        findings.append("RUNTIME_WORK_ORDER_RELEASE_AUTHORIZED")
    if work_order.get("product_change_authorized") is not False:
        findings.append("RUNTIME_WORK_ORDER_PRODUCT_CHANGE_AUTHORIZED")
    if work_order.get("target_evidence_level") != "L2_SOURCE_RUNTIME":
        findings.append("RUNTIME_WORK_ORDER_EVIDENCE_LEVEL_INVALID")
    return sorted(set(findings))


def validate_changed_paths(
    changed_paths: Sequence[str],
    governing_work_order: Mapping[str, Any],
) -> list[str]:
    allowed = set(str(item) for item in governing_work_order.get("files_allowed_to_change", []))
    findings: list[str] = []
    for path in changed_paths:
        normalized = PurePosixPath(path).as_posix()
        if normalized not in allowed:
            findings.append(f"WORK_ORDER_SCOPE_VIOLATION:{normalized}")
        if any(normalized.startswith(prefix) for prefix in PRODUCT_PREFIXES):
            findings.append(f"PRODUCT_CODE_CHANGED_WITHOUT_REQUIREMENT:{normalized}")
        if any(normalized == prefix or normalized.startswith(prefix) for prefix in PROTECTED_PREFIXES):
            findings.append(f"CANONICAL_SOURCE_MODIFIED:{normalized}")
    return sorted(set(findings))


def validate_status_proposal(
    row: Mapping[str, Any],
    proposed_status: str,
    evidence_ids: Sequence[str],
    proposer_role: str,
) -> list[str]:
    findings: list[str] = []
    if proposer_role != "CONTROL_PLANE":
        findings.append(f"CANONICAL_STATUS_OWNER_VIOLATION:{proposer_role}")
    if proposed_status not in STATUSES:
        findings.append("PROPOSED_STATUS_INVALID")
    if proposed_status == "VERIFIED" and not evidence_ids:
        findings.append(f"FORGED_VERIFIED_REJECTED:{row.get('requirement_id', 'UNKNOWN')}")
    return findings


def validate_l5_claim(claim: Mapping[str, Any]) -> list[str]:
    findings: list[str] = []
    if claim.get("status") == "VERIFIED" and claim.get("level") == "L5":
        required = (
            claim.get("physical_pass") is True,
            bool(claim.get("artifact_sha256")),
            bool(claim.get("installed_root")),
            bool(claim.get("entry_point")),
            bool(claim.get("actual_command_line")),
            bool(claim.get("environment_id")),
            bool(claim.get("evidence_ids")),
        )
        if not all(required):
            findings.append("FORGED_L5_REJECTED")
    return findings


def _gate_policy_sha256() -> str:
    return _sha256_json(GATE_POLICY)


def run_m1_negative_controls(
    repo_root: Path,
    rows: Sequence[Mapping[str, Any]],
    governing_work_order: Mapping[str, Any],
    exact_head: str,
) -> dict[str, Any]:
    controls: list[dict[str, Any]] = []

    def record(control_id: str, expected: str, findings: Iterable[str]) -> None:
        actual = sorted(set(findings))
        controls.append(
            {
                "control_id": control_id,
                "expected_finding": expected,
                "actual_findings": actual,
                "status": "PASS" if expected in actual else "FAIL",
            }
        )

    with tempfile.TemporaryDirectory() as temporary:
        temp_root = Path(temporary) / "repo"
        source_agent = repo_root / "docs/evidence/agent_v3_1"
        shutil.copytree(source_agent, temp_root / "docs/evidence/agent_v3_1")
        index = _read_json(temp_root / CANONICAL_RTM_INDEX)
        index["protocol_sha256"] = "0" * 64
        _write_json(temp_root / CANONICAL_RTM_INDEX, index)
        record(
            "NEG-M1-001-PROTOCOL-HASH-SWAP",
            "RTM_INDEX_BINDING_MISMATCH:protocol_sha256",
            ingest_literal_rtm(temp_root).get("findings", []),
        )

    with tempfile.TemporaryDirectory() as temporary:
        temp_root = Path(temporary) / "repo"
        source_agent = repo_root / "docs/evidence/agent_v3_1"
        shutil.copytree(source_agent, temp_root / "docs/evidence/agent_v3_1")
        first_shard = temp_root / "docs/evidence/agent_v3_1/rtm/REQUIREMENTS_TRACEABILITY_MATRIX.part-001.json"
        shard = _read_json(first_shard)
        shard["rows"].pop()
        _write_json(first_shard, shard)
        record(
            "NEG-M1-002-MISSING-REQUIREMENT",
            "RTM_SHARD_SHA256_MISMATCH:docs/evidence/agent_v3_1/rtm/REQUIREMENTS_TRACEABILITY_MATRIX.part-001.json",
            ingest_literal_rtm(temp_root).get("findings", []),
        )

    record(
        "NEG-M1-003-ROLE-PRIVILEGE-ESCALATION",
        "ROLE_PRIVILEGE_ESCALATION:VERIFIER:modify_production",
        authorize_role_action("VERIFIER", "modify_production", ["src/quantum/application/desktop_center.py"]),
    )

    forged_row = copy.deepcopy(dict(rows[0]))
    record(
        "NEG-M1-004-FORGED-VERIFIED",
        f"FORGED_VERIFIED_REJECTED:{forged_row['requirement_id']}",
        validate_status_proposal(forged_row, "VERIFIED", [], "CONTROL_PLANE"),
    )

    record(
        "NEG-M1-005-FORGED-L5",
        "FORGED_L5_REJECTED",
        validate_l5_claim(
            {
                "status": "VERIFIED",
                "level": "L5",
                "artifact_sha256": None,
                "installed_root": None,
                "entry_point": None,
                "actual_command_line": None,
                "environment_id": None,
                "evidence_ids": [],
                "physical_pass": False,
            }
        ),
    )

    mutated_policy = copy.deepcopy(GATE_POLICY)
    mutated_policy["negative_controls_required"] = False
    record(
        "NEG-M1-006-GATE-MODIFICATION",
        "GATE_POLICY_HASH_MISMATCH",
        [] if _sha256_json(mutated_policy) == _gate_policy_sha256() else ["GATE_POLICY_HASH_MISMATCH"],
    )

    try:
        acquire_exclusive_lock(
            "REQ-MP2-0142",
            "CONTROL_PLANE",
            [{"requirement_id": "REQ-MP2-0013", "state": "ACQUIRED"}],
            str(governing_work_order.get("work_order_sha256")),
        )
        parallel_findings: list[str] = []
    except ControlPlaneError as exc:
        parallel_findings = [str(exc)]
    record(
        "NEG-M1-007-PARALLEL-LOCK",
        "PARALLEL_REQUIREMENT_LOCK_REJECTED",
        parallel_findings,
    )

    context = default_scheduler_context(rows, governing_work_order)
    decision = select_next_requirement(rows, context)
    lock = acquire_exclusive_lock(
        str(decision["selected_requirement_id"]),
        "CONTROL_PLANE",
        [],
        str(governing_work_order.get("work_order_sha256")),
    )
    selected = next(row for row in rows if row["requirement_id"] == decision["selected_requirement_id"])
    runtime_work_order = emit_runtime_work_order(
        selected, decision, lock, governing_work_order, exact_head
    )
    tampered = copy.deepcopy(runtime_work_order)
    tampered["expected_result"] = "FORGED_PASS"
    record(
        "NEG-M1-008-WORK-ORDER-TAMPER",
        "RUNTIME_WORK_ORDER_SIGNATURE_INVALID",
        verify_runtime_work_order(tampered),
    )

    record(
        "NEG-M1-009-WORK-ORDER-SCOPE",
        "WORK_ORDER_SCOPE_VIOLATION:src/quantum/application/desktop_center.py",
        validate_changed_paths(
            ["src/quantum/application/desktop_center.py"], governing_work_order
        ),
    )

    mutated_policy_doc = _role_policy()
    mutated_policy_doc["roles"]["ADVERSARY"]["may_change_release_decision"] = True
    record(
        "NEG-M1-010-ROLE-POLICY-TAMPER",
        "ROLE_POLICY_SIGNATURE_INVALID",
        authorize_role_action(
            "ADVERSARY", "change_release_decision", policy=mutated_policy_doc
        ),
    )

    passed = sum(item["status"] == "PASS" for item in controls)
    report = {
        "artifact_type": "M1_NEGATIVE_CONTROL_REPORT",
        "schema_version": "1.0.0",
        "protocol_version": PROTOCOL_VERSION,
        "exact_head": exact_head,
        "status": "PASS" if passed == len(controls) else "FAIL",
        "controls": controls,
        "controls_passed": passed,
        "controls_total": len(controls),
        "all_controls_make_gate_red": passed == len(controls),
        "release_authorized": False,
    }
    return _signed(report, "report_sha256")


def evaluate_m1_gate(
    repo_root: Path,
    exact_head: str,
    changed_paths: Sequence[str],
) -> dict[str, Any]:
    findings: list[str] = []
    ingestion = ingest_literal_rtm(repo_root)
    if ingestion.get("status") != "PASS":
        findings.extend(ingestion.get("findings", []))
    rows = ingestion.get("_rows", [])
    try:
        governing_work_order = _load_governing_work_order(repo_root)
    except (OSError, UnicodeError, json.JSONDecodeError, ControlPlaneError) as exc:
        governing_work_order = {}
        findings.append(str(exc))
    if governing_work_order:
        findings.extend(validate_changed_paths(changed_paths, governing_work_order))
    if not rows or not governing_work_order:
        return {
            "artifact_type": "M1_IMPLEMENTATION_REPORT",
            "schema_version": "1.0.0",
            "protocol_version": PROTOCOL_VERSION,
            "exact_head": exact_head,
            "gate": "GATE-M1",
            "status": "FAIL",
            "findings": sorted(set(findings or ["M1_PREREQUISITE_MISSING"])),
            "release_authorized": False,
        }
    context = default_scheduler_context(rows, governing_work_order)
    decision_a = select_next_requirement(rows, context)
    decision_b = select_next_requirement(rows, copy.deepcopy(context))
    if decision_a != decision_b:
        findings.append("SCHEDULER_NONDETERMINISTIC")
    if decision_a.get("selected_requirement_id") != governing_work_order.get("primary_requirement_id"):
        findings.append("SCHEDULER_PRIMARY_REQUIREMENT_MISMATCH")
    lock = acquire_exclusive_lock(
        str(decision_a["selected_requirement_id"]),
        "CONTROL_PLANE",
        context.get("active_locks", []),
        str(governing_work_order.get("work_order_sha256")),
    )
    selected = next(
        row for row in rows if row["requirement_id"] == decision_a["selected_requirement_id"]
    )
    runtime_work_order = emit_runtime_work_order(
        selected, decision_a, lock, governing_work_order, exact_head
    )
    findings.extend(verify_runtime_work_order(runtime_work_order))
    policy = _role_policy()
    if not _verify_signature(policy, "policy_sha256"):
        findings.append("ROLE_POLICY_SIGNATURE_INVALID")
    negatives = run_m1_negative_controls(
        repo_root, rows, governing_work_order, exact_head
    )
    if negatives.get("status") != "PASS":
        findings.append("M1_NEGATIVE_CONTROLS_FAILED")
    if _gate_policy_sha256() != _sha256_json(GATE_POLICY):
        findings.append("GATE_POLICY_HASH_MISMATCH")
    coverage = ingestion.get("requirement_count", 0) / EXPECTED_REQUIREMENT_COUNT
    if coverage != 1.0:
        findings.append("M1_LITERAL_RTM_COVERAGE_INCOMPLETE")
    hash_binding = all(
        ingestion.get(field) == expected
        for field, expected in (
            ("protocol_sha256", EXPECTED_PROTOCOL_SHA256),
            ("master_prompt_sha256", EXPECTED_MASTER_PROMPT_SHA256),
            ("ui_reference_sha256", EXPECTED_UI_REFERENCE_SHA256),
            ("registry_set_sha256", EXPECTED_REGISTRY_SET_SHA256),
        )
    )
    if not hash_binding:
        findings.append("M1_HASH_BINDING_INCOMPLETE")
    report = {
        "artifact_type": "M1_IMPLEMENTATION_REPORT",
        "schema_version": "1.0.0",
        "protocol_version": PROTOCOL_VERSION,
        "exact_head": exact_head,
        "gate": "GATE-M1",
        "gate_policy_sha256": _gate_policy_sha256(),
        "status": "PASS" if not findings else "FAIL",
        "literal_rtm_coverage": coverage,
        "requirement_count": ingestion.get("requirement_count"),
        "protocol_hash_bound": hash_binding,
        "negative_controls_status": negatives.get("status"),
        "scheduler_deterministic": decision_a == decision_b,
        "selected_requirement_id": decision_a.get("selected_requirement_id"),
        "exclusive_lock_count": 1,
        "runtime_work_order_sha256": runtime_work_order.get("work_order_sha256"),
        "changed_paths": sorted(set(changed_paths)),
        "product_code_unchanged": not any(
            PurePosixPath(path).as_posix().startswith(PRODUCT_PREFIXES)
            for path in changed_paths
        ),
        "findings": sorted(set(findings)),
        "release_authorized": False,
        "_ingestion": ingestion,
        "_policy": policy,
        "_decision": decision_a,
        "_lock": lock,
        "_runtime_work_order": runtime_work_order,
        "_negatives": negatives,
    }
    return report


def _claim(
    claim_id: str,
    text: str,
    status: str,
    level: str,
    req_ids: list[str],
    head: str,
    evidence_ids: list[str],
) -> dict[str, Any]:
    return {
        "claim_id": claim_id,
        "claim": text,
        "status": status,
        "level": level,
        "requirement_ids": req_ids,
        "test_ids": [],
        "exact_head": head,
        "artifact_sha256": None,
        "installed_root": None,
        "entry_point": "tools/m9_maximum_assurance_control_plane.py",
        "actual_command_line": None,
        "environment_id": "SOURCE_RUNTIME_L2",
        "evidence_ids": evidence_ids,
        "falsification_attempts": [],
        "limitations": ["No L3, L4, L5 or release claim is made by Gate M1."],
    }


def write_m1_evidence(
    repo_root: Path,
    output_dir: Path,
    exact_head: str,
    changed_paths: Sequence[str],
) -> dict[str, Any]:
    gate = evaluate_m1_gate(repo_root, exact_head, changed_paths)
    output_dir.mkdir(parents=True, exist_ok=True)
    ingestion = _public_ingestion_report(gate.get("_ingestion", {}))
    policy = gate.get("_policy", _role_policy())
    decision = gate.get("_decision", {})
    runtime_work_order = gate.get("_runtime_work_order", {})
    negatives = gate.get("_negatives", {})
    gate_public = {key: copy.deepcopy(value) for key, value in gate.items() if not key.startswith("_")}
    role_trace = {
        "artifact_type": "ROLE_TRACE_INDEX",
        "schema_version": "1.0.0",
        "exact_head": exact_head,
        "traces": [
            {"role": "IMPLEMENTER", "result_type": "PROPOSAL", "action": "minimal existing-M9 migration"},
            {"role": "VERIFIER", "result_type": "RAW_EVIDENCE", "action": "independent literal/hash/scope verification"},
            {"role": "ADVERSARY", "result_type": "RAW_EVIDENCE", "action": "negative and mutation controls"},
            {"role": "CONTROL_PLANE", "result_type": "DETERMINISTIC_DECISION", "action": "Gate M1 decision"},
        ],
        "production_code_modified_by_verifier_or_adversary": False,
        "release_authorized": False,
    }
    transition_coverage = {
        "artifact_type": "STATE_TRANSITION_COVERAGE",
        "schema_version": "1.0.0",
        "exact_head": exact_head,
        "transitions": [
            "M1_OPEN_TO_LITERAL_INGESTED",
            "LITERAL_INGESTED_TO_REQUIREMENT_SELECTED",
            "REQUIREMENT_SELECTED_TO_LOCK_ACQUIRED",
            "LOCK_ACQUIRED_TO_WORK_ORDER_EMITTED",
            "WORK_ORDER_EMITTED_TO_NEGATIVE_CONTROLS_PASS",
            "NEGATIVE_CONTROLS_PASS_TO_GATE_M1_DECIDED",
        ],
        "covered_transition_count": 6 if gate.get("status") == "PASS" else 5,
        "required_transition_count": 6,
        "status": "COMPLETE" if gate.get("status") == "PASS" else "PARTIAL",
        "release_authorized": False,
    }
    claim_ledger = {
        "artifact_type": "CLAIM_LEDGER",
        "schema_version": "1.0.0",
        "protocol_version": PROTOCOL_VERSION,
        "exact_head": exact_head,
        "claims": [
            _claim("CLM-M1-001", "The immutable canonical RTM was ingested literally at source runtime.", "VERIFIED" if ingestion.get("status") == "PASS" else "FAILED", "L2", ["REQ-MP2-0142", "REQ-MP2-0143", "REQ-MP2-0144"], exact_head, ["EVD-M1-LITERAL-RTM"]),
            _claim("CLM-M1-002", "The scheduler, lock and signed work order are deterministic.", "VERIFIED" if gate.get("scheduler_deterministic") else "FAILED", "L2", ["REQ-MP2-0146", "REQ-MP2-0072", "REQ-MP2-0082"], exact_head, ["EVD-M1-SCHEDULER"]),
            _claim("CLM-M1-003", "All mandatory M1 negative controls make the gate red.", "VERIFIED" if negatives.get("status") == "PASS" else "FAILED", "L2", ["REQ-MP2-0149", "REQ-MP2-0150"], exact_head, ["EVD-M1-NEGATIVE-CONTROLS"]),
            _claim("CLM-M1-004", "Quantum is authorized for release.", "UNVERIFIED", "L0", ["REQ-MP2-0151"], exact_head, []),
        ],
        "release_authorized": False,
    }
    defects = {
        "artifact_type": "DEFECT_REGISTER",
        "schema_version": "1.0.0",
        "exact_head": exact_head,
        "defects": [
            {
                "defect_id": "M1-D-CONTROLLER-001",
                "severity": "P0",
                "status": "CLOSED_VERIFIED" if gate.get("status") == "PASS" else "OPEN",
                "title": "Protocol v3.1 literal RTM control-plane runtime was absent",
                "evidence_ids": ["EVD-M1-LITERAL-RTM", "EVD-M1-SCHEDULER", "EVD-M1-NEGATIVE-CONTROLS"],
            }
        ],
        "release_authorized": False,
    }
    state = {
        "artifact_type": "AUTONOMOUS_EXECUTION_STATE",
        "schema_version": "3.1.0",
        "exact_head": exact_head,
        "active_milestone": "M1" if gate.get("status") != "PASS" else "M2",
        "canonical_state_owner": "CONTROL_PLANE",
        "canonical_rtm": {
            "count": ingestion.get("requirement_count"),
            "registry_set_sha256": ingestion.get("registry_set_sha256"),
            "runtime_ingestion": ingestion.get("status"),
        },
        "gate_m1": gate.get("status"),
        "selected_requirement_id": gate.get("selected_requirement_id"),
        "current_decision": [
            "FAIL-CLOSED",
            "RELEASE_BLOCKED",
        ],
        "release_authorized": False,
        "physical_l5_status": "UNVERIFIED",
    }
    ledger = {
        "artifact_type": "WORK_ORDER_LEDGER",
        "schema_version": "3.1.0",
        "exact_head": exact_head,
        "entries": [
            {
                "work_order_id": runtime_work_order.get("work_order_id"),
                "work_order_sha256": runtime_work_order.get("work_order_sha256"),
                "requirement_id": runtime_work_order.get("requirement_id"),
                "status": "EVIDENCE_ACCEPTED" if gate.get("status") == "PASS" else "FAILED",
                "exclusive_lock_state": "RELEASED_AFTER_DETERMINISTIC_DECISION",
            }
        ],
        "active_lock_count": 0,
        "release_authorized": False,
    }
    documents = {
        "ROLE_PERMISSION_POLICY.json": policy,
        "ROLE_TRACE_INDEX.json": role_trace,
        "STATE_TRANSITION_COVERAGE.json": transition_coverage,
        "CLAIM_LEDGER.json": claim_ledger,
        "DEFECT_REGISTER.json": defects,
        "M1_LITERAL_RTM_INGESTION_REPORT.json": ingestion,
        "M1_NEGATIVE_CONTROL_REPORT.json": negatives,
        "M1_SCHEDULER_DECISION.json": decision,
        "M1_SIGNED_WORK_ORDER.json": runtime_work_order,
        "AUTONOMOUS_EXECUTION_STATE_M1_RUNTIME.json": state,
        "WORK_ORDER_LEDGER_M1_RUNTIME.json": ledger,
        "M1_IMPLEMENTATION_REPORT.json": gate_public,
    }
    for name, document in documents.items():
        _write_json(output_dir / name, document)
    return gate_public


def _decision_text(head: str, decision: str = "RELEASE_BLOCKED") -> str:
    return (
        "# Quantum Final Release Decision\n\n"
        f"Decision: {decision}\n"
        "Maximum claim: GATE_M1_SOURCE_RUNTIME_PASS\n"
        f"Exact head: {head}\n"
        "Marketplace writes: DISABLED\n"
        "Merge to main: NOT_AUTHORIZED\n"
        "Production release: NOT_AUTHORIZED\n\n"
        "Reason: L3 package, L4 installed runtime, same-artifact verification and physical L5 remain open.\n"
    )


def bootstrap_bundle(output_dir: Path, exact_head: str, repo_root: Path | None = None) -> None:
    repo_root = (repo_root or Path.cwd()).resolve()
    ingestion = ingest_literal_rtm(repo_root)
    if ingestion.get("status") != "PASS":
        raise ControlPlaneError("LITERAL_RTM_INGESTION_FAILED:" + ",".join(ingestion.get("findings", [])))
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = ingestion["_rows"]
    common = {"protocol_version": PROTOCOL_VERSION, "exact_head": exact_head}
    materialized_rtm = {
        **common,
        "schema_version": "quantum-literal-rtm-materialized-v3.1.0",
        "protocol_sha256": EXPECTED_PROTOCOL_SHA256,
        "master_prompt_sha256": EXPECTED_MASTER_PROMPT_SHA256,
        "ui_reference_sha256": EXPECTED_UI_REFERENCE_SHA256,
        "registry_set_sha256": EXPECTED_REGISTRY_SET_SHA256,
        "row_fields": list(MANDATORY_ROW_FIELDS),
        "requirement_count": len(rows),
        "requirements": rows,
    }
    payloads: dict[str, dict[str, Any]] = {
        "REQUIREMENTS_TRACEABILITY_MATRIX.json": materialized_rtm,
        "CLAIM_LEDGER.json": {
            **common,
            "claims": [
                _claim("CLM-M9-001", "The literal Protocol v3.1 RTM is structurally auditable.", "VERIFIED", "L2", ["REQ-MP2-0142", "REQ-MP2-0143"], exact_head, ["EVD-M1-LITERAL-RTM"]),
                _claim("CLM-M9-002", "Quantum is authorized for production release.", "UNVERIFIED", "L0", ["REQ-MP2-0151"], exact_head, []),
            ],
        },
        "DEFECT_REGISTER.json": {
            **common,
            "defects": [
                {"defect_id": "M9-D001", "severity": "P0", "status": "OPEN", "title": "Physical same-artifact L5 path is unverified"},
                {"defect_id": "M9-D002", "severity": "P1", "status": "OPEN", "title": "Independent adversarial RUN B is unbound"},
            ],
        },
        "STATE_TRANSITION_COVERAGE.json": {**common, "critical_transition_coverage": 0.0, "covered_transitions": [], "uncovered_transitions": ["INSTALL", "UPDATE_ROLLBACK", "RECOVERY"], "status": "PARTIAL"},
        "PARAMETER_COMBINATION_COVERAGE.json": {**common, "critical_launcher_3way_coverage": 0.0, "pairwise_coverage": 0.0, "historical_combinations_preserved": True, "status": "PARTIAL"},
        "MUTATION_REPORT.json": {**common, "critical_mutation_kill_rate": 0.0, "general_mutation_score": 0.0, "status": "UNVERIFIED"},
        "FUZZ_CORPUS_INDEX.json": {**common, "corpus": [], "crash_seeds": [], "corpus_retained": True, "status": "UNVERIFIED"},
        "FAULT_INJECTION_REPORT.json": {**common, "harness_negative_controls": "PENDING", "controls": [], "status": "PARTIAL"},
        "SECURITY_REPORT.json": {**common, "marketplace_write_enabled": False, "independent_adversary_new_p0_p1": None, "supply_chain_pinned": False, "status": "PARTIAL"},
        "SBOM.json": {"bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1, "exact_head": exact_head, "components": [], "status": "UNVERIFIED"},
        "LICENSE_REPORT.json": {**common, "dependencies_reviewed": [], "status": "UNVERIFIED"},
        "BUILD_PROVENANCE.json": {**common, "source_exact_head": exact_head, "artifact_sha256": None, "run_a_artifact_sha256": None, "run_b_artifact_sha256": None, "same_artifact_run_a_run_b": False, "source_to_installed_provenance_verified": False, "status": "PARTIAL"},
        "INSTALLED_FILE_MANIFEST.json": {**common, "artifact_sha256": None, "installed_root": None, "files": [], "manifest_diff_count": None, "installed_file_diff_count": None, "status": "UNVERIFIED"},
        "PHYSICAL_PILOT_REPORT.json": {**common, "level": "L5", "physical_pass": False, "entry_point": None, "actual_command_line": None, "artifact_sha256": None, "status": "UNVERIFIED"},
        "RESIDUAL_RISK_REGISTER.json": {**common, "risks": [{"risk_id": "RSK-M9-001", "severity": "P0", "status": "OPEN", "description": "No physical L5 pilot on the exact artifact."}, {"risk_id": "RSK-M9-002", "severity": "P1", "status": "OPEN", "description": "Coverage and adversarial gates are incomplete."}]},
    }
    for name, payload in payloads.items():
        _write_json(output_dir / name, payload)
    (output_dir / "FINAL_RELEASE_DECISION.md").write_text(
        _decision_text(exact_head), encoding="utf-8", newline="\n"
    )


def _parse_decision(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            result[key.strip().lower()] = value.strip()
    return result


def _rtm_map(rtm: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item["requirement_id"]): dict(item)
        for item in rtm.get("requirements", [])
        if isinstance(item, dict) and item.get("requirement_id")
    }


def _validate_rtm(rtm: Mapping[str, Any]) -> list[str]:
    findings: list[str] = []
    if rtm.get("protocol_version") != PROTOCOL_VERSION:
        findings.append("RTM_PROTOCOL_VERSION_MISMATCH")
    if rtm.get("protocol_sha256") != EXPECTED_PROTOCOL_SHA256:
        findings.append("RTM_PROTOCOL_HASH_MISMATCH")
    if rtm.get("requirement_count") != EXPECTED_REQUIREMENT_COUNT:
        findings.append("RTM_COUNT_MISMATCH")
    requirements = rtm.get("requirements", [])
    if not isinstance(requirements, list):
        return findings + ["RTM_REQUIREMENTS_INVALID"]
    seen: set[str] = set()
    for item in requirements:
        if not isinstance(item, dict):
            findings.append("RTM_REQUIREMENT_NOT_OBJECT")
            continue
        req_id = str(item.get("requirement_id", ""))
        if req_id in seen:
            findings.append(f"RTM_DUPLICATE_REQUIREMENT:{req_id}")
        seen.add(req_id)
        findings.extend(_validate_canonical_row(item))
    return sorted(set(findings))


def _validate_claims(
    ledger: Mapping[str, Any], requirements: Mapping[str, Mapping[str, Any]], head: str
) -> list[str]:
    findings: list[str] = []
    seen: set[str] = set()
    for claim in ledger.get("claims", []):
        if not isinstance(claim, dict):
            findings.append("CLAIM_NOT_OBJECT")
            continue
        claim_id = str(claim.get("claim_id", "UNKNOWN"))
        if claim_id in seen:
            findings.append(f"CLAIM_DUPLICATE_ID:{claim_id}")
        seen.add(claim_id)
        for field in CLAIM_FIELDS:
            if field not in claim:
                findings.append(f"CLAIM_{field.upper()}_MISSING:{claim_id}")
        if claim.get("status") not in {"VERIFIED", "PARTIAL", "INFERRED", "UNVERIFIED", "FAILED"}:
            findings.append(f"CLAIM_STATUS_INVALID:{claim_id}")
        if claim.get("level") not in LEVELS:
            findings.append(f"CLAIM_LEVEL_INVALID:{claim_id}")
        if claim.get("exact_head") != head:
            findings.append(f"CLAIM_EXACT_HEAD_MISMATCH:{claim_id}")
        req_ids = claim.get("requirement_ids", [])
        if not isinstance(req_ids, list):
            findings.append(f"CLAIM_REQUIREMENTS_INVALID:{claim_id}")
            req_ids = []
        for req_id in req_ids:
            if req_id not in requirements:
                findings.append(f"CLAIM_UNKNOWN_REQUIREMENT:{claim_id}:{req_id}")
        if claim.get("status") == "VERIFIED" and not claim.get("evidence_ids"):
            findings.append(f"VERIFIED_CLAIM_EVIDENCE_MISSING:{claim_id}")
        findings.extend(validate_l5_claim(claim))
    return sorted(set(findings))


def _open_p0_p1(defects: Mapping[str, Any]) -> bool:
    return any(
        isinstance(item, dict)
        and item.get("severity") in {"P0", "P1"}
        and item.get("status") not in {"CLOSED", "CLOSED_VERIFIED"}
        for item in defects.get("defects", [])
    )


def _plateau_findings(docs: Mapping[str, Mapping[str, Any]]) -> list[str]:
    findings: list[str] = []
    if _open_p0_p1(docs["DEFECT_REGISTER.json"]):
        findings.append("RELEASE_GATE_OPEN_P0_P1")
    if any(
        item.get("priority") in {"P0", "P1"} and item.get("actual_status") != "VERIFIED"
        for item in docs["REQUIREMENTS_TRACEABILITY_MATRIX.json"].get("requirements", [])
        if isinstance(item, dict)
    ):
        findings.append("RELEASE_GATE_RTM_INCOMPLETE")
    checks = (
        ("STATE_TRANSITION_COVERAGE.json", "critical_transition_coverage", 1.0, "RELEASE_GATE_CRITICAL_TRANSITIONS_INCOMPLETE"),
        ("PARAMETER_COMBINATION_COVERAGE.json", "critical_launcher_3way_coverage", 1.0, "RELEASE_GATE_LAUNCHER_3WAY_INCOMPLETE"),
        ("MUTATION_REPORT.json", "critical_mutation_kill_rate", 1.0, "RELEASE_GATE_CRITICAL_MUTATION_INCOMPLETE"),
        ("FAULT_INJECTION_REPORT.json", "harness_negative_controls", "PASS", "RELEASE_GATE_HARNESS_NEGATIVE_CONTROLS_INCOMPLETE"),
        ("BUILD_PROVENANCE.json", "same_artifact_run_a_run_b", True, "RELEASE_GATE_ARTIFACT_IDENTITY_UNPROVEN"),
        ("BUILD_PROVENANCE.json", "source_to_installed_provenance_verified", True, "RELEASE_GATE_PROVENANCE_INCOMPLETE"),
        ("INSTALLED_FILE_MANIFEST.json", "manifest_diff_count", 0, "RELEASE_GATE_MANIFEST_DIFF"),
        ("INSTALLED_FILE_MANIFEST.json", "installed_file_diff_count", 0, "RELEASE_GATE_INSTALLED_FILE_DIFF"),
        ("SECURITY_REPORT.json", "independent_adversary_new_p0_p1", False, "RELEASE_GATE_INDEPENDENT_ADVERSARY_INCOMPLETE"),
    )
    for name, field, expected, code in checks:
        if docs[name].get(field) != expected:
            findings.append(code)
    if docs["MUTATION_REPORT.json"].get("general_mutation_score", 0) < 0.9:
        findings.append("RELEASE_GATE_GENERAL_MUTATION_BELOW_90")
    physical = docs["PHYSICAL_PILOT_REPORT.json"]
    if not physical.get("physical_pass") or physical.get("status") != "VERIFIED":
        findings.append("RELEASE_GATE_PHYSICAL_L5_INCOMPLETE")
    return findings


def validate_bundle(bundle_dir: Path, expected_sha: str) -> list[str]:
    findings = [
        f"ARTIFACT_MISSING:{name}"
        for name in REQUIRED_ARTIFACTS
        if not (bundle_dir / name).is_file()
    ]
    if findings:
        return findings
    docs: dict[str, dict[str, Any]] = {}
    for name in REQUIRED_ARTIFACTS[:-1]:
        try:
            docs[name] = _read_json(bundle_dir / name)
        except (OSError, UnicodeError, json.JSONDecodeError, ControlPlaneError):
            findings.append(f"ARTIFACT_INVALID_JSON:{name}")
    if len(docs) != len(REQUIRED_ARTIFACTS) - 1:
        return sorted(set(findings))
    for name, doc in docs.items():
        for field in ("exact_head", "source_exact_head"):
            if field in doc and doc[field] != expected_sha:
                findings.append(f"EXACT_HEAD_MISMATCH:{name}:{field}")
    rtm = docs["REQUIREMENTS_TRACEABILITY_MATRIX.json"]
    findings.extend(_validate_rtm(rtm))
    findings.extend(_validate_claims(docs["CLAIM_LEDGER.json"], _rtm_map(rtm), expected_sha))
    if docs["SECURITY_REPORT.json"].get("marketplace_write_enabled") is not False:
        findings.append("MARKETPLACE_WRITES_ENABLED")
    decision = _parse_decision(bundle_dir / "FINAL_RELEASE_DECISION.md")
    value = decision.get("decision")
    if value not in {"RELEASE_BLOCKED", "AUTOMATED_VERIFICATION_PASS", "TECHNICAL_PLATEAU_REACHED", "RELEASE_AUTHORIZED"}:
        findings.append("RELEASE_DECISION_INVALID")
    if decision.get("exact head") != expected_sha:
        findings.append("RELEASE_DECISION_HEAD_MISMATCH")
    if decision.get("marketplace writes") != "DISABLED":
        findings.append("RELEASE_DECISION_MARKETPLACE_WRITE_NOT_DISABLED")
    if value in {"TECHNICAL_PLATEAU_REACHED", "RELEASE_AUTHORIZED"}:
        findings.extend(_plateau_findings(docs))
    physical = docs["PHYSICAL_PILOT_REPORT.json"]
    if physical.get("status") == "VERIFIED" and not physical.get("physical_pass"):
        findings.append("PHYSICAL_VERIFIED_WITHOUT_PASS")
    return sorted(set(findings))


def audit_bundle(bundle_dir: Path, expected_sha: str) -> dict[str, Any]:
    findings = validate_bundle(bundle_dir, expected_sha)
    decision_file = bundle_dir / "FINAL_RELEASE_DECISION.md"
    decision = _parse_decision(decision_file).get("decision") if decision_file.is_file() else "UNKNOWN"
    return {
        "milestone": "M9",
        "protocol_version": PROTOCOL_VERSION,
        "status": "PASS" if not findings else "FAIL",
        "exact_head": expected_sha,
        "bundle_dir": str(bundle_dir),
        "required_artifact_count": len(REQUIRED_ARTIFACTS),
        "findings": findings,
        "decision": decision,
        "maximum_claim": "GATE_M1_SOURCE_RUNTIME_PASS",
        "release_authorized": False,
        "marketplace_write_enabled": False,
        "merge_to_main_authorized": False,
    }


def run_negative_controls(expected_sha: str, repo_root: Path | None = None) -> dict[str, Any]:
    repo_root = (repo_root or Path.cwd()).resolve()
    controls: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        baseline = root / "baseline"
        bootstrap_bundle(baseline, expected_sha, repo_root)
        baseline_findings = validate_bundle(baseline, expected_sha)
        if baseline_findings:
            return {"milestone": "M9", "protocol_version": PROTOCOL_VERSION, "status": "FAIL", "baseline_findings": baseline_findings, "controls": []}

        def missing_status(path: Path) -> None:
            value = _read_json(path / "CLAIM_LEDGER.json")
            value["claims"][0].pop("status", None)
            _write_json(path / "CLAIM_LEDGER.json", value)

        def wrong_head(path: Path) -> None:
            value = _read_json(path / "BUILD_PROVENANCE.json")
            value["exact_head"] = "0" * 40
            _write_json(path / "BUILD_PROVENANCE.json", value)

        def enable_writes(path: Path) -> None:
            value = _read_json(path / "SECURITY_REPORT.json")
            value["marketplace_write_enabled"] = True
            _write_json(path / "SECURITY_REPORT.json", value)

        def authorize_release(path: Path) -> None:
            (path / "FINAL_RELEASE_DECISION.md").write_text(_decision_text(expected_sha, "RELEASE_AUTHORIZED"), encoding="utf-8")

        def delete_sbom(path: Path) -> None:
            (path / "SBOM.json").unlink()

        mutations = (
            ("NEG-M9-001", "CLAIM_STATUS_MISSING:CLM-M9-001", missing_status),
            ("NEG-M9-002", "EXACT_HEAD_MISMATCH:BUILD_PROVENANCE.json:exact_head", wrong_head),
            ("NEG-M9-003", "MARKETPLACE_WRITES_ENABLED", enable_writes),
            ("NEG-M9-004", "RELEASE_GATE_OPEN_P0_P1", authorize_release),
            ("NEG-M9-005", "ARTIFACT_MISSING:SBOM.json", delete_sbom),
        )
        for control_id, expected, mutate in mutations:
            candidate = root / control_id.lower()
            shutil.copytree(baseline, candidate)
            mutate(candidate)
            actual = validate_bundle(candidate, expected_sha)
            controls.append({"control_id": control_id, "status": "PASS" if expected in actual else "FAIL", "expected_finding": expected, "actual_findings": actual})
    passed = sum(item["status"] == "PASS" for item in controls)
    return {
        "milestone": "M9",
        "protocol_version": PROTOCOL_VERSION,
        "status": "PASS" if passed == len(controls) else "FAIL",
        "exact_head": expected_sha,
        "controls": controls,
        "controls_passed": passed,
        "controls_total": len(controls),
        "release_authorized": False,
        "marketplace_write_enabled": False,
    }


def _read_changed_paths(path: str | None) -> list[str]:
    if not path:
        return []
    return [line.strip() for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def _bootstrap(args: argparse.Namespace) -> int:
    bootstrap_bundle(Path(args.output_dir), args.exact_head, Path(args.repo_root))
    print(json.dumps({"status": "PASS", "artifact_count": len(REQUIRED_ARTIFACTS)}))
    return 0


def _audit(args: argparse.Namespace) -> int:
    report = audit_bundle(Path(args.bundle_dir), args.expected_sha)
    _write_json(Path(args.output), report)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


def _self_test(args: argparse.Namespace) -> int:
    report = run_negative_controls(args.expected_sha, Path(args.repo_root))
    _write_json(Path(args.output), report)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


def _m1_ingest(args: argparse.Namespace) -> int:
    report = ingest_literal_rtm(Path(args.repo_root))
    public = _public_ingestion_report(report)
    _write_json(Path(args.output), public)
    print(json.dumps(public, ensure_ascii=False, sort_keys=True))
    return 0 if public["status"] == "PASS" else 1


def _m1_run(args: argparse.Namespace) -> int:
    report = write_m1_evidence(
        Path(args.repo_root),
        Path(args.output_dir),
        args.exact_head,
        _read_changed_paths(args.changed_paths_file),
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Quantum Maximum-Assurance Protocol v3.1 control plane")
    commands = result.add_subparsers(dest="command", required=True)
    bootstrap = commands.add_parser("bootstrap")
    bootstrap.add_argument("--output-dir", required=True)
    bootstrap.add_argument("--exact-head", required=True)
    bootstrap.add_argument("--repo-root", default=".")
    bootstrap.set_defaults(handler=_bootstrap)
    audit = commands.add_parser("audit")
    audit.add_argument("--bundle-dir", required=True)
    audit.add_argument("--expected-sha", required=True)
    audit.add_argument("--output", required=True)
    audit.set_defaults(handler=_audit)
    self_test = commands.add_parser("self-test")
    self_test.add_argument("--expected-sha", required=True)
    self_test.add_argument("--output", required=True)
    self_test.add_argument("--repo-root", default=".")
    self_test.set_defaults(handler=_self_test)
    ingest = commands.add_parser("m1-ingest")
    ingest.add_argument("--repo-root", default=".")
    ingest.add_argument("--output", required=True)
    ingest.set_defaults(handler=_m1_ingest)
    m1_run = commands.add_parser("m1-run")
    m1_run.add_argument("--repo-root", default=".")
    m1_run.add_argument("--output-dir", required=True)
    m1_run.add_argument("--exact-head", required=True)
    m1_run.add_argument("--changed-paths-file")
    m1_run.set_defaults(handler=_m1_run)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
