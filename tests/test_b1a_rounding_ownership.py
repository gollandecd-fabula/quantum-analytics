import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class B1aRoundingOwnershipTests(unittest.TestCase):
    def test_rounding_policy_is_not_a_configuration_rule(self):
        rule_schema = json.loads((ROOT / "schemas/configuration-rule.schema.json").read_text(encoding="utf-8"))
        profile_schema = json.loads((ROOT / "schemas/calculation-profile.schema.json").read_text(encoding="utf-8"))
        contract = (ROOT / "docs/finance/CONFIGURATION_RULE_CONTRACT.md").read_text(encoding="utf-8")

        self.assertEqual(
            rule_schema["properties"]["rule_type"]["enum"],
            ["COST", "TAX", "OTHER_EXPENSE", "ALLOCATION"],
        )
        self.assertEqual(
            profile_schema["properties"]["rounding_policy_ref"]["$ref"],
            "#/$defs/versionedRef",
        )
        self.assertIn("Rounding policy is not a Configuration Rule type", contract)
        self.assertIn("`rounding_policy_ref`", contract)

if __name__ == "__main__":
    unittest.main()
