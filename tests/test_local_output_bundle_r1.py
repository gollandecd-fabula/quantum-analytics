import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree
from zipfile import ZipFile

from quantum.insights import build_recommendations
from quantum.outputs import (
    OutputBundleError,
    build_local_output_bundle,
    render_dashboard_html,
    render_xlsx_report,
    validate_local_output_bundle,
    write_local_output_bundle,
)
from tests.test_recommendation_engine_r1 import policy, supplier_analysis


GENERATED_AT = "2026-07-04T20:30:00Z"
SOURCE_SHA = "a" * 64


def report():
    analysis = supplier_analysis()
    analysis.update(
        {
            "schema_version": "quantum-wb-source-bridge-v1",
            "source_sha256": SOURCE_SHA,
            "limitations": ["AGGREGATED_SOURCE_NOT_EVENT_LEDGER"],
            "raw_rows_in_report": False,
        }
    )
    analysis["recommendations"] = build_recommendations(analysis, policy())
    return {
        "dataset_id": "dataset-123",
        "status": "ADMISSION_COMPLETE",
        "file_sha256": SOURCE_SHA,
        "source_bridge": analysis,
        "limitations": ["HOME_LOCAL_UNENCRYPTED_STORAGE"],
    }


class LocalOutputBundleTests(unittest.TestCase):
    def test_bundle_is_deterministic_and_valid(self):
        first = build_local_output_bundle(report(), generated_at=GENERATED_AT)
        second = build_local_output_bundle(report(), generated_at=GENERATED_AT)
        self.assertEqual(first, second)
        validate_local_output_bundle(first)
        self.assertEqual(len(first["bundle_hash"]), 64)
        self.assertNotIn("recommendations", first["analysis"])
        self.assertEqual(
            first["recommendations"]["recommendation_count"],
            len(first["recommendations"]["recommendations"]),
        )
        self.assertEqual(
            first["limitations"],
            [
                "HOME_LOCAL_UNENCRYPTED_STORAGE",
                "AGGREGATED_SOURCE_NOT_EVENT_LEDGER",
            ],
        )

    def test_raw_payload_is_rejected(self):
        unsafe = report()
        unsafe["source_bridge"]["raw_payload"] = {"secret": "value"}
        with self.assertRaises(OutputBundleError) as error:
            build_local_output_bundle(unsafe, generated_at=GENERATED_AT)
        self.assertTrue(error.exception.code.startswith("OUTPUT_RAW_DATA_FORBIDDEN:"))

    def test_xlsx_is_deterministic_valid_ooxml(self):
        bundle = build_local_output_bundle(report(), generated_at=GENERATED_AT)
        first = render_xlsx_report(bundle)
        second = render_xlsx_report(bundle)
        self.assertEqual(first, second)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.xlsx"
            path.write_bytes(first)
            with ZipFile(path) as archive:
                names = set(archive.namelist())
                self.assertIn("xl/workbook.xml", names)
                self.assertIn("xl/styles.xml", names)
                self.assertIn("xl/worksheets/sheet1.xml", names)
                workbook = ElementTree.fromstring(
                    archive.read("xl/workbook.xml")
                )
                sheets = workbook.find(
                    "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheets"
                )
                self.assertIsNotNone(sheets)
                sheet_names = [item.get("name") for item in list(sheets)]
                self.assertEqual(
                    sheet_names,
                    [
                        "Сводка",
                        "Показатели",
                        "Рекомендации",
                        "Ограничения",
                        "Источники",
                    ],
                )
                for name in names:
                    if name.endswith(".xml"):
                        ElementTree.fromstring(archive.read(name))

    def test_dashboard_is_local_and_contains_filters(self):
        bundle = build_local_output_bundle(report(), generated_at=GENERATED_AT)
        html = render_dashboard_html(bundle).decode("utf-8")
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)
        self.assertNotIn("+==", html)
        self.assertIn('id="severity"', html)
        self.assertIn('id="category"', html)
        self.assertIn(bundle["bundle_hash"], html)
        self.assertIn("Внешние библиотеки и сетевые запросы отсутствуют", html)

    def test_writer_creates_five_verified_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            result = write_local_output_bundle(
                report(),
                output_root=Path(directory),
                generated_at=GENERATED_AT,
            )
            self.assertEqual(result["status"], "OUTPUT_BUNDLE_COMPLETE")
            self.assertEqual(len(result["artifacts"]), 5)
            by_name = {item["name"]: item for item in result["artifacts"]}
            self.assertEqual(
                set(by_name),
                {
                    "quantum_result.json",
                    "recommendations.json",
                    "Quantum_Report.xlsx",
                    "dashboard.html",
                    "evidence_manifest.json",
                },
            )
            for item in result["artifacts"]:
                path = Path(item["path"])
                payload = path.read_bytes()
                self.assertEqual(len(payload), item["size_bytes"])
                self.assertEqual(hashlib.sha256(payload).hexdigest(), item["sha256"])
            manifest = json.loads(
                Path(by_name["evidence_manifest.json"]["path"]).read_text(
                    encoding="utf-8"
                )
            )
            self.assertTrue(manifest["manifest_excludes_self"])
            self.assertEqual(manifest["artifact_count"], 4)
            self.assertEqual(
                {item["name"] for item in manifest["artifacts"]},
                {
                    "quantum_result.json",
                    "recommendations.json",
                    "Quantum_Report.xlsx",
                    "dashboard.html",
                },
            )
            self.assertEqual(manifest["bundle_hash"], result["bundle_hash"])
            self.assertEqual(manifest["manifest_hash"], result["manifest_hash"])


if __name__ == "__main__":
    unittest.main()
