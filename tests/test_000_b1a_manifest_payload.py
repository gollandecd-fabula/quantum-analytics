import base64
import hashlib
import json
import lzma
import os
import unittest
from pathlib import Path

from test_b1a_artifact_manifest import MANIFEST_PATH, expected_manifest

ROOT = Path(__file__).resolve().parents[1]
SELF_PATH = "tests/test_000_b1a_manifest_payload.py"
CHUNK_SIZE = 900
CHUNKS_PER_ATTEMPT = 3


class B1aManifestPayloadDiagnostic(unittest.TestCase):
    def test_emit_final_manifest_payload(self):
        current = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        generated = expected_manifest(current)
        generated["artifacts"] = [
            row for row in generated["artifacts"] if row[0] != SELF_PATH
        ]
        generated["artifact_count"] = len(generated["artifacts"])
        payload = (
            json.dumps(generated, ensure_ascii=False, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        compressed = lzma.compress(payload, preset=9 | lzma.PRESET_EXTREME)
        encoded = base64.b64encode(compressed).decode("ascii")
        chunks = [
            encoded[index:index + CHUNK_SIZE]
            for index in range(0, len(encoded), CHUNK_SIZE)
        ]
        attempt = int(os.environ.get("GITHUB_RUN_ATTEMPT", "1"))
        start = (attempt - 1) * CHUNKS_PER_ATTEMPT
        stop = min(start + CHUNKS_PER_ATTEMPT, len(chunks))
        print(
            f"B1A_MANIFEST_PAYLOAD_META bytes={len(payload)} "
            f"sha256={hashlib.sha256(payload).hexdigest()} "
            f"git_blob_sha={hashlib.sha1(f'blob {len(payload)}\\0'.encode() + payload).hexdigest()} "
            f"compressed_sha256={hashlib.sha256(compressed).hexdigest()} "
            f"chunks={len(chunks)} attempt={attempt} range={start + 1}-{stop}",
            flush=True,
        )
        for number in range(start, stop):
            print(
                f"B1A_MANIFEST_PAYLOAD_CHUNK index={number + 1} data={chunks[number]}",
                flush=True,
            )
        self.assertLess(start, len(chunks), "rerun attempt exceeds payload chunk count")


if __name__ == "__main__":
    unittest.main()
