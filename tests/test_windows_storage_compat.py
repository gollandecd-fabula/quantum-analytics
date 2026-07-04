import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from quantum.ingestion import LocalRawStorage
from quantum.pilot.windows_storage_compat import _storage_atomic_write


class WindowsStorageCompatibilityTests(unittest.TestCase):
    def test_public_storage_class_uses_compatibility_writer(self):
        self.assertIs(
            LocalRawStorage._atomic_write.__func__,
            _storage_atomic_write,
        )

    def test_storage_replace_occurs_after_temporary_handle_is_closed(self):
        original_named = tempfile.NamedTemporaryFile
        original_replace = os.replace
        state = {}

        class TrackedContext:
            def __init__(self, *args, **kwargs):
                self._context = original_named(*args, **kwargs)
                self.handle = None

            def __enter__(self):
                self.handle = self._context.__enter__()
                state["handle"] = self.handle
                return self.handle

            def __exit__(self, exc_type, exc, tb):
                return self._context.__exit__(exc_type, exc, tb)

        def checked_replace(source, destination):
            self.assertTrue(state["handle"].closed)
            return original_replace(source, destination)

        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "raw" / "payload.bin"
            with mock.patch(
                "quantum.pilot.windows_storage_compat.tempfile.NamedTemporaryFile",
                side_effect=lambda *args, **kwargs: TrackedContext(*args, **kwargs),
            ), mock.patch(
                "quantum.pilot.windows_storage_compat.os.replace",
                side_effect=checked_replace,
            ):
                LocalRawStorage._atomic_write(target, b"payload")
            self.assertEqual(target.read_bytes(), b"payload")


if __name__ == "__main__":
    unittest.main()
