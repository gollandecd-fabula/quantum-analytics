import unittest
from copy import deepcopy
from quantum.finance import FinanceError,calculate
from tests.test_b1b_rescue_smoke import policy,typed

def request():
 z=typed("VALID","0","MONEY","MONEY","RUB")
 i={"gross_sales_units":typed("VALID","1","INTEGER","ITEM"),"returned_units":typed("VALID","0","INTEGER","ITEM"),"gross_sales_amount":typed("VALID","1000","MONEY","MONEY","RUB"),"discounts_amount":deepcopy(z),"subsidies_amount":deepcopy(z),"marketplace_commission_amount":deepcopy(z),"forward_logistics_amount":deepcopy(z),"reverse_logistics_amount":deepcopy(z),"storage_amount":deepcopy(z),"advertising_amount":deepcopy(z),"fines_withholdings_amount":deepcopy(z)}
 return {"calculation_id":"b","organization_id":"org-1","mode":"ACTUAL","scenario_id":None,"calculated_at":"2026-07-01T00:00:00Z","profile_ref":{"id":"p","version":1,"content_hash":"0"*64},"profile_status":"PILOT","rounding_policy":policy(),"currency":"RUB","inputs":i,"cost_per_unit":typed("VALID","0","MONEY","MONEY_PER_ITEM","RUB"),"other_expense_components":[{"component_id":"o","value":typed("VALID","0","MONEY","MONEY_PER_ITEM","RUB")}],"tax_rate":typed("VALID","0","RATE","RATE"),"tax_base_metric_id":"gross_sales_amount"}

class B1bInputBoundaryTests(unittest.TestCase):
 def test_malformed_expense(self):
  r=request();r["other_expense_components"]=[{"component_id":"x"}]
  with self.assertRaises(FinanceError) as e:calculate(r)
  self.assertEqual(e.exception.code,"OTHER_EXPENSE_COMPONENTS_INVALID")
 def test_duplicate_expense(self):
  r=request();c=r["other_expense_components"][0];r["other_expense_components"]=[c,deepcopy(c)]
  with self.assertRaises(FinanceError) as e:calculate(r)
  self.assertEqual(e.exception.code,"OTHER_EXPENSE_COMPONENTS_INVALID")
 def test_zero_is_valid(self):
  x=calculate(request())["results"]["other_expense_amount"]
  self.assertEqual((x["state"],x["value"]),("VALID","0.00"))
 def test_mode_isolation(self):
  r=request();r["scenario_id"]="s"
  with self.assertRaises(FinanceError) as e:calculate(r)
  self.assertEqual(e.exception.code,"PROFILE_MODE_CONTAMINATION")
  r=request();r["mode"]="SCENARIO"
  with self.assertRaises(FinanceError) as e:calculate(r)
  self.assertEqual(e.exception.code,"PROFILE_MODE_CONTAMINATION")
