import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class B1aValidTraceTests(unittest.TestCase):
    def test_valid_trace_candidate_constraint(self):
        schema = json.loads(
            (ROOT / "schemas/rule-resolution-result.schema.json").read_text(
                encoding="utf-8"
            )
        )
        valid = schema["allOf"][0]["then"]["properties"]["candidates"]
        non_valid = schema["allOf"][0]["else"]["properties"]["candidates"]

        self.assertEqual(valid["minItems"], 1)
        self.assertEqual(valid["minContains"], 1)
        self.assertEqual(valid["maxContains"], 1)
        self.assertEqual(valid["contains"]["properties"]["eligible"]["const"], True)
        self.assertEqual(valid["contains"]["properties"]["selected"]["const"], True)
        self.assertEqual(valid["contains"]["required"], ["eligible", "selected"])
        self.assertEqual(non_valid["minContains"], 0)
        self.assertEqual(non_valid["maxContains"], 0)
        self.assertEqual(non_valid["contains"]["properties"]["selected"]["const"], True)


if __name__ == "__main__":
    unittest.main()
