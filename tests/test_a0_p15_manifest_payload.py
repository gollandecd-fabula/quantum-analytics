from __future__ import annotations

import json
import unittest

from tests.test_p15_manifest_payload import OVERLAY_PATH, expected_entries


class A0P15ManifestPayloadPreflightTests(unittest.TestCase):
    def test_p15_manifest_payload_is_exact(self) -> None:
        overlay = json.loads(OVERLAY_PATH.read_text(encoding="utf-8"))
        expected = expected_entries()
        if overlay["entries"] != expected:
            raise AssertionError(
                "P15_MANIFEST_ENTRIES="
                + json.dumps(expected, ensure_ascii=False, separators=(",", ":"))
            )


if __name__ == "__main__":
    unittest.main()
