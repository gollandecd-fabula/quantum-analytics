from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from quantum.pilot._scope import LocalPilotExecutionError
from quantum.pilot.validation import validate_manifest
from tests.local_pilot_runner_fixtures import (
    DATASET_ID,
    changed,
    manifest,
    write_case,
)


class LocalPilotRunnerManifestTests(unittest.TestCase):
    def test_valid_manifest_is_bound_to_source_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, _ = write_case(root)
            result = validate_manifest(manifest_path)
        self.assertEqual(result["status"], "VALID")
        self.assertEqual(result["dataset_id"], DATASET_ID)
        self.assertEqual(len(result["original_file_sha256"]), 64)
        self.assertEqual(result["finance_labels"], ["synthetic"])

    def test_source_path_cannot_escape_manifest_directory(self):
        document = changed(manifest(), "source_file", "../outside.zip")
        with tempfile.TemporaryDirectory() as directory:
            manifest_path, _ = write_case(Path(directory), document=document)
            with self.assertRaisesRegex(
                LocalPilotExecutionError,
                "PILOT_WORKSPACE_PATH_ESCAPE",
            ):
                validate_manifest(manifest_path)

    def test_non_loopback_scope_is_rejected(self):
        document = changed(manifest(), "scope", "host", "0.0.0.0")
        with tempfile.TemporaryDirectory() as directory:
            manifest_path, _ = write_case(Path(directory), document=document)
            with self.assertRaisesRegex(
                LocalPilotExecutionError,
                "PILOT_LOOPBACK_REQUIRED",
            ):
                validate_manifest(manifest_path)

    def test_finance_lineage_must_reference_declared_dataset(self):
        document = changed(
            manifest(),
            "finance_lineage",
            "synthetic",
            "dataset_id",
            "33333333-3333-4333-8333-333333333333",
        )
        with tempfile.TemporaryDirectory() as directory:
            manifest_path, _ = write_case(Path(directory), document=document)
            with self.assertRaisesRegex(
                LocalPilotExecutionError,
                "PILOT_FINANCE_LINEAGE_MISMATCH",
            ):
                validate_manifest(manifest_path)

    def test_unknown_top_level_field_is_rejected(self):
        document = manifest()
        document["unapproved"] = True
        with tempfile.TemporaryDirectory() as directory:
            manifest_path, _ = write_case(Path(directory), document=document)
            with self.assertRaisesRegex(
                LocalPilotExecutionError,
                "PILOT_MANIFEST_INVALID",
            ):
                validate_manifest(manifest_path)


if __name__ == "__main__":
    unittest.main()
