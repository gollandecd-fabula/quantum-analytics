from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path

from quantum.ingestion import RawFileRecord, RawFileState
from quantum.ux import (
    apply_configuration_values,
    build_configuration_form,
    build_exception_inbox,
)


NOW = datetime(2026, 6, 30, 20, 0, tzinfo=UTC)
TENANT_ID = "tenant-contract-alignment"
ROOT = Path(__file__).resolve().parents[1]


def configuration_form():
    return build_configuration_form(
        form_id="form-contract-alignment",
        organization_id="org-synthetic",
        mode="ACTUAL",
        scenario_id=None,
        actor="pilot-user",
        scope={"organization_id": "org-synthetic"},
        valid_from=NOW,
        valid_to=None,
        currency="RUB",
        created_at=NOW,
    )


class P15ContractAlignmentTests(unittest.TestCase):
    def test_tax_base_matches_b1a_rate_vocabulary(self) -> None:
        allowed = {
            "UNIT",
            "ORDER",
            "EVENT",
            "PERIOD",
            "GROSS_SALES",
            "NET_SALES",
            "PAYOUT",
            "PRODUCT_COST",
            "CUSTOM_VARIABLE",
        }
        for value in sorted(allowed):
            with self.subTest(value=value):
                configured = apply_configuration_values(
                    configuration_form(),
                    {"tax_base": value},
                )
                tax_base = configured["fields"][2]
                self.assertEqual(tax_base["state"], "VALID")
                self.assertEqual(tax_base["value"], value)

        for value in ("NONE", "UNVERIFIED_BASE"):
            with self.subTest(rejected=value):
                configured = apply_configuration_values(
                    configuration_form(),
                    {"tax_base": value},
                )
                tax_base = configured["fields"][2]
                self.assertEqual(tax_base["state"], "INVALID")
                self.assertEqual(tax_base["diagnostic"], "TAX_BASE_INVALID")

    def test_empty_import_diagnostics_use_stable_fallback_cause(self) -> None:
        digest = "e" * 64
        record = RawFileRecord(
            raw_file_id="00000000-0000-4000-8000-000000000030",
            tenant_id=TENANT_ID,
            sha256=digest,
            size_bytes=64,
            sanitized_filename="empty-diagnostics.csv",
            storage_key=f"tenants/{TENANT_ID}/raw/{digest}",
            state=RawFileState.QUARANTINED,
            schema_id=None,
            structural_fingerprint={"columns": ["unknown"]},
            semantic_fingerprint=None,
            diagnostics=("", ""),
        )
        inbox = build_exception_inbox(
            [],
            import_records=[record],
            tenant_id=TENANT_ID,
            generated_at=NOW,
        )
        self.assertEqual(inbox["exception_count"], 1)
        self.assertEqual(inbox["exceptions"][0]["cause"], "IMPORT_QUARANTINED")
        self.assertIn("IMPORT_QUARANTINED", inbox["exceptions"][0]["accessible_summary"])

    def test_premerge_evidence_uses_current_pr_head_target(self) -> None:
        evidence = (
            ROOT / "docs/evidence/STAGE_P1_5_EXECUTION_STATE.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("verification_target: CURRENT_PR_HEAD", evidence)
        self.assertIn("review_target: CURRENT_PR_HEAD", evidence)
        self.assertIn(
            "merge_sha_recording: POST_MERGE_CLOSURE_ONLY",
            evidence,
        )
        self.assertNotIn("requested_commit:", evidence)
        self.assertNotIn("exact_head:", evidence)


if __name__ == "__main__":
    unittest.main()
