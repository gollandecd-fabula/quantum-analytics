from __future__ import annotations
import hashlib,json,re,unittest
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parents[1]
SCHEMAS=ROOT/"schemas"
FINANCE=ROOT/"docs"/"finance"
VECTORS=ROOT/"tests"/"contracts"/"fixtures"/"b1a-rule-resolution-vectors.json"
SCOPE_ORDER=("product_id","product_group_id","marketplace_account_id","marketplace","calculation_profile_id","scenario_id")

def load_json(path:Path)->dict[str,Any]: return json.loads(path.read_text(encoding="utf-8"))

def scope_has_explicit_null(scope:dict[str,Any])->bool:
    return any(value is None for value in scope.values())

def parse_instant(value:Any)->datetime|None:
    if not isinstance(value,str) or not value:return None
    try:
        parsed=datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None

def candidate_matches(context:dict[str,Any],candidate:dict[str,Any])->bool:
    scope=candidate["scope"]
    mode=context.get("mode")
    instant=parse_instant(context.get("calculation_instant"))
    valid_from=parse_instant(candidate.get("valid_from"))
    valid_to_raw=candidate.get("valid_to")
    valid_to=parse_instant(valid_to_raw) if valid_to_raw is not None else None
    if mode not in {"ACTUAL","SCENARIO"}:return False
    if instant is None or valid_from is None:return False
    if valid_to_raw is not None and valid_to is None:return False
    if instant<valid_from or (valid_to is not None and instant>=valid_to):return False
    if scope_has_explicit_null(scope):return False
    if not context.get("organization_id") or scope.get("organization_id")!=context["organization_id"]:return False
    if mode=="ACTUAL" and "scenario_id" in scope:return False
    if mode=="SCENARIO" and not context.get("scenario_id"):return False
    return all(k not in scope or context.get(k)==scope[k] for k in SCOPE_ORDER)

def ordering_tuple(candidate:dict[str,Any])->tuple[Any,...]:
    scope=candidate["scope"]
    return (tuple(1 if k in scope else 0 for k in SCOPE_ORDER),candidate["priority"],candidate["valid_from"],candidate["version"])

def resolve_vector(vector:dict[str,Any])->tuple[str,str|None]:
    eligible=[x for x in vector["candidates"] if candidate_matches(vector["context"],x)]
    if not eligible:return "BLOCKED",None
    ranked=sorted(eligible,key=ordering_tuple,reverse=True)
    if len(ranked)>1 and ordering_tuple(ranked[0])==ordering_tuple(ranked[1]):return "CONFLICT",None
    return "VALID",ranked[0]["rule_id"]

def has_cycle(graph:dict[str,list[str]])->bool:
    visiting:set[str]=set();visited:set[str]=set()
    def visit(node:str)->bool:
        if node in visiting:return True
        if node in visited:return False
        visiting.add(node)
        if any(visit(dep) for dep in graph.get(node,[])):return True
        visiting.remove(node);visited.add(node);return False
    return any(visit(node) for node in graph)

def scopes_intersect(a:dict[str,Any],b:dict[str,Any])->bool:
    if scope_has_explicit_null(a) or scope_has_explicit_null(b):return False
    if a.get("organization_id")!=b.get("organization_id"):return False
    return all(k not in a or k not in b or a[k]==b[k] for k in SCOPE_ORDER)

def intervals_overlap(a:dict[str,Any],b:dict[str,Any])->bool:
    return (b.get("valid_to") is None or a["valid_from"]<b["valid_to"]) and (a.get("valid_to") is None or b["valid_from"]<a["valid_to"])

def diagnostic(v:dict[str,Any])->str|None:
    if v["kind"]=="EXCLUSIVITY_OVERLAP":
        a,b=v["rules"]
        return "RULE_EXCLUSIVITY_OVERLAP" if a["exclusivity_group"]==b["exclusivity_group"] and scopes_intersect(a["scope"],b["scope"]) and intervals_overlap(a,b) else None
    if v["kind"]=="DEPENDENCY_CYCLE":return "RULE_DEPENDENCY_CYCLE" if has_cycle(v["graph"]) else None
    if v["kind"]=="UNIT_MISMATCH":
        a,b=v["producer"],v["consumer"]
        return "RULE_UNIT_MISMATCH" if a["unit"]!=b["expected_unit"] or a.get("currency")!=b.get("currency") else None
    raise AssertionError(v["kind"])

def canonical_hash(value:dict[str,Any],excluded:str)->str:
    payload=dict(value);payload.pop(excluded,None)
    return hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()

class B1aFinancialContractTests(unittest.TestCase):
    def test_all_b1a_schemas_are_valid_json_without_defaults(self):
        for name in ("configuration-rule.schema.json","safe-expression.schema.json","rounding-policy.schema.json","calculation-profile.schema.json","metric-definition.schema.json","rule-resolution-result.schema.json"):
            with self.subTest(schema=name):
                text=(SCHEMAS/name).read_text(encoding="utf-8");doc=json.loads(text)
                self.assertEqual(doc["$schema"],"https://json-schema.org/draft/2020-12/schema");self.assertNotIn('"default"',text)

    def test_configuration_rule_schema_has_typed_scope_and_exclusive_methods(self):
        schema=load_json(SCHEMAS/"configuration-rule.schema.json");scope=schema["properties"]["scope"]
        self.assertFalse(scope["additionalProperties"])
        self.assertEqual(set(scope["properties"]),{"organization_id","marketplace_account_id","marketplace","product_id","product_group_id","calculation_profile_id","scenario_id"})
        self.assertEqual(schema["properties"]["method"]["enum"],["FIXED_VALUE","RATE","SAFE_EXPRESSION"])
        text=json.dumps(schema,sort_keys=True);self.assertIn("safe-expression.schema.json",text);self.assertNotIn("C40",text)

    def test_safe_expression_allowlist_excludes_execution_and_rounding(self):
        ops=load_json(SCHEMAS/"safe-expression.schema.json")["$defs"]["operation"]["properties"]["operator"]["enum"]
        self.assertIn("MULTIPLY",ops);self.assertIn("IF",ops)
        for bad in ("EVAL","EXEC","IMPORT","SHELL","SQL","ROUND","RANDOM"):self.assertNotIn(bad,ops)

    def test_resolution_vectors_enforce_order_tenant_boundary_and_fail_closed(self):
        vectors=load_json(VECTORS)["vectors"];self.assertGreaterEqual(len(vectors),11)
        for v in vectors:
            with self.subTest(vector=v["id"]):
                self.assertTrue(v["context"].get("organization_id"))
                self.assertIn(v["context"].get("mode"),{"ACTUAL","SCENARIO"})
                self.assertIsNotNone(parse_instant(v["context"].get("calculation_instant")))
                self.assertFalse(scope_has_explicit_null(v["context"]))
                self.assertTrue(all(x["scope"].get("organization_id") for x in v["candidates"]))
                self.assertTrue(all(not scope_has_explicit_null(x["scope"]) for x in v["candidates"]))
                self.assertEqual(resolve_vector(v),(v["expected_state"],v["expected_rule_id"]))

    def test_resolution_matcher_rejects_explicit_null_scope_wildcards(self):
        context={"organization_id":"org-a","mode":"ACTUAL","calculation_instant":"2026-06-15T00:00:00Z","product_id":"p1"}
        invalid={"rule_id":"invalid-null","version":1,"scope":{"organization_id":"org-a","product_id":None},"priority":0,"valid_from":"2026-01-01T00:00:00Z"}
        valid={"rule_id":"omitted-wildcard","version":1,"scope":{"organization_id":"org-a"},"priority":0,"valid_from":"2026-01-01T00:00:00Z"}
        self.assertFalse(candidate_matches(context,invalid))
        self.assertTrue(candidate_matches(context,valid))

    def test_resolution_matcher_enforces_mode_isolation(self):
        instant="2026-06-15T00:00:00Z"
        candidate={"rule_id":"scenario","version":1,"scope":{"organization_id":"org-a","scenario_id":"s1"},"priority":0,"valid_from":"2026-01-01T00:00:00Z"}
        self.assertFalse(candidate_matches({"organization_id":"org-a","mode":"ACTUAL","calculation_instant":instant,"scenario_id":"s1"},candidate))
        self.assertTrue(candidate_matches({"organization_id":"org-a","mode":"SCENARIO","calculation_instant":instant,"scenario_id":"s1"},candidate))
        self.assertFalse(candidate_matches({"organization_id":"org-a","mode":"SCENARIO","calculation_instant":instant},candidate))
        active={"rule_id":"active","version":1,"scope":{"organization_id":"org-a"},"priority":0,"valid_from":"2026-01-01T00:00:00Z","valid_to":"2026-07-01T00:00:00Z"}
        future={"rule_id":"future","version":1,"scope":{"organization_id":"org-a"},"priority":0,"valid_from":"2026-07-01T00:00:00Z"}
        expired={"rule_id":"expired","version":1,"scope":{"organization_id":"org-a"},"priority":0,"valid_from":"2026-01-01T00:00:00Z","valid_to":"2026-06-15T00:00:00Z"}
        actual={"organization_id":"org-a","mode":"ACTUAL","calculation_instant":instant}
        self.assertTrue(candidate_matches(actual,active))
        self.assertFalse(candidate_matches(actual,future))
        self.assertFalse(candidate_matches(actual,expired))
        self.assertFalse(candidate_matches({"organization_id":"org-a","mode":"ACTUAL"},active))

    def test_validation_vectors_cover_claimed_fail_closed_blockers(self):
        vectors=load_json(VECTORS)["validation_vectors"]
        self.assertEqual({v["kind"] for v in vectors},{"EXCLUSIVITY_OVERLAP","DEPENDENCY_CYCLE","UNIT_MISMATCH"})
        for v in vectors:
            with self.subTest(vector=v["id"]):
                if v["kind"]=="EXCLUSIVITY_OVERLAP":self.assertTrue(all(not scope_has_explicit_null(rule["scope"]) for rule in v["rules"]))
                self.assertEqual(diagnostic(v),v["expected_diagnostic"])

    def test_dependency_cycles_are_detected(self):
        self.assertFalse(has_cycle({"a":["b"],"b":["c"],"c":[]}))
        self.assertTrue(has_cycle({"a":["b"],"b":["c"],"c":["a"]}));self.assertTrue(has_cycle({"self":["self"]}))

    def test_calculation_profile_hash_is_deterministic_and_mode_isolation_is_encoded(self):
        schema=load_json(SCHEMAS/"calculation-profile.schema.json");text=json.dumps(schema,sort_keys=True)
        self.assertIn('"ACTUAL"',text);self.assertIn('"SCENARIO"',text)
        profile={"profile_id":"p","profile_version":1,"profile_hash":"ignored","organization_id":"org","mode":"ACTUAL","scenario_id":None,"rule_refs":[{"id":"rule-b","version":1,"content_hash":"b"*64},{"id":"rule-a","version":2,"content_hash":"a"*64}]}
        first=canonical_hash(profile,"profile_hash");self.assertEqual(first,canonical_hash(json.loads(json.dumps(profile)),"profile_hash"));self.assertRegex(first,r"^[a-f0-9]{64}$")

    def test_rounding_policy_is_versioned_and_has_no_active_instance(self):
        modes=load_json(SCHEMAS/"rounding-policy.schema.json")["$defs"]["mode"]["enum"]
        self.assertEqual(set(modes),{"HALF_EVEN","HALF_UP","DOWN","UP","FLOOR","CEILING"})
        text=(FINANCE/"ROUNDING_POLICY.md").read_text(encoding="utf-8")
        self.assertIn("Status: `DRAFT_FOR_B1A_REVIEW`",text);self.assertIn("Intermediate/accounting rounding",text);self.assertIn("Presentation rounding",text)

    def test_metric_catalogue_contains_required_flows_and_boundaries(self):
        text=(FINANCE/"METRIC_CATALOGUE.md").read_text(encoding="utf-8")
        required={"orders_count","gross_sales_units","returned_units","payout_amount","inventory_on_hand_units","marketplace_commission_amount","forward_logistics_amount","reverse_logistics_amount","storage_amount","advertising_amount","fines_withholdings_amount","product_cost_amount","other_expense_amount","tax_amount","net_marketplace_income_amount","net_profit_amount","profit_per_sold_unit","profitability_of_costs"}
        present=set(re.findall(r"\| `([a-z0-9_.-]+)` \|",text));self.assertTrue(required.issubset(present),required-present)
        self.assertIn("A payout is not revenue",text);self.assertIn("does not treat missing return data as zero",text);self.assertIn("explicitly excludes product cost, other",text)

    def test_financial_contracts_contain_no_legacy_commercial_constants(self):
        paths=list(FINANCE.glob("*.md"))+[SCHEMAS/x for x in ("configuration-rule.schema.json","metric-definition.schema.json","rounding-policy.schema.json","calculation-profile.schema.json","safe-expression.schema.json")]
        for path in paths:
            text=path.read_text(encoding="utf-8")
            for marker in ("C40","40 ₽","400 ₽","500 ₽","cost = 400","tax_rate = 6"):
                with self.subTest(path=path.name,marker=marker):self.assertNotIn(marker,text)

if __name__=="__main__":unittest.main()
