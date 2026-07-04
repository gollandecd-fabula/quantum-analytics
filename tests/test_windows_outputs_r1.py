from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from quantum.outputs import verify_local_output_directory
from quantum.pilot.windows_outputs import attach_local_output_bundle
from tests.test_local_output_bundle_r1 import GENERATED_AT, report


class WindowsOutputsTests(unittest.TestCase):
    def test_source_bridge_report_creates_verified_outputs_next_to_primary_report(self):
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "import.json"
            result = attach_local_output_bundle(
                report=report(),
                output_path=output_path,
                generated_at=GENERATED_AT,
            )
            self.assertEqual(result["status"], "OUTPUT_BUNDLE_COMPLETE")
            self.assertEqual(
                result["windows_integration_schema_version"],
                "quantum-windows-output-integration-v1",
            )
            self.assertEqual(result["primary_output_path"], str(output_path.resolve()))
            self.assertEqual(
                result["output_root"],
                str((output_path.parent / "Quantum_Output").resolve()),
            )
            self.assertEqual(result["artifact_count"], 5)
            verified = verify_local_output_directory(Path(result["directory"]))
            self.assertEqual(verified["bundle_hash"], result["bundle_hash"])

    def test_report_without_source_bridge_is_skipped(self):
        self.assertIsNone(
            attach_local_output_bundle(
                report={"status": "ADMISSION_REJECTED"},
                output_path=Path("output.json"),
                generated_at=GENERATED_AT,
            )
        )

    def test_writer_error_is_isolated_and_message_is_not_exposed(self):
        with patch(
            "quantum.pilot.windows_outputs.write_local_output_bundle",
            side_effect=RuntimeError("sensitive path"),
        ):
            result = attach_local_output_bundle(
                report=report(),
                output_path=Path("output.json"),
                generated_at=GENERATED_AT,
            )
        self.assertEqual(result["status"], "OUTPUT_BUNDLE_ERROR")
        self.assertEqual(result["detail"], "RuntimeError")
        self.assertEqual(result["reason_code"], "OUTPUT_BUNDLE_UNEXPECTED_ERROR")
        self.assertNotIn("sensitive path", str(result))


if __name__ == "__main__":
    unittest.main()
