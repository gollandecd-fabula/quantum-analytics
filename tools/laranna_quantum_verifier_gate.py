#!/usr/bin/env python3
"""Fail-closed repository gate for Windows-signed LarannA Quantum changes."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


PROJECT_ID = "quantum"
REPOSITORY = "gollandecd-fabula/quantum-analytics"
BRANCH = "fix/quantum-pilot-v3-canonical"
CONTROLLER_PATH = "tools/m9_maximum_assurance_control_plane.py"
TRUSTED_KEY_ID = "49f2c8f2b18deae2"
TRUSTED_PUBLIC_KEY_SHA256 = (
    "49f2c8f2b18deae24882de345a0f83db99d0f143fcfc8bd138a72f4f7910d1ec"
)
SIGNATURE_ALGORITHM = "Ed25519"
AUTHORIZATION_PATHS = (
    "docs/evidence/laranna_quantum/bootstrap/BOOTSTRAP_CHANGE_PERMIT.json",
    "docs/evidence/laranna_quantum/bootstrap/BOOTSTRAP_CHANGE_REQUEST.json",
    "docs/evidence/laranna_quantum/bootstrap/BOOTSTRAP_WORK_ORDER.json",
    "docs/evidence/laranna_quantum/bootstrap/QUANTUM_PUBLIC_KEY_BINDING.json",
)
RESULT_PATH = "docs/evidence/laranna_quantum/bootstrap/BOOTSTRAP_RESULT.json"
RECEIPT_PATH = "docs/evidence/laranna_quantum/bootstrap/VERIFIER_RECEIPT.json"

REQUEST_FIELDS = {
    "schema",
    "request_id",
    "project_id",
    "campaign_id",
    "repo",
    "branch",
    "base_head",
    "risk_class",
    "action",
    "action_hash",
    "test",
    "rollback",
    "expires_utc",
    "work_order_id",
    "work_order_sha256",
    "protocol_sha256",
    "allowed_paths",
    "expected_result",
}
PERMIT_FIELDS = {
    "schema",
    "project_id",
    "request_id",
    "campaign_id",
    "repo",
    "branch",
    "base_head",
    "risk_class",
    "work_order_id",
    "work_order_sha256",
    "protocol_sha256",
    "allowed_paths",
    "allowed_paths_sha256",
    "action_hash",
    "request_hash",
    "policy_digest",
    "nonce",
    "issued_utc",
    "expires_utc",
    "evidence_ceiling",
    "release_authorized",
    "signature_algorithm",
    "key_id",
    "signature",
}
BINDING_FIELDS = {
    "schema",
    "project_id",
    "campaign_id",
    "repo",
    "branch",
    "policy_digest",
    "public_key_b64",
    "public_key_sha256",
    "issued_utc",
    "release_authorized",
    "signature_algorithm",
    "key_id",
    "signature",
}
RESULT_FIELDS = {
    "schema",
    "project_id",
    "request_id",
    "permit_nonce",
    "base_head",
    "result_head",
    "work_order_sha256",
    "diff_sha256",
    "test_results",
    "evidence_level",
    "release_requested",
}
RECEIPT_FIELDS = {
    "schema",
    "project_id",
    "request_id",
    "campaign_id",
    "repo",
    "branch",
    "base_head",
    "result_head",
    "work_order_id",
    "work_order_sha256",
    "protocol_sha256",
    "allowed_paths_sha256",
    "action_hash",
    "diff_sha256",
    "test_evidence_digest",
    "evidence_level",
    "policy_digest",
    "permit_nonce_hash",
    "issued_utc",
    "release_authorized",
    "signature_algorithm",
    "key_id",
    "signature",
}


class GateError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_value(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def parse_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise GateError("TIME_INVALID", "Timestamp must be a string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GateError("TIME_INVALID", "Timestamp is not RFC3339") from exc
    if parsed.tzinfo is None:
        raise GateError("TIME_INVALID", "Timestamp has no timezone")
    return parsed.astimezone(timezone.utc)


def require_sha(value: Any, field: str, length: int = 64) -> str:
    rendered = str(value)
    if not re.fullmatch(rf"[0-9a-f]{{{length}}}", rendered):
        raise GateError("DIGEST_INVALID", f"{field} is not a lowercase SHA value")
    return rendered


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError("JSON_INVALID", f"Cannot load {path}") from exc
    if not isinstance(value, dict):
        raise GateError("JSON_INVALID", f"{path} is not a JSON object")
    return value


def normalize_paths(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        raise GateError("PATH_SCOPE_INVALID", "Allowed paths are empty")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item or "\\" in item or "\0" in item:
            raise GateError("PATH_SCOPE_INVALID", "Allowed path is invalid")
        candidate = PurePosixPath(item)
        if candidate.is_absolute() or candidate.as_posix() != item:
            raise GateError("PATH_SCOPE_INVALID", "Allowed path is not canonical")
        if any(part in {"", ".", ".."} for part in candidate.parts):
            raise GateError("PATH_SCOPE_INVALID", "Allowed path escapes repository scope")
        lowered = item.casefold()
        if lowered == ".git" or lowered.startswith(".git/") or "imagelab" in lowered:
            raise GateError("CROSS_PROJECT_SCOPE", "ImageLab or Git internals entered Quantum scope")
        result.append(item)
    if result != sorted(set(result)):
        raise GateError("PATH_SCOPE_INVALID", "Allowed paths are not sorted and unique")
    return result


def action_hash(request: Mapping[str, Any]) -> str:
    return sha256_value(
        {
            "project_id": request.get("project_id"),
            "campaign_id": request.get("campaign_id"),
            "repo": request.get("repo"),
            "branch": request.get("branch"),
            "base_head": request.get("base_head"),
            "risk_class": request.get("risk_class"),
            "work_order_id": request.get("work_order_id"),
            "work_order_sha256": request.get("work_order_sha256"),
            "protocol_sha256": request.get("protocol_sha256"),
            "allowed_paths": request.get("allowed_paths"),
            "action": request.get("action"),
            "test": request.get("test"),
            "expected_result": request.get("expected_result"),
            "rollback": request.get("rollback"),
        }
    )


def verify_ed25519(value: Mapping[str, Any], public_key_raw: bytes) -> None:
    unsigned = dict(value)
    encoded = unsigned.pop("signature", None)
    if unsigned.get("signature_algorithm") != SIGNATURE_ALGORITHM:
        raise GateError("SIGNATURE_INVALID", "Signature algorithm is not Ed25519")
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )
    except ModuleNotFoundError as exc:
        raise GateError(
            "CRYPTO_RUNTIME_MISSING",
            "Install requirements/laranna-quantum-verifier.txt with hashes",
        ) from exc
    try:
        signature = base64.b64decode(str(encoded), validate=True)
        Ed25519PublicKey.from_public_bytes(public_key_raw).verify(
            signature,
            canonical_json(unsigned).encode("utf-8"),
        )
    except (ValueError, InvalidSignature) as exc:
        raise GateError("SIGNATURE_INVALID", "Ed25519 signature verification failed") from exc


@dataclass(frozen=True)
class Authorization:
    binding: dict[str, Any]
    work_order: dict[str, Any]
    request: dict[str, Any]
    permit: dict[str, Any]
    public_key_raw: bytes

    @property
    def base_head(self) -> str:
        return str(self.request["base_head"])


def _require_exact_fields(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise GateError("FIELDS_INVALID", f"{label} fields are not exact")


def validate_documents(
    binding: dict[str, Any],
    work_order: dict[str, Any],
    request: dict[str, Any],
    permit: dict[str, Any],
    *,
    enforce_unexpired: bool,
) -> Authorization:
    _require_exact_fields(binding, BINDING_FIELDS, "Public-key binding")
    _require_exact_fields(request, REQUEST_FIELDS, "Change request")
    _require_exact_fields(permit, PERMIT_FIELDS, "Change permit")
    if (
        binding.get("schema") != "laranna.quantum.public-key-binding.v1"
        or request.get("schema") != "laranna.quantum.change-request.v2"
        or permit.get("schema") != "laranna.quantum.change-permit.v2"
    ):
        raise GateError("SCHEMA_INVALID", "Authorization schema is invalid")
    if any(
        value.get("project_id") != PROJECT_ID
        for value in (binding, work_order, request, permit)
    ):
        raise GateError("PROJECT_MISMATCH", "Authorization is not Quantum-only")

    try:
        public_key_raw = base64.b64decode(str(binding["public_key_b64"]), validate=True)
    except (KeyError, ValueError) as exc:
        raise GateError("PUBLIC_KEY_INVALID", "Public key is invalid") from exc
    if len(public_key_raw) != 32:
        raise GateError("PUBLIC_KEY_INVALID", "Ed25519 public key length is invalid")
    public_digest = sha256_bytes(public_key_raw)
    if (
        public_digest != TRUSTED_PUBLIC_KEY_SHA256
        or binding.get("public_key_sha256") != public_digest
        or binding.get("key_id") != TRUSTED_KEY_ID
        or permit.get("key_id") != TRUSTED_KEY_ID
    ):
        raise GateError("PUBLIC_KEY_UNTRUSTED", "Quantum public key is not pinned")
    verify_ed25519(binding, public_key_raw)
    verify_ed25519(permit, public_key_raw)

    unsigned_work_order = dict(work_order)
    stated_work_order_digest = unsigned_work_order.pop("work_order_sha256", None)
    if stated_work_order_digest != sha256_value(unsigned_work_order):
        raise GateError("WORK_ORDER_DIGEST_INVALID", "Work-order digest does not match")
    require_sha(stated_work_order_digest, "work_order_sha256")
    allowed = normalize_paths(work_order.get("files_allowed_to_change"))
    if request.get("allowed_paths") != allowed or permit.get("allowed_paths") != allowed:
        raise GateError("PATH_SCOPE_MISMATCH", "Signed path scope does not match work order")
    if permit.get("allowed_paths_sha256") != sha256_value(allowed):
        raise GateError("PATH_SCOPE_MISMATCH", "Allowed-path digest does not match")
    if request.get("action_hash") != action_hash(request):
        raise GateError("ACTION_HASH_INVALID", "Action hash does not match request")
    if permit.get("request_hash") != sha256_value(request):
        raise GateError("REQUEST_HASH_INVALID", "Permit request hash does not match")

    common = {
        "campaign_id": request.get("campaign_id"),
        "repo": request.get("repo"),
        "branch": request.get("branch"),
        "base_head": request.get("base_head"),
        "risk_class": request.get("risk_class"),
        "work_order_id": request.get("work_order_id"),
        "work_order_sha256": request.get("work_order_sha256"),
        "protocol_sha256": request.get("protocol_sha256"),
        "action_hash": request.get("action_hash"),
        "expires_utc": request.get("expires_utc"),
    }
    for field, expected in common.items():
        if permit.get(field) != expected:
            raise GateError("PERMIT_BINDING_MISMATCH", f"Permit {field} does not match")
    if (
        request.get("work_order_id") != work_order.get("work_order_id")
        or request.get("work_order_sha256") != stated_work_order_digest
        or request.get("base_head") != work_order.get("exact_head")
        or request.get("protocol_sha256") != work_order.get("protocol_sha256")
    ):
        raise GateError("WORK_ORDER_BINDING_MISMATCH", "Request is not bound to work order")
    for field in ("action", "test", "rollback", "expected_result"):
        if request.get(field) != work_order.get(field):
            raise GateError("WORK_ORDER_BINDING_MISMATCH", f"Request {field} does not match")
    if (
        request.get("repo") != REPOSITORY
        or request.get("branch") != BRANCH
        or work_order.get("repo") != REPOSITORY
        or work_order.get("branch") != BRANCH
        or binding.get("repo") != REPOSITORY
        or binding.get("branch") != BRANCH
        or work_order.get("controller_path") != CONTROLLER_PATH
    ):
        raise GateError("REPOSITORY_SCOPE_MISMATCH", "Repository or M9 scope does not match")
    if binding.get("campaign_id") != request.get("campaign_id"):
        raise GateError("CAMPAIGN_MISMATCH", "Public key binding campaign does not match")
    if (
        binding.get("policy_digest") != permit.get("policy_digest")
        or permit.get("policy_digest") is None
    ):
        raise GateError("POLICY_MISMATCH", "Policy digest does not match")
    if permit.get("evidence_ceiling") != work_order.get("target_evidence_level"):
        raise GateError("EVIDENCE_SCOPE_MISMATCH", "Evidence ceiling does not match")

    authorization_paths = tuple(work_order.get("authorization_commit_paths", ()))
    implementation_paths = tuple(work_order.get("implementation_commit_paths", ()))
    receipt_paths = tuple(work_order.get("receipt_commit_paths", ()))
    if authorization_paths != AUTHORIZATION_PATHS:
        raise GateError("AUTHORIZATION_PATHS_INVALID", "Authorization commit paths changed")
    for group in (authorization_paths, implementation_paths, receipt_paths):
        if list(group) != sorted(set(group)) or not set(group).issubset(allowed):
            raise GateError("COMMIT_SCOPE_INVALID", "Commit path group is invalid")
    if RESULT_PATH not in receipt_paths or RECEIPT_PATH not in receipt_paths:
        raise GateError("RECEIPT_SCOPE_INVALID", "Final receipt paths are incomplete")
    if CONTROLLER_PATH not in work_order.get("files_forbidden_to_change", ()):
        raise GateError("M9_BOUNDARY_INVALID", "M9 controller is not protected")
    for field in (
        "product_change_authorized",
        "m9_authority_change_authorized",
        "github_ruleset_change_authorized",
        "merge_authorized",
        "release_authorized",
    ):
        if work_order.get(field) is not False:
            raise GateError("BOOTSTRAP_AUTHORITY_ESCALATION", f"{field} must remain false")
    if binding.get("release_authorized") is not False or permit.get(
        "release_authorized"
    ) is not False:
        raise GateError("RELEASE_AUTHORITY_ESCALATION", "Bootstrap cannot authorize release")
    require_sha(request.get("base_head"), "base_head", 40)
    require_sha(request.get("protocol_sha256"), "protocol_sha256")
    issued = parse_time(permit.get("issued_utc"))
    expires = parse_time(permit.get("expires_utc"))
    if issued >= expires:
        raise GateError("PERMIT_TIME_INVALID", "Permit expires before it is issued")
    if enforce_unexpired and expires <= datetime.now(timezone.utc):
        raise GateError("PERMIT_EXPIRED", "Bootstrap permit has expired")
    return Authorization(binding, work_order, request, permit, public_key_raw)


def run_git(root: Path, *arguments: str, binary: bool = False) -> str | bytes:
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=False,
        capture_output=True,
        text=not binary,
    )
    if result.returncode != 0:
        stderr = result.stderr if isinstance(result.stderr, str) else result.stderr.decode()
        raise GateError("GIT_FAILED", stderr.strip() or "git command failed")
    return result.stdout


def resolve_commit(root: Path, revision: str) -> str:
    value = str(run_git(root, "rev-parse", "--verify", f"{revision}^{{commit}}"))
    resolved = value.strip()
    require_sha(resolved, "git commit", 40)
    return resolved


def changed_paths(root: Path, older: str, newer: str) -> tuple[str, ...]:
    raw = run_git(
        root,
        "diff",
        "--name-only",
        "--no-renames",
        "-z",
        older,
        newer,
        binary=True,
    )
    assert isinstance(raw, bytes)
    paths = tuple(sorted(part.decode("utf-8") for part in raw.split(b"\0") if part))
    if paths != tuple(sorted(set(paths))):
        raise GateError("DIFF_PATH_INVALID", "Git diff paths are not unique")
    return paths


def _commit_parent(root: Path, commit: str) -> str:
    line = str(run_git(root, "rev-list", "--parents", "-n", "1", commit)).strip()
    parts = line.split()
    if len(parts) != 2:
        raise GateError("TOPOLOGY_INVALID", "Transaction commits must have one parent")
    return parts[1]


@dataclass(frozen=True)
class Topology:
    base_head: str
    authorization_head: str
    implementation_head: str | None
    final_head: str | None


def validate_topology(
    root: Path,
    authorization: Authorization,
    head: str,
    phase: str,
) -> Topology:
    base = resolve_commit(root, authorization.base_head)
    resolved_head = resolve_commit(root, head)
    chain_text = str(
        run_git(root, "rev-list", "--first-parent", "--reverse", f"{base}..{resolved_head}")
    )
    chain = [line for line in chain_text.splitlines() if line]
    expected_count = {"authorization": 1, "implementation": 2, "final": 3}[phase]
    if len(chain) != expected_count:
        raise GateError("TOPOLOGY_INVALID", f"{phase} phase requires {expected_count} commits")
    all_count = int(str(run_git(root, "rev-list", "--count", f"{base}..{resolved_head}")).strip())
    if all_count != expected_count:
        raise GateError("TOPOLOGY_INVALID", "Side commits or merges entered transaction")
    expected_parent = base
    for commit in chain:
        if _commit_parent(root, commit) != expected_parent:
            raise GateError("TOPOLOGY_INVALID", "Commit parent is not exact")
        expected_parent = commit

    work_order = authorization.work_order
    expected_groups = [
        tuple(work_order["authorization_commit_paths"]),
        tuple(work_order["implementation_commit_paths"]),
        tuple(work_order["receipt_commit_paths"]),
    ]
    previous = base
    for index, commit in enumerate(chain):
        actual = changed_paths(root, previous, commit)
        if actual != expected_groups[index]:
            raise GateError(
                "COMMIT_SCOPE_MISMATCH",
                f"Commit {index + 1} changed {actual}, expected {expected_groups[index]}",
            )
        previous = commit
    all_paths = changed_paths(root, base, resolved_head)
    if not set(all_paths).issubset(set(work_order["files_allowed_to_change"])):
        raise GateError("PATH_SCOPE_MISMATCH", "Transaction changed a path outside permit")
    return Topology(
        base,
        chain[0],
        chain[1] if len(chain) > 1 else None,
        chain[2] if len(chain) > 2 else None,
    )


def diff_rows(root: Path, base: str, head: str) -> list[dict[str, Any]]:
    output = str(run_git(root, "diff", "--name-status", "--no-renames", base, head))
    rows: list[dict[str, Any]] = []
    for line in output.splitlines():
        status, path = line.split("\t", 1)
        status = status[:1]
        if status == "D":
            raw = b""
            digest: str | None = None
        else:
            raw_value = run_git(root, "show", f"{head}:{path}", binary=True)
            assert isinstance(raw_value, bytes)
            raw = raw_value
            digest = sha256_bytes(raw)
        rows.append(
            {
                "path": path,
                "status": status,
                "sha256": digest,
                "size_bytes": len(raw),
            }
        )
    return sorted(rows, key=lambda item: item["path"])


def diff_digest(root: Path, base: str, head: str) -> str:
    return sha256_value(diff_rows(root, base, head))


def load_authorization(root: Path, *, enforce_unexpired: bool) -> Authorization:
    base = root / "docs/evidence/laranna_quantum/bootstrap"
    return validate_documents(
        load_json(base / "QUANTUM_PUBLIC_KEY_BINDING.json"),
        load_json(base / "BOOTSTRAP_WORK_ORDER.json"),
        load_json(base / "BOOTSTRAP_CHANGE_REQUEST.json"),
        load_json(base / "BOOTSTRAP_CHANGE_PERMIT.json"),
        enforce_unexpired=enforce_unexpired,
    )


def validate_final_evidence(
    root: Path,
    authorization: Authorization,
    topology: Topology,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if topology.implementation_head is None or topology.final_head is None:
        raise GateError("FINAL_TOPOLOGY_INVALID", "Final topology is incomplete")
    result = load_json(root / RESULT_PATH)
    receipt = load_json(root / RECEIPT_PATH)
    _require_exact_fields(result, RESULT_FIELDS, "Change result")
    _require_exact_fields(receipt, RECEIPT_FIELDS, "Verifier receipt")
    request = authorization.request
    permit = authorization.permit
    expected_diff = diff_digest(root, topology.base_head, topology.implementation_head)
    if (
        result.get("schema") != "laranna.quantum.change-result.v2"
        or result.get("project_id") != PROJECT_ID
        or result.get("request_id") != request["request_id"]
        or result.get("permit_nonce") != permit["nonce"]
        or result.get("base_head") != topology.base_head
        or result.get("result_head") != topology.implementation_head
        or result.get("work_order_sha256") != request["work_order_sha256"]
        or result.get("diff_sha256") != expected_diff
        or result.get("evidence_level") != "L2"
        or result.get("release_requested") is not False
    ):
        raise GateError("RESULT_BINDING_MISMATCH", "Change result does not match exact diff")
    tests = result.get("test_results")
    if not isinstance(tests, list) or not tests:
        raise GateError("TEST_EVIDENCE_MISSING", "Result has no mandatory test evidence")
    for test in tests:
        if (
            not isinstance(test, dict)
            or set(test) != {"id", "status", "evidence_sha256"}
            or test.get("status") != "PASS"
            or not isinstance(test.get("id"), str)
            or not test["id"].strip()
        ):
            raise GateError("TEST_EVIDENCE_INVALID", "Mandatory test evidence is invalid")
        require_sha(test.get("evidence_sha256"), "test evidence")

    verify_ed25519(receipt, authorization.public_key_raw)
    expected_receipt = {
        "project_id": PROJECT_ID,
        "request_id": request["request_id"],
        "campaign_id": request["campaign_id"],
        "repo": request["repo"],
        "branch": request["branch"],
        "base_head": topology.base_head,
        "result_head": topology.implementation_head,
        "work_order_id": request["work_order_id"],
        "work_order_sha256": request["work_order_sha256"],
        "protocol_sha256": request["protocol_sha256"],
        "allowed_paths_sha256": permit["allowed_paths_sha256"],
        "action_hash": request["action_hash"],
        "diff_sha256": expected_diff,
        "test_evidence_digest": sha256_value(tests),
        "evidence_level": "L2",
        "policy_digest": permit["policy_digest"],
        "permit_nonce_hash": sha256_bytes(str(permit["nonce"]).encode("utf-8")),
        "release_authorized": False,
        "key_id": TRUSTED_KEY_ID,
        "signature_algorithm": SIGNATURE_ALGORITHM,
    }
    if receipt.get("schema") != "laranna.quantum.verifier-receipt.v2":
        raise GateError("RECEIPT_SCHEMA_INVALID", "Receipt schema is invalid")
    for field, expected in expected_receipt.items():
        if receipt.get(field) != expected:
            raise GateError("RECEIPT_BINDING_MISMATCH", f"Receipt {field} does not match")
    if parse_time(receipt.get("issued_utc")) > parse_time(permit.get("expires_utc")):
        raise GateError("RECEIPT_TIME_INVALID", "Receipt was issued after permit expiry")
    return result, receipt


def _require_clean_worktree(root: Path) -> None:
    if str(run_git(root, "status", "--porcelain=v1", "--untracked-files=all")).strip():
        raise GateError("WORKTREE_DIRTY", "Preflight requires a clean worktree")


def execute(root: Path, command: str, head: str) -> dict[str, Any]:
    phase = {
        "preflight": "authorization",
        "verify-implementation": "implementation",
        "verify-final": "final",
        "verify-release": "final",
        "diff-digest": "implementation",
    }[command]
    authorization = load_authorization(
        root,
        enforce_unexpired=command in {"preflight", "verify-implementation", "diff-digest"},
    )
    topology = validate_topology(root, authorization, head, phase)
    if command == "preflight":
        _require_clean_worktree(root)
    result: dict[str, Any] = {
        "schema": "laranna.quantum.repository-gate-verdict.v1",
        "status": "VERIFIED",
        "phase": phase,
        "project_id": PROJECT_ID,
        "base_head": topology.base_head,
        "authorization_head": topology.authorization_head,
        "implementation_head": topology.implementation_head,
        "final_head": topology.final_head,
        "work_order_id": authorization.work_order["work_order_id"],
        "work_order_sha256": authorization.work_order["work_order_sha256"],
        "release_authorized": False,
    }
    if topology.implementation_head is not None:
        result["diff_sha256"] = diff_digest(
            root,
            topology.base_head,
            topology.implementation_head,
        )
    if command in {"verify-final", "verify-release"}:
        change_result, receipt = validate_final_evidence(root, authorization, topology)
        result["test_evidence_digest"] = receipt["test_evidence_digest"]
        result["result_evidence_level"] = change_result["evidence_level"]
        if command == "verify-release":
            raise GateError(
                "RELEASE_AUTHORIZATION_REQUIRED",
                "Normal Quantum receipt cannot authorize a release",
            )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "preflight",
            "verify-implementation",
            "verify-final",
            "verify-release",
            "diff-digest",
        ),
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--head", default="HEAD")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    try:
        verdict = execute(root, args.command, args.head)
    except GateError as exc:
        print(f"LARANNA_QUANTUM_GATE_DENY:{exc.code}:{exc}", file=sys.stderr)
        return 2
    print(json.dumps(verdict, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
