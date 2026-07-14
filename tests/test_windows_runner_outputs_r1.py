import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from quantum.pilot import windows_runner


class _Parser:
    def __init__(self, args):
        self.args = args

    def parse_args(self):
        return self.args


class WindowsRunnerOutputIntegrationTests(unittest.TestCase):
    def test_runner_attaches_output_bundle_without_changing_run_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.xlsx"
            source.write_bytes(b"xlsx")
            config = root / "config.json"
            config.write_text("{}", encoding="utf-8")
            output = root / "result.json"
            args = SimpleNamespace(
                home_local=True,
                config=config,
                file=source,
                storage_root=root / "storage",
                output=output,
                authority_attested=True,
                discover_only=False,
                discover_schema=False,
                schema_reviewed=False,
                expected_file_sha256=None,
                max_scan_rows=100,
                min_header_columns=3,
                debug_errors=False,
            )
            initial_report = {
                "status": "ADMISSION_COMPLETE",
                "dataset_id": "d1",
                "storage_zone_state": "ADMITTED",
                "limitations": [],
                "calculation": None,
                "reconciliation": {
                    "state": "NOT_REQUESTED",
                    "differences": [],
                },
            }
            source_bridge = {
                "status": "SOURCE_BRIDGE_COMPLETE",
                "recommendations": {
                    "recommendations": [],
                    "recommendation_count": 0,
                },
            }
            output_result = {
                "status": "OUTPUT_BUNDLE_COMPLETE",
                "directory": str(root / "Quantum_Output" / "q"),
            }
            captured = {}

            def atomic(path, payload):
                captured["path"] = path
                captured["payload"] = json.loads(json.dumps(payload))

            with (
                patch.object(windows_runner, "_parser", return_value=_Parser(args)),
                patch.object(windows_runner, "install_windows_compatibility"),
                patch.object(windows_runner, "_limits", return_value=object()),
                patch.object(
                    windows_runner._engine,
                    "run_local_pilot",
                    return_value=initial_report,
                ),
                patch.object(
                    windows_runner,
                    "attach_reviewed_source_bridge",
                    return_value=source_bridge,
                ),
                patch.object(
                    windows_runner,
                    "attach_local_output_bundle",
                    return_value=output_result,
                ) as output_mock,
                patch.object(windows_runner, "_atomic_json", side_effect=atomic),
                patch("builtins.print") as print_mock,
            ):
                code = windows_runner.main()

            self.assertEqual(code, 0)
            self.assertEqual(captured["path"], output)
            self.assertEqual(captured["payload"]["status"], "ADMISSION_COMPLETE")
            self.assertEqual(captured["payload"]["source_bridge"], source_bridge)
            self.assertEqual(captured["payload"]["output_bundle"], output_result)
            self.assertIn(
                "HOME_LOCAL_UNENCRYPTED_STORAGE",
                captured["payload"]["limitations"],
            )
            output_mock.assert_called_once()
            self.assertEqual(output_mock.call_args.kwargs["output_path"], output)
            console = json.loads(print_mock.call_args.args[0])
            self.assertEqual(console["output_bundle_status"], "OUTPUT_BUNDLE_COMPLETE")
            self.assertEqual(
                console["output_bundle_directory"],
                output_result["directory"],
            )


if __name__ == "__main__":
    unittest.main()
