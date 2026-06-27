import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class B1aCustomVariableDependencyTests(unittest.TestCase):
    def test_custom_variable_base_requires_dependency(self):
        schema = json.loads((ROOT / "schemas/configuration-rule.schema.json").read_text(encoding="utf-8"))
        matches = []
        for branch in schema["allOf"]:
            base = branch["if"].get("properties", {}).get("base")
            if base == {"const": "CUSTOM_VARIABLE"}:
                matches.append(branch)

        self.assertEqual(len(matches), 1)
        branch = matches[0]
        self.assertEqual(branch["if"]["required"], ["base"])
        self.assertEqual(branch["then"]["properties"]["dependencies"]["minItems"], 1)

if __name__ == "__main__":
    unittest.main()
