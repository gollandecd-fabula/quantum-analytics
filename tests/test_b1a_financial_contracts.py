from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"
FINANCE = ROOT / "docs" / "finance"
VECTORS = ROOT / "tests" / "contracts" / "fixtures" / "b1a-rule-resolution-vectors.json"

SCOPE_ORDER = (
    "product_id",
    "product_group_id",
    "marketplace_account_id",
    "marketplace",
    "calculation_profile_id",
    "scenario_id",
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def candidate_matches(context: dict[str, Any], candidate: dict[str, Any]) -> bool:
    scope = candidate["scope"]
    for key in SCOPE_ORDER:
        expected = scope.get(key)
        if expected is not None and context.get(key) != expected:
            return False
    return True


def ordering_tuple(candidate: dict[str, Any]) -> tuple[Any, ...]:
    scope = candidate["scope"]
    specificity = tuple(1 if scope.get(key) is not None else 0 for key in SCOPE_ORDER)
    return (
        specificity,
        candidate["priority"],
        candidate["valid_from"],
        candidate["version"],
    )


def resolve_vector(vector: dict[str, Any]) -> tuple[str, str | None]:
    eligible = [item for item in vector["candidates"] if candidate_matches(vector["context"], item)]
    if not eligible:
        return "BLOCKED", None
    ranked = sorted(eligible, key=ordering_tuple, reverse=True)
    if len(ranked) > 1 and ordering_tuple(ranked[0]) == ordering_tuple(ranked[1]):
        return "CONFLICT", None
    return "VALID", ranked[0]["rule_id"]


def has_cycle(graph: dict[str, list[str]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for dependency in graph.get(node, []):
            if visit(dependency):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in graph)


def canonical_hash(value: dict[str, Any], excluded_key: str) -> str:
    payload = dict(value)
    payload.pop(excluded_key, None)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class B1aFinancialContractTests(unittest.TestCase):
    def test_all_b1a_schemas_are_valid_json_without_defaults(self) -> None:
        names = (
            "configuration-rule.schema.json",
            "safe-expression.schema.json",
            "rounding-policy.schema.json",
            "calculation-profile.schema.json",
            "metric-definition.schema.json",
            "rule-resolution-result.schema.json",
        )
        for name in names:
            with self.subTest(schema=name):
                text = (SCHEMAS / name).read_text(encoding="utf-8")
                document = json.loads(text)
                self.assertEqual(document["$schema"], "https://json-schema.org/draft/2020-12/schema")
                self.assertNotIn('"default"', text)

    def test_configuration_rule_schema_has_typed_scope_and_exclusive_methods(self) -> None:
        schema = load_json(SCHEMAS / "configuration-rule.schema.json")
        scope = schema["properties"]["scope"]
        self.assertFalse(scope["additionalProperties"])
        self.assertEqual(
            set(scope["properties"]),
            {
                "organization_id",
                "marketplace_account_id",
                "marketplace",
                "product_id",
                "product_group_id",
                "calculation_profile_id",
                "scenario_id",
            },
        )
        self.assertEqual(
            schema["properties"]["method"]["enum"],
            ["FIXED_VALUE", "RATE", "SAFE_EXPRESSION"],
        )
        serialized = json.dumps(schema, sort_keys=True)
        self.assertIn("safe-expression.schema.json", serialized)
        self.assertNotIn("C40", serialized)

    def test_safe_expression_allowlist_excludes_execution_and_rounding(self) -> None:
        schema = load_json(SCHEMAS / "safe-expression.schema.json")
        operators = schema["$defs"]["operation"]["properties"]["operator"]["enum"]
        self.assertIn("MULTIPLY", operators)
        self.assertIn("IF", operators)
        for forbidden in ("EVAL", "EXEC", "IMPORT", "SHELL", "SQL", "ROUND", "RANDOM"):
            self.assertNotIn(forbidden, operators)

    def test_resolution_vectors_follow_total_order_and_fail_closed(self) -> None:
        vectors = load_json(VECTORS)["vectors"]
        self.assertGreaterEqual(len(vectors), 7)
        for vector in vectors:
            with self.subTest(vector=vector["id"]):
                state, rule_id = resolve_vector(vector)
                self.assertEqual(state, vector["expected_state"])
                self.assertEqual(rule_id, vector["expected_rule_id"])

    def test_dependency_cycles_are_detected(self) -> None:
        self.assertFalse(has_cycle({"a": ["b"], "b": ["c"], "c": []}))
        self.assertTrue(has_cycle({"a": ["b"], "b": ["c"], "c": ["a"]}))
        self.assertTrue(has_cycle({"self": ["self"]}))

    def test_calculation_profile_hash_is_deterministic_and_mode_isolation_is_encoded(self) -> None:
        schema = load_json(SCHEMAS / "calculation-profile.schema.json")
        serialized = json.dumps(schema, sort_keys=True)
        self.assertIn('"ACTUAL"', serialized)
        self.assertIn('"SCENARIO"', serialized)
        profile = {
            "profile_id": "p",
            "profile_version": 1,
            "profile_hash": "ignored",
            "organization_id": "org",
            "mode": "ACTUAL",
            "scenario_id": None,
            "rule_refs": [
                {"id": "rule-b", "version": 1, "content_hash": "b" * 64},
                {"id": "rule-a", "version": 2, "content_hash": "a" * 64},
            ],
        }
        first = canonical_hash(profile, "profile_hash")
        second = canonical_hash(json.loads(json.dumps(profile)), "profile_hash")
        self.assertEqual(first, second)
        self.assertRegex(first, r"^[a-f0-9]{64}$")

    def test_rounding_policy_is_versioned_and_has_no_active_instance(self) -> None:
        schema = load_json(SCHEMAS / "rounding-policy.schema.json")
        modes = schema["$defs"]["mode"]["enum"]
        self.assertEqual(set(modes), {"HALF_EVEN", "HALF_UP", "DOWN", "UP", "FLOOR", "CEILING"})
        policy = (FINANCE / "ROUNDING_POLICY.md").read_text(encoding="utf-8")
        self.assertIn("Status: `DRAFT_FOR_B1A_REVIEW`", policy)
        self.assertIn("Intermediate/accounting rounding", policy)
        self.assertIn("Presentation rounding", policy)

    def test_metric_catalogue_contains_required_flows_and_boundaries(self) -> None:
        catalogue = (FINANCE / "METRIC_CATALOGUE.md").read_text(encoding="utf-8")
        required = {
            "orders_count",
            "gross_sales_units",
            "returned_units",
            "payout_amount",
            "inventory_on_hand_units",
            "marketplace_commission_amount",
            "forward_logistics_amount",
            "reverse_logistics_amount",
            "storage_amount",
            "advertising_amount",
            "fines_withholdings_amount",
            "product_cost_amount",
            "other_expense_amount",
            "tax_amount",
            "net_marketplace_income_amount",
            "net_profit_amount",
            "profit_per_sold_unit",
            "profitability_of_costs",
        }
        present = set(re.findall(r"\| `([a-z0-9_.-]+)` \|", catalogue))
        self.assertTrue(required.issubset(present), required - present)
        self.assertIn("A payout is not revenue", catalogue)
        self.assertIn("does not treat missing return data as zero", catalogue)
        self.assertIn("explicitly excludes product cost, other", catalogue)

    def test_financial_contracts_contain_no_legacy_commercial_constants(self) -> None:
        forbidden = ("C40", "40 ₽", "400 ₽", "500 ₽", "cost = 400", "tax_rate = 6")
        paths = list(FINANCE.glob("*.md")) + [
            SCHEMAS / "configuration-rule.schema.json",
            SCHEMAS / "metric-definition.schema.json",
            SCHEMAS / "rounding-policy.schema.json",
            SCHEMAS / "calculation-profile.schema.json",
            SCHEMAS / "safe-expression.schema.json",
        ]
        for path in paths:
            text = path.read_text(encoding="utf-8")
            for marker in forbidden:
                with self.subTest(path=path.name, marker=marker):
                    self.assertNotIn(marker, text)


if __name__ == "__main__":
    unittest.main()
