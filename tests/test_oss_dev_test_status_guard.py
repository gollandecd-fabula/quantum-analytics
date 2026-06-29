from __future__ import annotations

import copy
import unittest
from pathlib import Path

from quantum.dependencies.admission import load_json_document, validate_register

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "docs/dependencies/OSS_DEPENDENCY_REGISTER.yaml"
LICENSES = ROOT / "docs/dependencies/LICENSE_ALLOWLIST.yaml"


def _duckdb(register: dict) -> dict:
    return next(
        item for item in register["components"]
        if item.get("name") == "duckdb"
    )


def _mpl_rule(licenses: dict) -> dict:
    return next(
        item for item in licenses["conditional_licenses"]
        if item.get("license") == "MPL-2.0"
    )


def _verify_dev_test_status_guard() -> None:
    register = load_json_document(REGISTER)
    licenses = load_json_document(LICENSES)
    assert validate_register(register, licenses) == ()

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

    for mandatory_condition in (
        "development_or_test_scope_only",
        "no_vendored_modified_source_without_legal_review",
        "license_and_notice_retained",
    ):
        incomplete_policy = copy.deepcopy(licenses)
        _mpl_rule(incomplete_policy)["conditions"].remove(mandatory_condition)
        policy_errors = validate_register(register, incomplete_policy)
        assert "MPL-2.0:MANDATORY_CONDITIONS_MISSING" in policy_errors


def load_tests(
    loader: unittest.TestLoader,
    tests: unittest.TestSuite,
    pattern: str | None,
) -> unittest.TestSuite:
    del loader, tests, pattern
    return unittest.TestSuite([unittest.FunctionTestCase(_verify_dev_test_status_guard)])
