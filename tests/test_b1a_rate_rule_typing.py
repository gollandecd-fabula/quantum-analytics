import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class B1aRateRuleTypingTests(unittest.TestCase):
    def test_rate_rules_require_rate_unit_and_null_currency(self):
        schema = json.loads(
            (ROOT / "schemas/configuration-rule.schema.json").read_text(encoding="utf-8")
        )
        matches = []
        for branch in schema["allOf"]:
            method = branch["if"].get("properties", {}).get("method")
            if method == {"const": "RATE"}:
                matches.append(branch)

        self.assertEqual(len(matches), 1)
        properties = matches[0]["then"]["properties"]
        self.assertEqual(properties["unit"], {"const": "RATE"})
        self.assertEqual(properties["currency"], {"type": "null"})


if __name__ == "__main__":
    unittest.main()
