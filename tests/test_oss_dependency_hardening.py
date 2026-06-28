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
            "license_text": "ignored",
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
