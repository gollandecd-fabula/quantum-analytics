from __future__ import annotations

import copy
import unittest
from pathlib import Path

from quantum.dependencies.admission import (
    load_json_document,
    validate_register,
    validate_sbom,
)
from quantum.scripts.oss_admission_scan import (
    license_matches,
    license_metadata_matches,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "docs/dependencies/OSS_DEPENDENCY_REGISTER.yaml"
LICENSES = ROOT / "docs/dependencies/LICENSE_ALLOWLIST.yaml"
SBOM = ROOT / "docs/dependencies/SBOM.spdx.json"


def _verify_hardening_cases() -> None:
    register = load_json_document(REGISTER)
    licenses = load_json_document(LICENSES)
    sbom = load_json_document(SBOM)

    malformed_ecosystem = copy.deepcopy(register)
    malformed_ecosystem["components"][0]["ecosystem"] = []
    assert "duckdb:ECOSYSTEM_INVALID" in validate_register(malformed_ecosystem, licenses)

    malformed_name = copy.deepcopy(register)
    malformed_name["components"][0]["name"] = []
    assert "COMPONENT_NAME_INVALID" in validate_register(malformed_name, licenses)

    duplicate_package = copy.deepcopy(sbom)
    duplicate = copy.deepcopy(duplicate_package["packages"][0])
    duplicate["SPDXID"] = "SPDXRef-Package-duckdb-duplicate"
    duplicate_package["packages"].append(duplicate)
    duplicate_package["documentDescribes"].append(duplicate["SPDXID"])
    assert "duckdb:SBOM_DUPLICATE_PACKAGE" in validate_sbom(register, duplicate_package)

    duplicate_spdx = copy.deepcopy(sbom)
    duplicate_spdx["packages"][1]["SPDXID"] = duplicate_spdx["packages"][0]["SPDXID"]
    assert (
        "SPDXRef-Package-duckdb:SBOM_DUPLICATE_SPDXID"
        in validate_sbom(register, duplicate_spdx)
    )

    assert not license_matches("MIT", "MIT-0")
    assert not license_matches("MIT", "MIT AND GPL-3.0-only")
    assert not license_matches("MIT", "MIT OR Apache-2.0")
    assert not license_matches("Apache-2.0", "Apache-2.0 OR MIT")
    assert license_matches("MIT", "License :: OSI Approved :: MIT License")
    assert license_metadata_matches(
        "MIT",
        {
            "license_expression": "MIT",
            "license_text": "MIT",
            "license_classifiers": [],
        },
    )
    assert not license_metadata_matches(
        "MIT",
        {
            "license_expression": "MIT",
            "license_text": "GPL-3.0-only",
            "license_classifiers": [],
        },
    )
    assert not license_metadata_matches(
        "MIT",
        {
            "license_expression": "MIT",
            "license_text": "License :: Other/Proprietary License",
            "license_classifiers": [],
        },
    )
    assert not license_metadata_matches(
        "MIT",
        {
            "license_expression": ["MIT"],
            "license_text": "MIT",
            "license_classifiers": [],
        },
    )
    assert not license_metadata_matches(
        "MIT",
        {
            "license_expression": "MIT AND GPL-3.0-only",
            "license_text": "",
            "license_classifiers": [],
        },
    )
    assert license_metadata_matches(
        "MIT",
        {
            "license_expression": None,
            "license_text": "",
            "license_classifiers": [
                "License :: OSI Approved",
                "License :: OSI Approved :: MIT License",
            ],
        },
    )
    assert not license_metadata_matches(
        "MIT",
        {
            "license_expression": None,
            "license_text": "",
            "license_classifiers": [
                "License :: OSI Approved :: MIT License",
                "License :: OSI Approved :: GNU General Public License (GPL)",
            ],
        },
    )
    assert not license_metadata_matches(
        "MIT",
        {
            "license_expression": None,
            "license_text": "",
            "license_classifiers": [
                "License :: OSI Approved :: MIT License",
                "License :: Other/Proprietary License",
            ],
        },
    )
    assert not license_metadata_matches(
        "MIT",
        {
            "license_expression": "MIT",
            "license_text": "",
            "license_classifiers": [
                "License :: OSI Approved :: GNU General Public License (GPL)",
            ],
        },
    )
    assert not license_metadata_matches(
        "MIT",
        {
            "license_expression": None,
            "license_text": "",
            "license_classifiers": "License :: OSI Approved :: MIT License",
        },
    )

    conditional_scope = copy.deepcopy(register)
    conditional_scope["components"][0]["license"] = "MPL-2.0"
    conditional_scope["components"][0]["prohibited_use"].append(
        "vendoring modified source without review"
    )
    assert (
        "duckdb:CONDITIONAL_LICENSE_SCOPE_VIOLATION"
        in validate_register(conditional_scope, licenses)
    )

    conditional_dev = copy.deepcopy(conditional_scope)
    conditional_dev["components"][0]["status"] = "APPROVED_DEV_TEST_ONLY"
    conditional_errors = validate_register(conditional_dev, licenses)
    assert not any(error.startswith("duckdb:CONDITIONAL_LICENSE_") for error in conditional_errors)

    missing_vendor_guard = copy.deepcopy(conditional_dev)
    missing_vendor_guard["components"][0]["prohibited_use"].remove(
        "vendoring modified source without review"
    )
    assert (
        "duckdb:CONDITIONAL_LICENSE_VENDORING_GUARD_REQUIRED"
        in validate_register(missing_vendor_guard, licenses)
    )

    missing_notice_policy = copy.deepcopy(licenses)
    missing_notice_policy["rules"]["license_notice_required"] = False
    assert (
        "hypothesis:CONDITIONAL_LICENSE_NOTICE_POLICY_REQUIRED"
        in validate_register(register, missing_notice_policy)
    )

    unsupported_condition = copy.deepcopy(licenses)
    unsupported_condition["conditional_licenses"][0]["conditions"].append(
        "unrecognized_condition"
    )
    assert (
        "MPL-2.0:LICENSE_CONDITION_UNSUPPORTED"
        in validate_register(register, unsupported_condition)
    )

    state = load_json_document(
        ROOT / "docs/evidence/OSS_DEPENDENCY_ADMISSION_STATE.yaml"
    )
    status_counts = {
        "approved_future": sum(
            item.get("status") == "APPROVED_FOR_FUTURE_INTEGRATION"
            for item in register["components"]
        ),
        "approved_dev_test_only": sum(
            item.get("status") == "APPROVED_DEV_TEST_ONLY"
            for item in register["components"]
        ),
        "audit_required": sum(
            item.get("status") == "AUDIT_REQUIRED"
            for item in register["components"]
        ),
    }
    for key, value in status_counts.items():
        assert state["component_counts"][key] == value
    assert sum(state["component_counts"].values()) == len(register["components"])


def load_tests(
    loader: unittest.TestLoader,
    tests: unittest.TestSuite,
    pattern: str | None,
) -> unittest.TestSuite:
    del loader, tests, pattern
    return unittest.TestSuite([unittest.FunctionTestCase(_verify_hardening_cases)])
