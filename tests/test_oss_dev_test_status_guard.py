from __future__ import annotations

import copy
import unittest
from pathlib import Path

from quantum.dependencies.admission import (
    load_json_document,
    validate_register,
    validate_sbom,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "docs/dependencies/OSS_DEPENDENCY_REGISTER.yaml"
LICENSES = ROOT / "docs/dependencies/LICENSE_ALLOWLIST.yaml"
SBOM = ROOT / "docs/dependencies/SBOM.spdx.json"
WORKFLOW = ROOT / ".github/workflows/oss-admission-ci.yml"


def _duckdb(register: dict) -> dict:
    return next(
        item for item in register["components"]
        if item.get("name") == "duckdb"
    )


def _hypothesis(register: dict) -> dict:
    return next(
        item for item in register["components"]
        if item.get("name") == "hypothesis"
    )


def _mpl_rule(licenses: dict) -> dict:
    return next(
        item for item in licenses["conditional_licenses"]
        if item.get("license") == "MPL-2.0"
    )


def _verify_dev_test_status_guard() -> None:
    register = load_json_document(REGISTER)
    licenses = load_json_document(LICENSES)
    sbom = load_json_document(SBOM)
    assert validate_register(register, licenses) == ()
    assert validate_sbom(register, sbom) == ()

    conflicting_conclusion = copy.deepcopy(sbom)
    conflicting_conclusion["packages"][0]["licenseConcluded"] = "GPL-3.0-only"
    assert (
        "duckdb:SBOM_LICENSE_CONCLUDED_MISMATCH"
        in validate_sbom(register, conflicting_conclusion)
    )

    missing_conclusion = copy.deepcopy(sbom)
    missing_conclusion["packages"][0].pop("licenseConcluded")
    assert (
        "duckdb:SBOM_LICENSE_CONCLUDED_MISMATCH"
        in validate_sbom(register, missing_conclusion)
    )

    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "TARGET_SHA: ${{ github.event.pull_request.head.sha || github.sha }}" in workflow
    assert 'git fetch --depth=1 origin "${TARGET_SHA}"' in workflow
    assert 'test "$(git rev-parse HEAD)" = "${TARGET_SHA}"' in workflow
    assert 'git fetch --depth=1 origin "${GITHUB_SHA}"' not in workflow

    relabeled = copy.deepcopy(register)
    _duckdb(relabeled)["status"] = "APPROVED_DEV_TEST_ONLY"
    errors = validate_register(relabeled, licenses)
    assert "duckdb:CONDITIONAL_LICENSE_SCOPE_DESCRIPTOR_VIOLATION" in errors
    assert "duckdb:CONDITIONAL_LICENSE_ALLOWED_USE_VIOLATION" in errors

    mixed_use = copy.deepcopy(register)
    mixed_duckdb = _duckdb(mixed_use)
    mixed_duckdb["status"] = "APPROVED_DEV_TEST_ONLY"
    mixed_duckdb["scope"] = "B2_RECONCILIATION_TEST"
    mixed_duckdb["allowed_use"] = ["development tests in production runtime"]
    mixed_errors = validate_register(mixed_use, licenses)
    assert "duckdb:DEV_TEST_ALLOWED_USE_NOT_EXCLUSIVE" in mixed_errors

    for prohibited_scope in (
        "PRODUCTION_TEST",
        "B4_RUNTIME_TEST",
        "OPERATIONAL_TEST",
        "CUSTOMER_FACING_TEST",
        "USER_FACING_TEST",
    ):
        mixed_scope = copy.deepcopy(register)
        _hypothesis(mixed_scope)["scope"] = prohibited_scope
        scope_errors = validate_register(mixed_scope, licenses)
        assert "hypothesis:DEV_TEST_SCOPE_NOT_EXCLUSIVE" in scope_errors

    for mandatory_condition in (
        "development_or_test_scope_only",
        "no_vendored_modified_source_without_legal_review",
        "license_and_notice_retained",
    ):
        incomplete_policy = copy.deepcopy(licenses)
        _mpl_rule(incomplete_policy)["conditions"].remove(mandatory_condition)
        policy_errors = validate_register(register, incomplete_policy)
        assert "MPL-2.0:MANDATORY_CONDITIONS_MISSING" in policy_errors

    for prerelease_version in ("1.2.0-beta.1", "1.2rc1"):
        prerelease = copy.deepcopy(register)
        prerelease_duckdb = _duckdb(prerelease)
        prerelease_duckdb["version"] = prerelease_version
        prerelease_errors = validate_register(prerelease, licenses)
        assert (
            "duckdb:PRERELEASE_BOUNDED_EXPERIMENT_APPROVAL_REQUIRED"
            in prerelease_errors
        )

        prerelease_duckdb["prerelease_bounded_experiment"] = {
            "approved": True,
            "approval_id": "EXP-OSS-001",
            "expires_on": "2999-12-31",
            "scope": ["isolated sandbox contract tests"],
        }
        approved_errors = validate_register(prerelease, licenses)
        assert (
            "duckdb:PRERELEASE_BOUNDED_EXPERIMENT_APPROVAL_REQUIRED"
            not in approved_errors
        )

        prerelease_duckdb["prerelease_bounded_experiment"]["expires_on"] = "2000-01-01"
        expired_errors = validate_register(prerelease, licenses)
        assert (
            "duckdb:PRERELEASE_BOUNDED_EXPERIMENT_APPROVAL_REQUIRED"
            in expired_errors
        )

        prerelease_duckdb["prerelease_bounded_experiment"]["expires_on"] = "2999-02-30"
        invalid_date_errors = validate_register(prerelease, licenses)
        assert (
            "duckdb:PRERELEASE_BOUNDED_EXPERIMENT_APPROVAL_REQUIRED"
            in invalid_date_errors
        )

    incomplete_approval = copy.deepcopy(register)
    incomplete_duckdb = _duckdb(incomplete_approval)
    incomplete_duckdb["version"] = "1.2.0-beta.1"
    incomplete_duckdb["prerelease_bounded_experiment"] = {"approved": True}
    assert (
        "duckdb:PRERELEASE_BOUNDED_EXPERIMENT_APPROVAL_REQUIRED"
        in validate_register(incomplete_approval, licenses)
    )


def load_tests(
    loader: unittest.TestLoader,
    tests: unittest.TestSuite,
    pattern: str | None,
) -> unittest.TestSuite:
    del loader, tests, pattern
    return unittest.TestSuite([unittest.FunctionTestCase(_verify_dev_test_status_guard)])
