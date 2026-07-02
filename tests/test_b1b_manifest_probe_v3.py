import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATHS = (
    "schemas/financial-kernel-result.schema.json",
    "src/quantum/finance/__init__.py",
    "src/quantum/finance/_calculation_core.py",
    "src/quantum/finance/_calculation_expenses.py",
    "src/quantum/finance/_calculation_profit.py",
    "src/quantum/finance/_common.py",
    "src/quantum/finance/_expression.py",
    "src/quantum/finance/_expression_limits.py",
    "src/quantum/finance/_expression_validation.py",
    "src/quantum/finance/_metrics.py",
    "src/quantum/finance/_rounding.py",
    "src/quantum/finance/_rule_context.py",
    "src/quantum/finance/_rule_documents.py",
    "src/quantum/finance/_rule_method_evaluation.py",
    "src/quantum/finance/_rule_resolver.py",
    "src/quantum/finance/_rules_evaluate_v2.py",
    "src/quantum/finance/_rules_hardening.py",
    "src/quantum/finance/_rules_precheck.py",
    "src/quantum/finance/_rules_resolution_validation.py",
    "src/quantum/finance/_rules_resolve_facade.py",
    "src/quantum/finance/_rules_trace_registry.py",
    "src/quantum/finance/oracle.py",
    "src/quantum/finance/runtime.py",
    "tests/b1a_artifact_manifest_r8.py",
    "tests/test_b1b_decimal_context_rescue_v4.py",
    "tests/test_b1b_integer_literal_limits.py",
    "tests/test_b1b_policy_input_limits.py",
    "tests/test_b1b_rescue_input_boundaries.py",
    "tests/test_b1b_rescue_smoke.py",
)


class B1bManifestProbeV3Tests(unittest.TestCase):
    def test_emit_manifest_entries(self):
        for path in PATHS:
            data = (ROOT / path).read_bytes()
            entry = [path, hashlib.sha256(data).hexdigest(), len(data)]
            print("B1B_MANIFEST_ENTRY:" + json.dumps(entry, separators=(",", ":")))
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
