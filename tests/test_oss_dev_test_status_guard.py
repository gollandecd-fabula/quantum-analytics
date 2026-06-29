from __future__ import annotations

import copy
import unittest
from pathlib import Path

from quantum.dependencies.admission import load_json_document, validate_register

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "docs/dependencies/OSS_DEPENDENCY_REGISTER.yaml"
LICENSES = ROOT / "docs/dependencies/LICENSE_ALLOWLIST.yaml"


def _verify_dev_test_status_guard() -> None:
    register = load_json_document(REGISTER)
    licenses = load_json_document(LICENSES)
    assert validate_register(register, licenses) == ()

    relabeled = copy.deepcopy(register)
    duckdb = next(
        item for item in relabeled["components"]
        if item.get("name") == "duckdb"
    )
    duckdb["status"] = "APPROVED_DEV_TEST_ONLY"

    errors = validate_register(relabeled, licenses)
    assert "duckdb:CONDITIONAL_LICENSE_SCOPE_DESCRIPTOR_VIOLATION" in errors
    assert "duckdb:CONDITIONAL_LICENSE_ALLOWED_USE_VIOLATION" in errors


def load_tests(
    loader: unittest.TestLoader,
    tests: unittest.TestSuite,
    pattern: str | None,
) -> unittest.TestSuite:
    del loader, tests, pattern
    return unittest.TestSuite([unittest.FunctionTestCase(_verify_dev_test_status_guard)])
