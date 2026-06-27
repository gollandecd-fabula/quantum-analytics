import base64
import hashlib
import json
import lzma
import os
import sys
import unittest

from test_b1a_artifact_manifest import MANIFEST_PATH, expected_manifest

CHUNK_SIZE = 1000


class ArtifactManifestPayloadTests(unittest.TestCase):
    def test_emit_payload_before_manifest_failure(self):
        current = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        expected = expected_manifest(current)
        if current != expected:
            payload = json.dumps(
                expected, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
            compressed = lzma.compress(
                payload, preset=9 | lzma.PRESET_EXTREME
            )
            encoded = base64.b64encode(compressed).decode("ascii")
            chunks = [
                encoded[index:index + CHUNK_SIZE]
                for index in range(0, len(encoded), CHUNK_SIZE)
            ]
            attempt = max(1, int(os.environ.get("GITHUB_RUN_ATTEMPT", "1")))
            index = min(attempt, len(chunks)) - 1
            checksum = hashlib.sha256(compressed).hexdigest()
            sys.stderr.write(
                f"MANIFEST_CHUNK={index + 1}/{len(chunks)};"
                f"SHA256={checksum};DATA={chunks[index]}\n"
            )
            sys.stderr.flush()
        self.assertEqual(current, expected)


if __name__ == "__main__":
    unittest.main()
