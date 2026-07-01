from __future__ import annotations

import io
import unittest


B1B_MODULES = (
    "tests.test_b1b_dependency_limits",
    "tests.test_b1b_differential_oracle",
    "tests.test_b1b_expression_hardening",
    "tests.test_b1b_financial_kernel",
    "tests.test_b1b_financial_signature_precedence",
    "tests.test_b1b_rescue_governance",
    "tests.test_b1b_rule_admission_validation",
    "tests.test_b1b_rule_resolution_and_expression",
    "tests.test_b1b_second_review_regressions",
    "tests.test_b1b_timestamp_schema_alignment",
    "tests.test_b1b_trusted_trace_precedence",
)


class A0B1bRescuePreflightTests(unittest.TestCase):
    def test_complete_b1b_rescue_suite_is_green(self) -> None:
        suite = unittest.defaultTestLoader.loadTestsFromNames(B1B_MODULES)
        self.assertGreater(suite.countTestCases(), 0)
        stream = io.StringIO()
        result = unittest.TextTestRunner(
            stream=stream,
            verbosity=2,
            failfast=False,
        ).run(suite)
        if not result.wasSuccessful():
            output = stream.getvalue()
            self.fail(
                "B1B_RESCUE_PREFLIGHT_FAILED\n"
                f"tests_run={result.testsRun}\n"
                f"failures={len(result.failures)}\n"
                f"errors={len(result.errors)}\n"
                f"skipped={len(result.skipped)}\n"
                + output[-12000:]
            )


if __name__ == "__main__":
    unittest.main()
