from __future__ import annotations

import json
import unittest

from tests.test_p15_manifest_payload import effective_entries, expected_entries


class A0P15ManifestPayloadPreflightTests(unittest.TestCase):
    def test_p15_manifest_payload_is_exact(self) -> None:
        expected = expected_entries()
        actual = effective_entries()
        if actual != expected:
            payload = (
                "P15_CLOSURE_MANIFEST_ENTRIES="
                + json.dumps(expected, ensure_ascii=False, separators=(",", ":"))
            )
            print(payload, flush=True)
            raise AssertionError(payload)


if __name__ == "__main__":
    unittest.main()
