from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"
EXPECTED_PATTERN = (
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$"
)


class B1bTimestampSchemaAlignmentTests(unittest.TestCase):
    def load(self, name: str) -> dict:
        return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))

    def test_public_finance_schemas_share_lossless_timestamp_pattern(self) -> None:
        schemas = {
            name: self.load(name)
            for name in (
                "configuration-rule.schema.json",
                "rounding-policy.schema.json",
                "calculation-profile.schema.json",
                "rule-resolution-result.schema.json",
                "financial-kernel-result.schema.json",
            )
        }
        for name, schema in schemas.items():
            with self.subTest(schema=name):
                self.assertEqual(
                    schema["$defs"]["rfc3339Microsecond"]["pattern"],
                    EXPECTED_PATTERN,
                )

    def test_schema_pattern_accepts_microseconds_and_rejects_precision_loss(self) -> None:
        self.assertIsNotNone(
            re.fullmatch(EXPECTED_PATTERN, "2026-06-30T12:00:00.123456Z")
        )
        self.assertIsNotNone(
            re.fullmatch(EXPECTED_PATTERN, "2026-06-30T12:00:00+05:00")
        )
        self.assertIsNone(
            re.fullmatch(EXPECTED_PATTERN, "2026-06-30T12:00:00.1234567Z")
        )


if __name__ == "__main__":
    unittest.main()
