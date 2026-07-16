from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

LEVELS = ("L0", "L1", "L2", "L3", "L4", "L5")
STATUSES = {"VERIFIED", "PARTIAL", "INFERRED", "UNVERIFIED", "FAILED"}
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


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(path.name)
    return value


def _decision_text(head: str, decision: str = "RELEASE_BLOCKED") -> str:
    return (
        "# Quantum Final Release Decision\n\n"
        f"Decision: {decision}\n"
        "Maximum claim: AUTOMATED_VERIFICATION_PASS\n"
        f"Exact head: {head}\n"
        "Marketplace writes: DISABLED\n"
        "Merge to main: NOT_AUTHORIZED\n"
        "Production release: NOT_AUTHORIZED\n\n"
        "Reason: same-artifact RUN A/RUN B, installed provenance, independent "
        "adversarial verification and the physical L5 user path remain open.\n"
    )


def _req(
    req_id: str,
    title: str,
    risk: str,
    *,
    user_visible: bool = False,
    physical: bool = False,
) -> dict[str, Any]:
    return {
        "requirement_id": req_id,
        "title": title,
        "risk": risk,
        "user_visible": user_visible,
        "states": ["S13_DEGRADED", "S14_FAILED"],
        "transitions": [f"TR-{req_id}"],
        "positive_tests": [f"TST-{req_id}"],
        "negative_controls": [f"NEG-{req_id}"],
        "critical_mutations": [f"MUT-{req_id}"],
        "runs": ["RUN-M9-SOURCE"],
        "artifact_checks": [f"CHK-{req_id}"],
        "physical_checks": [f"PHY-{req_id}-PENDING"] if physical else [],
        "coverage_status": "PARTIAL",
        "residual_risk": "Higher evidence levels remain open.",
    }


def _claim(
    claim_id: str,
    text: str,
    status: str,
    level: str,
    req_ids: list[str],
    head: str,
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
        "entry_point": None,
        "actual_command_line": None,
        "environment_id": None,
        "evidence_ids": [],
        "falsification_attempts": [],
        "limitations": ["No installed or physical path is claimed by M9."],
    }


def bootstrap_bundle(output_dir: Path, exact_head: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    common = {"protocol_version": "3.0", "exact_head": exact_head}
    payloads: dict[str, dict[str, Any]] = {
        "REQUIREMENTS_TRACEABILITY_MATRIX.json": {
            **common,
            "requirements": [
                _req("REQ-M9-001", "Fail-closed claim integrity", "P0"),
                _req(
                    "REQ-M9-002",
                    "Release and plateau gate integrity",
                    "P0",
                    user_visible=True,
                    physical=True,
                ),
                _req("REQ-M9-003", "Mandatory assurance artifact set", "P1"),
            ],
        },
        "CLAIM_LEDGER.json": {
            **common,
            "claims": [
                _claim(
                    "CLM-M9-001",
                    "The M9 assurance bundle is structurally auditable.",
                    "PARTIAL",
                    "L2",
                    ["REQ-M9-001", "REQ-M9-003"],
                    exact_head,
                ),
                _claim(
                    "CLM-M9-002",
                    "Quantum is authorized for production release.",
                    "UNVERIFIED",
                    "L0",
                    ["REQ-M9-002"],
                    exact_head,
                ),
            ],
        },
        "DEFECT_REGISTER.json": {
            **common,
            "defects": [
                {
                    "defect_id": "M9-D001",
                    "severity": "P0",
                    "status": "OPEN",
                    "title": "Physical same-artifact L5 path is unverified",
                },
                {
                    "defect_id": "M9-D002",
                    "severity": "P1",
                    "status": "OPEN",
                    "title": "Independent adversarial RUN B is unbound",
                },
            ],
        },
        "STATE_TRANSITION_COVERAGE.json": {
            **common,
            "critical_transition_coverage": 0.0,
            "covered_transitions": [],
            "uncovered_transitions": ["INSTALL", "UPDATE_ROLLBACK", "RECOVERY"],
            "status": "PARTIAL",
        },
        "PARAMETER_COMBINATION_COVERAGE.json": {
            **common,
            "critical_launcher_3way_coverage": 0.0,
            "pairwise_coverage": 0.0,
            "historical_combinations_preserved": True,
            "status": "PARTIAL",
        },
        "MUTATION_REPORT.json": {
            **common,
            "critical_mutation_kill_rate": 0.0,
            "general_mutation_score": 0.0,
            "status": "UNVERIFIED",
        },
        "FUZZ_CORPUS_INDEX.json": {
            **common,
            "corpus": [],
            "crash_seeds": [],
            "corpus_retained": True,
            "status": "UNVERIFIED",
        },
        "FAULT_INJECTION_REPORT.json": {
            **common,
            "harness_negative_controls": "PENDING",
            "controls": [],
            "status": "PARTIAL",
        },
        "SECURITY_REPORT.json": {
            **common,
            "marketplace_write_enabled": False,
            "independent_adversary_new_p0_p1": None,
            "supply_chain_pinned": False,
            "status": "PARTIAL",
        },
        "SBOM.json": {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "exact_head": exact_head,
            "components": [],
            "status": "UNVERIFIED",
        },
        "LICENSE_REPORT.json": {
            **common,
            "dependencies_reviewed": [],
            "status": "UNVERIFIED",
        },
        "BUILD_PROVENANCE.json": {
            **common,
            "source_exact_head": exact_head,
            "artifact_sha256": None,
            "run_a_artifact_sha256": None,
            "run_b_artifact_sha256": None,
            "same_artifact_run_a_run_b": False,
            "source_to_installed_provenance_verified": False,
            "status": "PARTIAL",
        },
        "INSTALLED_FILE_MANIFEST.json": {
            **common,
            "artifact_sha256": None,
            "installed_root": None,
            "files": [],
            "manifest_diff_count": None,
            "installed_file_diff_count": None,
            "status": "UNVERIFIED",
        },
        "PHYSICAL_PILOT_REPORT.json": {
            **common,
            "level": "L5",
            "physical_pass": False,
            "entry_point": None,
            "actual_command_line": None,
            "artifact_sha256": None,
            "status": "UNVERIFIED",
        },
        "RESIDUAL_RISK_REGISTER.json": {
            **common,
            "risks": [
                {
                    "risk_id": "RSK-M9-001",
                    "severity": "P0",
                    "status": "OPEN",
                    "description": "No physical L5 pilot on the exact artifact.",
                },
                {
                    "risk_id": "RSK-M9-002",
                    "severity": "P1",
                    "status": "OPEN",
                    "description": "Coverage and adversarial gates are incomplete.",
                },
            ],
        },
    }
    for name, payload in payloads.items():
        _write_json(output_dir / name, payload)
    (output_dir / "FINAL_RELEASE_DECISION.md").write_text(
        _decision_text(exact_head), encoding="utf-8"
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
        str(item["requirement_id"]): item
        for item in rtm.get("requirements", [])
        if isinstance(item, dict) and item.get("requirement_id")
    }


def _validate_rtm(rtm: Mapping[str, Any]) -> list[str]:
    findings: list[str] = []
    seen: set[str] = set()
    for item in rtm.get("requirements", []):
        if not isinstance(item, dict):
            findings.append("RTM_REQUIREMENT_NOT_OBJECT")
            continue
        req_id = str(item.get("requirement_id", ""))
        if not req_id:
            findings.append("RTM_REQUIREMENT_ID_MISSING")
            continue
        if req_id in seen:
            findings.append(f"RTM_DUPLICATE_REQUIREMENT:{req_id}")
        seen.add(req_id)
        if item.get("risk") not in {"P0", "P1", "P2", "P3"}:
            findings.append(f"RTM_INVALID_RISK:{req_id}")
            continue
        if item.get("risk") in {"P0", "P1"}:
            for field in (
                "positive_tests",
                "negative_controls",
                "critical_mutations",
                "artifact_checks",
            ):
                if not item.get(field):
                    findings.append(f"RTM_P0_P1_COVERAGE_MISSING:{req_id}:{field}")
            if item.get("user_visible") and not item.get("physical_checks"):
                findings.append(f"RTM_PHYSICAL_CHECK_MISSING:{req_id}")
    return findings


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
        if claim.get("status") not in STATUSES:
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
        if claim.get("status") == "VERIFIED":
            if not claim.get("test_ids"):
                findings.append(f"VERIFIED_CLAIM_TESTS_MISSING:{claim_id}")
            if not claim.get("evidence_ids"):
                findings.append(f"VERIFIED_CLAIM_EVIDENCE_MISSING:{claim_id}")
            for req_id in req_ids:
                req = requirements.get(str(req_id), {})
                if req.get("risk") == "P0" and req.get("user_visible"):
                    if claim.get("level") != "L5":
                        findings.append(f"USER_P0_CLAIM_BELOW_L5:{claim_id}")
    return findings


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
        item.get("risk") in {"P0", "P1"} and item.get("coverage_status") != "COMPLETE"
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
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
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
    if value not in {
        "RELEASE_BLOCKED",
        "AUTOMATED_VERIFICATION_PASS",
        "TECHNICAL_PLATEAU_REACHED",
        "RELEASE_AUTHORIZED",
    }:
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
        "protocol_version": "3.0",
        "status": "PASS" if not findings else "FAIL",
        "exact_head": expected_sha,
        "bundle_dir": str(bundle_dir),
        "required_artifact_count": len(REQUIRED_ARTIFACTS),
        "findings": findings,
        "decision": decision,
        "maximum_claim": "AUTOMATED_VERIFICATION_PASS",
        "release_authorized": False,
        "marketplace_write_enabled": False,
        "merge_to_main_authorized": False,
    }


def run_negative_controls(expected_sha: str) -> dict[str, Any]:
    controls: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        baseline = root / "baseline"
        bootstrap_bundle(baseline, expected_sha)
        baseline_findings = validate_bundle(baseline, expected_sha)
        if baseline_findings:
            return {"milestone": "M9", "status": "FAIL", "baseline_findings": baseline_findings, "controls": []}

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
            (path / "FINAL_RELEASE_DECISION.md").write_text(
                _decision_text(expected_sha, "RELEASE_AUTHORIZED"), encoding="utf-8"
            )

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
            controls.append(
                {
                    "control_id": control_id,
                    "status": "PASS" if expected in actual else "FAIL",
                    "expected_finding": expected,
                    "actual_findings": actual,
                }
            )
    passed = sum(item["status"] == "PASS" for item in controls)
    return {
        "milestone": "M9",
        "protocol_version": "3.0",
        "status": "PASS" if passed == len(controls) else "FAIL",
        "exact_head": expected_sha,
        "controls": controls,
        "controls_passed": passed,
        "controls_total": len(controls),
        "release_authorized": False,
        "marketplace_write_enabled": False,
    }


def _bootstrap(args: argparse.Namespace) -> int:
    bootstrap_bundle(Path(args.output_dir), args.exact_head)
    print(json.dumps({"status": "PASS", "artifact_count": len(REQUIRED_ARTIFACTS)}))
    return 0


def _audit(args: argparse.Namespace) -> int:
    report = audit_bundle(Path(args.bundle_dir), args.expected_sha)
    _write_json(Path(args.output), report)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


def _self_test(args: argparse.Namespace) -> int:
    report = run_negative_controls(args.expected_sha)
    _write_json(Path(args.output), report)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Quantum Maximum-Assurance v3 control plane")
    commands = result.add_subparsers(dest="command", required=True)
    bootstrap = commands.add_parser("bootstrap")
    bootstrap.add_argument("--output-dir", required=True)
    bootstrap.add_argument("--exact-head", required=True)
    bootstrap.set_defaults(handler=_bootstrap)
    audit = commands.add_parser("audit")
    audit.add_argument("--bundle-dir", required=True)
    audit.add_argument("--expected-sha", required=True)
    audit.add_argument("--output", required=True)
    audit.set_defaults(handler=_audit)
    self_test = commands.add_parser("self-test")
    self_test.add_argument("--expected-sha", required=True)
    self_test.add_argument("--output", required=True)
    self_test.set_defaults(handler=_self_test)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
