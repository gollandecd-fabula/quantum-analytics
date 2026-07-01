import hashlib,json,unittest
from pathlib import Path
R=Path(__file__).resolve().parents[1]
P=("schemas/financial-kernel-result.schema.json","src/quantum/finance/__init__.py","src/quantum/finance/_calculation_core.py","src/quantum/finance/_calculation_expenses.py","src/quantum/finance/_calculation_profit.py","src/quantum/finance/_common.py","src/quantum/finance/_expression.py","src/quantum/finance/_expression_validation.py","src/quantum/finance/_metrics.py","src/quantum/finance/_rounding.py","src/quantum/finance/_rules.py","src/quantum/finance/_rules_hardening.py","src/quantum/finance/oracle.py","src/quantum/finance/runtime.py","tests/test_b1b_rescue_smoke.py")
class Rows(unittest.TestCase):
 def test_rows(self):
  rows=[]
  for p in P:
   b=(R/p).read_bytes();rows.append([p,hashlib.sha256(b).hexdigest(),len(b)])
  print("ROWS="+json.dumps(rows),flush=True);self.assertEqual(len(rows),15)
