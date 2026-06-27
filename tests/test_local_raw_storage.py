import hashlib
import io
import tempfile
import unittest
from pathlib import Path

from quantum.infrastructure.local_raw_storage import (
    ImmutableObjectConflict,
    LocalImmutableRawStorage,
)


class LocalRawStorageTests(unittest.TestCase):
    def test_write_and_idempotent_replay(self):
        content = b"quantum-source-file"
        digest = hashlib.sha256(content).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalImmutableRawStorage(Path(tmp))
            first = store.put_immutable(
                storage_key="org/account/file.bin",
                stream=io.BytesIO(content),
                expected_sha256=digest,
            )
            second = store.put_immutable(
                storage_key="org/account/file.bin",
                stream=io.BytesIO(content),
                expected_sha256=digest,
            )
            self.assertEqual(first, second)
            self.assertEqual(first.read_bytes(), content)

    def test_same_key_with_different_bytes_is_rejected(self):
        first_content = b"first"
        second_content = b"second"
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalImmutableRawStorage(Path(tmp))
            store.put_immutable(
                storage_key="file.bin",
                stream=io.BytesIO(first_content),
                expected_sha256=hashlib.sha256(first_content).hexdigest(),
            )
            with self.assertRaises(ImmutableObjectConflict):
                store.put_immutable(
                    storage_key="file.bin",
                    stream=io.BytesIO(second_content),
                    expected_sha256=hashlib.sha256(second_content).hexdigest(),
                )

    def test_path_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalImmutableRawStorage(Path(tmp))
            with self.assertRaises(ValueError):
                store.put_immutable(
                    storage_key="../escape.bin",
                    stream=io.BytesIO(b"x"),
                    expected_sha256=hashlib.sha256(b"x").hexdigest(),
                )


if __name__ == "__main__":
    unittest.main()
