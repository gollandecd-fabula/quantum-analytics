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


def load_tests(
    loader: unittest.TestLoader,
    tests: unittest.TestSuite,
    pattern: str | None,
) -> unittest.TestSuite:
    del loader, tests, pattern
    return unittest.TestSuite([unittest.FunctionTestCase(_verify_hardening_cases)])
