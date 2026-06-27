import base64
import json
import lzma
import sys
import unittest

from test_b1a_artifact_manifest import MANIFEST_PATH, expected_manifest


class ArtifactManifestPayloadTests(unittest.TestCase):
    def test_emit_payload_before_manifest_failure(self):
        current = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        expected = expected_manifest(current)
        if current != expected:
            payload = json.dumps(
                expected, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
            encoded = base64.b64encode(
                lzma.compress(payload, preset=9 | lzma.PRESET_EXTREME)
            ).decode("ascii")
            sys.stderr.write(f"MANIFEST_LZMA_B64={encoded}\n")
            sys.stderr.flush()
        self.assertEqual(current, expected)


if __name__ == "__main__":
    unittest.main()
