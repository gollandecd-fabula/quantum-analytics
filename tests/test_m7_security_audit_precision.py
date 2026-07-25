from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "tools/m7_security_performance_one_click.py"
SPEC = importlib.util.spec_from_file_location("m7_assurance_precision", TOOL_PATH)
assert SPEC is not None and SPEC.loader is not None
m7 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = m7
SPEC.loader.exec_module(m7)


class M7SecurityAuditPrecisionTests(unittest.TestCase):
    def test_ci_marker_string_is_not_runtime_write_enablement(self) -> None:
        marker = "marketplace_write_enabled" + " = true"
        source = f"FORBIDDEN_SOURCE_MARKERS = ({marker!r},)\n"
        self.assertFalse(m7._python_enables_marketplace_writes(source))

    def test_real_python_write_enablement_is_still_blocked(self) -> None:
        samples = (
            "marketplace_write_enabled = True\n",
            "config = {'marketplace_write_enabled': True}\n",
            "build(marketplace_write_enabled=True)\n",
        )
        for source in samples:
            with self.subTest(source=source):
                self.assertTrue(m7._python_enables_marketplace_writes(source))

    def test_forwarded_attestation_is_not_an_implicit_switch_default(self) -> None:
        forwarded = "$helperArguments = @{ AuthorityAttested = $true }"
        self.assertFalse(
            m7._has_implicit_switch_default(forwarded, "AuthorityAttested")
        )

    def test_real_implicit_switch_default_is_still_blocked(self) -> None:
        declaration = "param([switch]$AuthorityAttested = $true)"
        self.assertTrue(
            m7._has_implicit_switch_default(declaration, "AuthorityAttested")
        )

    def test_repository_audit_does_not_classify_oss_url_read_as_network_write(self) -> None:
        result = m7.audit_repository(ROOT)
        self.assertEqual(result["status"], "PASS", result)
        self.assertFalse(
            any(
                "urllib.request.urlopen(" in finding["message"]
                for finding in result["all_findings"]
            ),
            result,
        )


if __name__ == "__main__":
    unittest.main()
