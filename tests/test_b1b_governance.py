from __future__ import annotations

import ast
import inspect
import json
import unittest
from pathlib import Path

import quantum.finance.runtime as runtime
from quantum.finance import FinanceError, canonical_hash, validate_rounding_policy

from tests.b1b_helpers import FIXTURE_PATH, policy

B1B_PRODUCTION_MODULES = (
    "__init__.py",
    "_calculation_core.py",
    "_calculation_expenses.py",
    "_calculation_profit.py",
    "_common.py",
    "_expression.py",
    "_expression_validation.py",
    "_metrics.py",
    "_rounding.py",
    "_rules.py",
    "_rules_hardening.py",
    "runtime.py",
)


def production_module_sources() -> dict[str, str]:
    finance_dir = Path(__file__).resolve().parents[1] / "src/quantum/finance"
    sources: dict[str, str] = {}
    for module_name in B1B_PRODUCTION_MODULES:
        path = finance_dir / module_name
        if not path.is_file():
            raise AssertionError(f"B1B_PRODUCTION_MODULE_MISSING:{module_name}")
        sources[module_name] = path.read_text(encoding="utf-8")
    return sources


class B1bGovernanceTests(unittest.TestCase):
    def test_fixture_is_synthetic_and_explicitly_owner_approved(self) -> None:
        fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        self.assertFalse(fixture["real_commercial_data"])
        self.assertEqual(fixture["approval_state"], "APPROVED")
        self.assertEqual(fixture["oracle_owner_identity"], "PROJECT_OWNER_USER")

    def test_runtime_contains_no_arbitrary_code_execution(self) -> None:
        forbidden_calls = {
            "e" + "val", "ex" + "ec", "com" + "pile",
            "__im" + "port__", "op" + "en", "in" + "put",
            "flo" + "at",
        }
        forbidden_imports = {
            "sub" + "process", "sock" + "et", "req" + "uests",
            "url" + "lib", "ht" + "tp", "ft" + "plib",
            "path" + "lib", "o" + "s", "s" + "ys",
        }
        for module_name, source in production_module_sources().items():
            tree = ast.parse(source, filename=module_name)
            with self.subTest(module=module_name):
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                        self.assertNotIn(node.func.id, forbidden_calls)
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            self.assertNotIn(alias.name.split(".")[0], forbidden_imports)
                    if isinstance(node, ast.ImportFrom) and node.module:
                        self.assertNotIn(node.module.split(".")[0], forbidden_imports)
                self.assertNotIn("datetime.now", source)
                self.assertNotIn("random", source)

    def test_runtime_contains_no_binary_float_constructor(self) -> None:
        for module_name, source in production_module_sources().items():
            tree = ast.parse(source, filename=module_name)
            with self.subTest(module=module_name):
                self.assertFalse(
                    any(
                        isinstance(node, ast.Constant) and isinstance(node.value, float)
                        for node in ast.walk(tree)
                    )
                )

    def test_rounding_policy_hash_tampering_fails(self) -> None:
        document = policy()
        document["money_scale"] = 3
        with self.assertRaisesRegex(FinanceError, "ROUNDING_HASH_MISMATCH"):
            validate_rounding_policy(document)

    def test_rounding_policy_requires_explicit_accounting_points(self) -> None:
        document = policy()
        document["application_points"].remove("METRIC_FINAL_ACCOUNTING")
        document["content_hash"] = canonical_hash(
            document, exclude=frozenset({"content_hash"})
        )
        validated = validate_rounding_policy(document)
        self.assertNotIn("METRIC_FINAL_ACCOUNTING", validated["application_points"])

    def test_rounding_quantize_failure_is_typed(self) -> None:
        from quantum.finance._rounding import _input_decimal

        document = policy()
        with self.assertRaisesRegex(FinanceError, "ROUNDING_OPERATION_INVALID"):
            _input_decimal(
                "9999999999999999999999999999",
                document,
                code="VALUE_DECIMAL_INVALID",
            )

    def test_candidate_fixture_has_unique_case_ids(self) -> None:
        fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        ids = [case["case_id"] for case in fixture["cases"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_candidate_fixture_has_actual_and_scenario(self) -> None:
        fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        self.assertEqual({case["mode"] for case in fixture["cases"]}, {"ACTUAL", "SCENARIO"})

    def test_candidate_fixture_covers_zero_and_negative_values(self) -> None:
        fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        values = {
            metric["value"]
            for case in fixture["cases"]
            for metric in case["expected"].values()
            if metric["value"] is not None
        }
        self.assertTrue(any(value.startswith("-") for value in values))
        self.assertIn("0.00", values)

    def test_release_blocker_is_not_removed_by_kernel(self) -> None:
        source = inspect.getsource(runtime)
        self.assertIn("PRODUCTION_RELEASE_BLOCKED", source)
        self.assertNotIn("RELEASE_ALLOWED", source)

    def test_result_schema_is_preview_only_and_matches_runtime_version(self) -> None:
        schema_path = Path(__file__).resolve().parents[1] / "schemas/financial-kernel-result.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(
            schema["properties"]["schema_version"]["const"],
            runtime.KERNEL_SCHEMA_VERSION,
        )
        self.assertEqual(
            schema["properties"]["publication_state"]["const"],
            "PREVIEW_ONLY",
        )

    def test_result_schema_requires_exact_kernel_metric_set(self) -> None:
        schema_path = Path(__file__).resolve().parents[1] / "schemas/financial-kernel-result.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        expected = {
            "net_sold_units", "product_cost_amount", "other_expense_amount",
            "tax_amount", "net_marketplace_income_amount", "net_profit_amount",
            "profit_per_sold_unit", "profitability_of_costs",
        }
        results = schema["properties"]["results"]
        self.assertEqual(set(results["required"]), expected)
        self.assertEqual(set(results["properties"]), expected)
        self.assertFalse(results["additionalProperties"])

    def test_contract_records_owner_approval_and_release_blocker(self) -> None:
        root = Path(__file__).resolve().parents[1]
        contract = (root / "docs/finance/B1B_CALCULATION_KERNEL_CONTRACT.md").read_text(encoding="utf-8")
        self.assertIn("OWNER_APPROVED_BASELINE", contract)
        self.assertIn("approval state is `APPROVED`", contract)
        self.assertIn("`RELEASE_BLOCKED`", contract)

    def test_live_state_keeps_dependent_units_gated(self) -> None:
        root = Path(__file__).resolve().parents[1]
        state = (root / "docs/evidence/STAGE_B_EXECUTION_STATE.yaml").read_text(encoding="utf-8")
        self.assertIn("current_unit: B1b", state)
        self.assertIn("state: REVIEW_PENDING_CI_AND_INDEPENDENT_REVIEW", state)
        self.assertIn("blocker: B1B_NOT_COMPLETE", state)
        self.assertIn("blocker: B1B_AND_B2_NOT_COMPLETE", state)
        self.assertIn("production_release: BLOCKED", state)

    def test_b1b_evidence_forbids_real_data_and_activation(self) -> None:
        root = Path(__file__).resolve().parents[1]
        evidence = (root / "docs/evidence/STAGE_B_B1B_EXECUTION_STATE.yaml").read_text(encoding="utf-8")
        self.assertIn("exact_value_approval: APPROVED_BY_PROJECT_OWNER_2026-06-30", evidence)
        self.assertIn("active_rules_created: false", evidence)
        self.assertIn("source_authority_activated: false", evidence)
        self.assertIn("real_or_anonymized_commercial_data_admitted: false", evidence)
        self.assertIn("release_status: RELEASE_BLOCKED", evidence)

    def test_independent_oracle_does_not_import_production_runtime(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "src/quantum/finance/oracle.py").read_text(encoding="utf-8")
        self.assertNotIn("quantum.finance.runtime", source)
        self.assertNotIn("from .runtime", source)
        self.assertNotIn("import runtime", source)


if __name__ == "__main__":
    unittest.main()
