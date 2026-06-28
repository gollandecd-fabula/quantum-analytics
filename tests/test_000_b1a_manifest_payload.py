import base64
import hashlib
import json
import lzma
import unittest

from test_b1a_artifact_manifest import MANIFEST_PATH, expected_manifest

SELF = "tests/test_000_b1a_manifest_payload.py"
START = 0
COUNT = 4
CHUNK_SIZE = 900


class B1aManifestPayloadDiagnostic(unittest.TestCase):
    def test_emit_manifest_payload(self):
        current = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        generated = expected_manifest(current)
        generated["artifacts"] = [row for row in generated["artifacts"] if row[0] != SELF]
        generated["artifact_count"] = len(generated["artifacts"])
        payload = (json.dumps(generated, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        compressed = lzma.compress(payload, preset=9 | lzma.PRESET_EXTREME)
        encoded = base64.b64encode(compressed).decode("ascii")
        chunks = [encoded[i:i + CHUNK_SIZE] for i in range(0, len(encoded), CHUNK_SIZE)]
        print(f"B1A_PAYLOAD_META bytes={len(payload)} sha256={hashlib.sha256(payload).hexdigest()} git_blob={hashlib.sha1(f'blob {len(payload)}\0'.encode() + payload).hexdigest()} compressed_sha256={hashlib.sha256(compressed).hexdigest()} chunks={len(chunks)}", flush=True)
        for index in range(START, min(START + COUNT, len(chunks))):
            print(f"B1A_PAYLOAD_CHUNK index={index + 1} data={chunks[index]}", flush=True)
        self.assertGreater(len(chunks), START)


if __name__ == "__main__":
    unittest.main()
