from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from quantum.finance import canonical_hash

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "tests" / "contracts" / "fixtures" / "b1b-golden-baseline.json"


def load_baseline() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def typed(
    value: str | bool | None,
    *,
    value_type: str,
    unit: str,
    currency: str | None = None,
    state: str = "VALID",
    reason_code: str | None = None,
    source_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "state": state,
        "value": value if state == "VALID" else None,
        "value_type": value_type,
        "unit": unit,
        "currency": currency,
        "reason_code": None if state == "VALID" else (reason_code or f"TEST_{state}"),
        "source_ids": list(source_ids or []),
    }


def policy(mode: str = "HALF_EVEN", *, money_scale: int = 2) -> dict[str, Any]:
    document = {
        "policy_id": f"synthetic-{mode.lower()}-v1",
        "version": 1,
        "content_hash": "",
        "status": "SHADOW",
        "calculation_mode": mode,
        "calculation_scale": 6,
        "money_scale": money_scale,
        "rate_scale": 6,
        "presentation_mode": mode,
        "presentation_scale": 2,
        "currency_presentation_scales": {"EUR": 2, "RUB": 2},
        "application_points": [
            "RULE_INPUT_NORMALIZATION",
            "RULE_COMPONENT_RESULT",
            "METRIC_FINAL_ACCOUNTING",
        ],
        "max_input_precision": 28,
        "max_input_scale": 8,
        "actor": "business-golden-oracle-owner",
        "created_at": "2026-06-30T16:00:00Z",
        "source": "synthetic-approved-methodology",
        "change_reason": "B1b independent decimal baseline",
        "approval_reference": "user-b1b-authorization-2026-06-30",
        "supersedes": None,
    }
    document["content_hash"] = canonical_hash(
        document, exclude=frozenset({"content_hash"})
    )
    return document


def request_from_case(case: dict[str, Any]) -> dict[str, Any]:
    currency = case["currency"]
    inputs = {
        "gross_sales_units": typed(
            case["gross_sales_units"], value_type="INTEGER", unit="ITEM"
        ),
        "returned_units": typed(
            case["returned_units"], value_type="INTEGER", unit="ITEM"
        ),
    }
    for metric_id, value in case["inputs"].items():
        inputs[metric_id] = typed(
            value, value_type="MONEY", unit="MONEY", currency=currency
        )
    return {
        "calculation_id": case["case_id"],
        "organization_id": "org-synthetic",
        "mode": case["mode"],
        "scenario_id": case["scenario_id"],
        "calculated_at": "2026-06-30T16:30:00Z",
        "profile_ref": {
            "id": f"profile-{case['mode'].lower()}",
            "version": 1,
            "content_hash": "1" * 64,
        },
        "profile_status": "SHADOW",
        "rounding_policy": policy(
            case["rounding_mode"], money_scale=case["money_scale"]
        ),
        "currency": currency,
        "inputs": inputs,
        "cost_per_unit": typed(
            case["cost_per_unit"],
            value_type="MONEY",
            unit="MONEY_PER_ITEM",
            currency=currency,
        ),
        "other_expense_components": [
            {
                "component_id": component["component_id"],
                "value": typed(
                    component["value"],
                    value_type="MONEY",
                    unit=component["unit"],
                    currency=currency,
                ),
            }
            for component in case["other_expenses"]
        ],
        "tax_rate": typed(
            case["tax_rate"], value_type="RATE", unit="RATE"
        ),
        "tax_base_metric_id": case["tax_base_metric_id"],
    }


def rule_document(
    *,
    rule_id: str = "cost.default",
    method: str = "FIXED_VALUE",
    status: str = "SHADOW",
    scope: dict[str, str] | None = None,
    priority: int = 0,
    version: int = 1,
    valid_from: str = "2026-01-01T00:00:00Z",
    exclusivity_group: str | None = None,
    value: str = "40",
    rate: str = "0.06",
    expression: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if method == "RATE":
        rule_type = "TAX"
        unit = "RATE"
        currency = None
        base = "GROSS_SALES"
        dependencies = ["gross_sales_amount"]
    elif method == "SAFE_EXPRESSION":
        rule_type = "OTHER_EXPENSE"
        unit = "MONEY"
        currency = "EUR"
        base = "CUSTOM_VARIABLE"
        dependencies = ["gross_sales_amount", "tax_rate"]
    else:
        rule_type = "COST"
        unit = "MONEY_PER_ITEM"
        currency = "EUR"
        base = "UNIT"
        dependencies = []
    document: dict[str, Any] = {
        "rule_id": rule_id,
        "version": version,
        "content_hash": "",
        "rule_type": rule_type,
        "scope": scope or {"organization_id": "org-synthetic"},
        "method": method,
        "base": base,
        "unit": unit,
        "currency": currency,
        "dependencies": dependencies,
        "valid_from": valid_from,
        "valid_to": None,
        "priority": priority,
        "exclusivity_group": exclusivity_group,
        "status": status,
        "source": "synthetic-test",
        "actor": "test-fixture",
        "created_at": "2026-06-30T16:00:00Z",
        "change_reason": "B1b test vector",
        "approval_reference": "user-b1b-authorization-2026-06-30",
        "supersedes": None,
    }
    if method == "FIXED_VALUE":
        document["value"] = value
    elif method == "RATE":
        document["rate"] = rate
    else:
        document["expression"] = expression
    document["content_hash"] = canonical_hash(
        document, exclude=frozenset({"content_hash"})
    )
    return document


def context(**overrides: Any) -> dict[str, Any]:
    base = {
        "organization_id": "org-synthetic",
        "mode": "ACTUAL",
        "scenario_id": None,
        "calculation_instant": "2026-06-30T12:00:00Z",
        "marketplace_account_id": None,
        "marketplace": None,
        "product_id": None,
        "product_group_id": None,
        "calculation_profile_id": "profile-actual",
        "resolved_at": "2026-06-30T16:30:00Z",
        "actor": "b1b-test",
    }
    base.update(overrides)
    return base


def result_projection(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        metric_id: {
            "state": metric["state"],
            "value": metric["value"],
        }
        for metric_id, metric in result["results"].items()
    }
