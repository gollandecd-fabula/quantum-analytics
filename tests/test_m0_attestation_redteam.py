from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class M0AttestationRedTeamTests(unittest.TestCase):
    def read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8-sig")

    def test_generated_and_installed_launchers_never_attest_for_operator(self):
        builder = self.read("scripts/windows/build_local_production.ps1")
        installer = self.read("scripts/windows/install_home_local.ps1")
        self.assertNotIn('-PackageRoot "%~dp0" -AuthorityAttested -SchemaReviewed', builder)
        self.assertNotIn('import_source.ps1" -AuthorityAttested -SchemaReviewed', builder)
        self.assertNotIn('import_source.ps1" -AuthorityAttested -SchemaReviewed', installer)
        self.assertNotIn('-SkipInstall -AuthorityAttested -SchemaReviewed', installer)
        self.assertIn("Type AUTHORIZE", builder)
        self.assertIn("type REVIEWED", builder)
        self.assertIn("Launchers never attest on your behalf", builder)

    def test_noninteractive_requires_two_explicit_switches(self):
        script = self.read("scripts/windows/one_click_home_local.ps1")
        self.assertNotIn(
            "if ($NonInteractive -or ($AuthorityAttested -and $SchemaReviewed))",
            script,
        )
        self.assertIn("if ($NonInteractive)", script)
        self.assertIn("-not $AuthorityAttested -or -not $SchemaReviewed", script)
        self.assertIn(
            "Non-interactive mode requires explicit AuthorityAttested and SchemaReviewed switches.",
            script,
        )

    def test_gui_does_not_auto_attest_and_uses_visible_console(self):
        source = self.read("src/quantum/application/local_app.py")
        run_import = source[source.index("def run_import") :]
        self.assertNotIn('"-NonInteractive"', run_import)
        self.assertNotIn('"-AuthorityAttested"', run_import)
        self.assertNotIn('"-SchemaReviewed"', run_import)
        self.assertIn('getattr(subprocess, "CREATE_NEW_CONSOLE", 0)', run_import)
        self.assertIn("capture_output=False", run_import)

    def test_configuration_contains_no_preverified_evidence(self):
        config = json.loads(self.read("config/home-local.template.json"))
        self.assertFalse(config["lawful_authority_attested"])
        self.assertTrue(config["attestations"])
        self.assertTrue(all(value is False for value in config["attestations"].values()))
        wizard = self.read("scripts/windows/configure_home_local.ps1")
        for name in config["attestations"]:
            self.assertIn(f"{name} = $false", wizard)
            self.assertNotIn(f"{name} = $true", wizard)

    def test_scan_outcome_and_reviewed_period_are_bound(self):
        helper = self.read("src/quantum/pilot/import_xlsx_source.ps1")
        self.assertIn("MalwareScanOutcome", helper)
        self.assertIn("malware_scan_outcome", helper)
        self.assertIn("$scanReceipt.receipt.outcome", helper)
        self.assertIn("Configured reporting period", helper)
        self.assertIn("schema and reporting period", helper)

    def test_schema_review_is_bound_after_review_gate(self):
        runner = self.read("src/quantum/pilot/windows_runner.py")
        gate = runner.index("if not args.schema_reviewed")
        binding = runner.index('config["schema_reviewed"] = True')
        engine = runner.index("_engine.run_local_pilot", binding)
        self.assertLess(gate, binding)
        self.assertLess(binding, engine)

    def test_dataset_evidence_is_not_constant_true(self):
        tree = ast.parse(self.read("src/quantum/pilot/local_runner.py"))
        target = {
            "source_authority_verified",
            "report_period_verified",
            "control_totals_verified",
            "direct_identifiers_absent_or_approved",
            "malware_scan_clean",
        }
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "DatasetControlEvidence"
        ]
        self.assertEqual(len(calls), 1)
        values = {kw.arg: kw.value for kw in calls[0].keywords if kw.arg in target}
        self.assertEqual(set(values), target)
        for name, value in values.items():
            self.assertFalse(
                isinstance(value, ast.Constant) and value.value is True,
                f"{name} must not be fabricated as constant True",
            )
        malware = ast.unparse(values["malware_scan_clean"])
        self.assertIn("malware_scan_outcome", malware)
        self.assertIn("CLEAN", malware)

    def test_incomplete_evidence_is_reported_as_blocked(self):
        source = self.read("src/quantum/pilot/local_runner.py")
        self.assertIn("except AdmissionError as exc", source)
        self.assertIn('report["status"] = "ADMISSION_BLOCKED"', source)
        self.assertIn('"CONTROL_EVIDENCE_INCOMPLETE"', source)
        self.assertIn('"CONTROL_TOTALS_NOT_PROVIDED"', source)

    @staticmethod
    def build_minimal_xlsx() -> bytes:
        from io import BytesIO
        from zipfile import ZIP_DEFLATED, ZipFile

        parts = {
            "[Content_Types].xml": b'''<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>''',
            "_rels/.rels": b'''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>''',
            "xl/workbook.xml": b'''<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>''',
            "xl/_rels/workbook.xml.rels": b'''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>''',
            "xl/worksheets/sheet1.xml": b'''<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>article</t></is></c><c r="B1" t="inlineStr"><is><t>quantity</t></is></c><c r="C1" t="inlineStr"><is><t>sale_price</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>A-1</t></is></c><c r="B2" t="inlineStr"><is><t>1</t></is></c><c r="C2" t="inlineStr"><is><t>1000</t></is></c></row></sheetData></worksheet>''',
        }
        buffer = BytesIO()
        with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
            for name, payload in parts.items():
                archive.writestr(name, payload)
        return buffer.getvalue()

    def run_admission(self, malware_outcome: str) -> dict:
        from quantum.pilot.local_runner import run_local_pilot
        from quantum.pilot.windows_runner import _limits, apply_discovered_schema, discover_schema

        payload = self.build_minimal_xlsx()
        with tempfile.TemporaryDirectory() as temporary:
            temp = Path(temporary)
            source = temp / "report.xlsx"
            source.write_bytes(payload)
            config = json.loads(self.read("config/home-local.template.json"))
            config["configuration_status"] = "READY"
            config["retention_deadline"] = "2030-01-01T00:00:00Z"
            candidate = discover_schema(payload=payload, limits=_limits(config))
            config = apply_discovered_schema(config, candidate)
            config["lawful_authority_attested"] = True
            config["schema_reviewed"] = True
            config["malware_scan_evidence_sha256"] = hashlib.sha256(malware_outcome.encode()).hexdigest()
            config["malware_scan_outcome"] = malware_outcome
            return run_local_pilot(file_path=source, config=config, storage_root=temp / "storage")

    def test_clean_scan_and_explicit_review_can_admit(self):
        report = self.run_admission("CLEAN")
        self.assertEqual(report["status"], "ADMISSION_COMPLETE")
        self.assertEqual(report["admission_state"], "ADMITTED")
        self.assertIn("CONTROL_TOTALS_NOT_PROVIDED", report["limitations"])

    def test_defender_unavailable_cannot_claim_clean_admission(self):
        report = self.run_admission("DEFENDER_UNAVAILABLE_STRUCTURAL_FALLBACK")
        self.assertEqual(report["status"], "ADMISSION_BLOCKED")
        self.assertEqual(report["admission_state"], "VALIDATED")
        self.assertEqual(report["reason"], "DATASET_CONTROLS_INCOMPLETE")
        self.assertIn("CONTROL_EVIDENCE_INCOMPLETE", report["limitations"])


if __name__ == "__main__":
    unittest.main()
