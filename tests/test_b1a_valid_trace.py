import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class B1aValidTraceTests(unittest.TestCase):
    def test_valid_trace_candidate_constraint(self):
        schema = json.loads((ROOT / "schemas/rule-resolution-result.schema.json").read_text())
        rule = schema["allOf"][0]["then"]["properties"]["candidates"]
        self.assertEqual(rule["minItems"], 1)
        self.assertEqual(rule["minContains"], 1)
        self.assertEqual(rule["contains"]["properties"]["eligible"]["const"], True)
        self.assertEqual(rule["contains"]["required"], ["eligible"])

if __name__ == "__main__":
    unittest.main()
