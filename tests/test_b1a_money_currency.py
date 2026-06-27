import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class B1aMoneyCurrencyTests(unittest.TestCase):
    def test_money_nodes_require_currency(self):
        schema = json.loads((ROOT / "schemas/safe-expression.schema.json").read_text(encoding="utf-8"))
        for name in ("literal", "variable", "operation"):
            node = schema["$defs"][name]
            self.assertIn("currency", node["required"])
            matches = [
                branch for branch in node["allOf"]
                if branch["if"].get("properties", {}).get("value_type") == {"const": "MONEY"}
            ]
            self.assertEqual(len(matches), 1)
            branch = matches[0]
            self.assertEqual(branch["then"]["properties"]["currency"]["type"], "string")
            self.assertEqual(branch["else"]["properties"]["currency"]["type"], "null")

if __name__ == "__main__":
    unittest.main()
