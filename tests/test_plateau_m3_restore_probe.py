from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from quantum.application._finance_center_persistence import restore_reports


class PlateauM3RestoreProbe(unittest.TestCase):
    def test_emit_restore_exception(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config" / "default-home-local.json"
            config.parent.mkdir(parents=True)
            config.write_text(
                json.dumps(
                    {
                        "configuration_status": "READY",
                        "execution_mode": "ADMISSION_ONLY",
                        "tenant_id": "tenant-home-local",
                    }
                ),
                encoding="utf-8",
            )
            payload = b"not-a-real-xlsx-but-immutable"
            digest = sha256(payload).hexdigest()
            dataset_id = "dataset-persistence-test"
            tenant_token = sha256(b"tenant-home-local").hexdigest()
            source = (
                root
                / "data"
                / "pilot-zones"
                / tenant_token
                / "admitted"
                / dataset_id
                / digest
            )
            source.parent.mkdir(parents=True)
            source.write_bytes(payload)
            report = {
                "status": "ADMISSION_COMPLETE",
                "dataset_id": dataset_id,
                "file_sha256": digest,
                "file_size_bytes": len(payload),
                "sanitized_filename": "wb-detailed.xlsx",
                "source_bridge": {
                    "status": "SOURCE_BRIDGE_COMPLETE",
                    "source_type": "WB_DETAILED_FINANCIAL",
                },
            }
            output = root / "output" / "pilot_gui_20260714_010203.json"
            output.parent.mkdir(parents=True)
            output.write_text(json.dumps(report), encoding="utf-8")
            try:
                restored = restore_reports(root, config)
            except Exception as exc:
                self.fail(
                    "M3_RESTORE_EXCEPTION="
                    + type(exc).__name__
                    + ":"
                    + repr(exc)
                )
            self.assertEqual(1, len(restored))


if __name__ == "__main__":
    unittest.main()
