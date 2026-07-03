import unittest
from copy import deepcopy
from quantum.finance import calculate,canonical_hash,evaluate_resolved_rule,resolve_rule
from quantum.finance.oracle import reference_calculate


def typed(state,value,value_type,unit,currency=None,reason_code=None):
    return {"state":state,"value":value,"value_type":value_type,"unit":unit,"currency":currency,"reason_code":reason_code,"source_ids":[]}


def policy():
    value={"policy_id":"pilot-rounding","version":1,"content_hash":"","status":"PILOT","calculation_mode":"HALF_EVEN","calculation_scale":6,"money_scale":2,"rate_scale":6,"presentation_mode":"HALF_EVEN","presentation_scale":2,"currency_presentation_scales":{"RUB":2},"application_points":["RULE_INPUT_NORMALIZATION","RULE_COMPONENT_RESULT","METRIC_FINAL_ACCOUNTING"],"max_input_precision":28,"max_input_scale":8,"actor":"pilot","created_at":"2026-07-01T00:00:00Z","source":"pilot","change_reason":"local pilot","approval_reference":"owner","supersedes":None}
    value["content_hash"]=canonical_hash(value,exclude=frozenset({"content_hash"}))
    return value


def money_rule():
    value={"rule_id":"pilot-money-expression","version":1,"content_hash":"","rule_type":"OTHER_EXPENSE","scope":{"organization_id":"org-1"},"method":"SAFE_EXPRESSION","base":"CUSTOM_VARIABLE","unit":"MONEY","currency":"RUB","dependencies":["gross_sales_amount"],"valid_from":"2026-01-01T00:00:00Z","valid_to":None,"priority":1,"exclusivity_group":None,"status":"PILOT","source":"pilot","actor":"pilot","created_at":"2026-07-01T00:00:00Z","change_reason":"p1 regression","approval_reference":"owner","supersedes":None,"expression":{"kind":"VARIABLE","name":"gross_sales_amount","value_type":"MONEY","currency":"RUB","unit":"MONEY"}}
    value["content_hash"]=canonical_hash(value,exclude=frozenset({"content_hash"}))
    return value


def context():
    return {"organization_id":"org-1","mode":"ACTUAL","scenario_id":None,"calculation_instant":"2026-07-01T00:00:00Z","marketplace_account_id":None,"marketplace":None,"product_id":None,"product_group_id":None,"calculation_profile_id":"profile-1","resolved_at":"2026-07-01T00:00:00Z","actor":"pilot"}


class B1bRescueSmokeTests(unittest.TestCase):
    def test_missing_dependency_preserves_selected_rule_signature(self):
        rule=money_rule(); resolution=resolve_rule([rule],context())
        result=evaluate_resolved_rule(resolution,[rule],{},policy())
        self.assertEqual(result["state"],"UNAVAILABLE")
        self.assertEqual((result["value_type"],result["unit"],result["currency"]),("MONEY","MONEY","RUB"))
        self.assertIn(resolution["trace_id"],result["source_ids"])
        self.assertIn(rule["content_hash"],result["source_ids"])

    def test_kernel_matches_independent_oracle(self):
        p=policy(); zero=typed("VALID","0","MONEY","MONEY","RUB")
        inputs={"gross_sales_units":typed("VALID","10","INTEGER","ITEM"),"returned_units":typed("VALID","2","INTEGER","ITEM"),"gross_sales_amount":typed("VALID","10000","MONEY","MONEY","RUB"),"discounts_amount":deepcopy(zero),"subsidies_amount":deepcopy(zero),"marketplace_commission_amount":typed("VALID","1000","MONEY","MONEY","RUB"),"forward_logistics_amount":typed("VALID","500","MONEY","MONEY","RUB"),"reverse_logistics_amount":typed("VALID","100","MONEY","MONEY","RUB"),"storage_amount":typed("VALID","100","MONEY","MONEY","RUB"),"advertising_amount":typed("VALID","200","MONEY","MONEY","RUB"),"fines_withholdings_amount":deepcopy(zero)}
        request={"calculation_id":"calc-1","organization_id":"org-1","mode":"ACTUAL","scenario_id":None,"calculated_at":"2026-07-01T00:00:00Z","profile_ref":{"id":"profile-1","version":1,"content_hash":"0"*64},"profile_status":"PILOT","rounding_policy":p,"currency":"RUB","inputs":inputs,"cost_per_unit":typed("VALID","400","MONEY","MONEY_PER_ITEM","RUB"),"other_expense_components":[{"component_id":"other-per-unit","value":typed("VALID","40","MONEY","MONEY_PER_ITEM","RUB")}],"tax_rate":typed("VALID","0.06","RATE","RATE"),"tax_base_metric_id":"gross_sales_amount"}
        actual=calculate(request)["results"]
        case={"money_scale":2,"rounding_mode":"HALF_EVEN","inputs":{"gross_sales_amount":"10000","discounts_amount":"0","subsidies_amount":"0","marketplace_commission_amount":"1000","forward_logistics_amount":"500","reverse_logistics_amount":"100","storage_amount":"100","advertising_amount":"200","fines_withholdings_amount":"0"},"gross_sales_units":10,"returned_units":2,"cost_per_unit":"400","other_expenses":[{"unit":"MONEY_PER_ITEM","value":"40"}],"tax_base_metric_id":"gross_sales_amount","tax_rate":"0.06"}
        expected=reference_calculate(case)
        for key,value in expected.items():
            self.assertEqual(actual[key]["state"],value["state"],key)
            self.assertEqual(actual[key]["value"],value["value"],key)


if __name__=="__main__":
    unittest.main()
