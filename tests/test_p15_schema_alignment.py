from __future__ import annotations

import json
import unittest
from pathlib import Path

from quantum.ux import (
    CONFIGURATION_FORM_VERSION,
    EXCEPTION_INBOX_VERSION,
    UX_SCHEMA_VERSION,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"
RFC3339_PATTERN = (
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
CANONICAL_UUID_PATTERN = (
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12}$"
)


def load_schema(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


class P15SchemaAlignmentTests(unittest.TestCase):
    def test_schema_versions_match_runtime_constants(self) -> None:
        form = load_schema("ux-configuration-form.schema.json")
        view = load_schema("ux-view.schema.json")
        inbox = load_schema("exception-inbox.schema.json")
        self.assertEqual(
            form["properties"]["schema_version"]["const"],
            CONFIGURATION_FORM_VERSION,
        )
        for variant in ("metricResult", "importStatus", "evidenceDrilldown"):
            self.assertEqual(
                view["$defs"][variant]["properties"]["schema_version"]["const"],
                UX_SCHEMA_VERSION,
            )
        self.assertEqual(
            inbox["properties"]["schema_version"]["const"],
            EXCEPTION_INBOX_VERSION,
        )

    def test_configuration_form_has_exact_explicit_input_order(self) -> None:
        form = load_schema("ux-configuration-form.schema.json")
        fields = form["properties"]["fields"]
        self.assertEqual(fields["minItems"], 4)
        self.assertEqual(fields["maxItems"], 4)
        refs = [item["$ref"] for item in fields["prefixItems"]]
        self.assertEqual(
            refs,
            [
                "#/$defs/costField",
                "#/$defs/taxRateField",
                "#/$defs/taxBaseField",
                "#/$defs/otherExpenseField",
            ],
        )
        self.assertFalse(fields["items"])

    def test_configuration_form_is_preview_only_and_closed(self) -> None:
        form = load_schema("ux-configuration-form.schema.json")
        self.assertFalse(form["additionalProperties"])
        self.assertEqual(
            form["properties"]["publication_state"]["const"],
            "PREVIEW_ONLY",
        )
        self.assertIn("valid_from", form["required"])
        self.assertIn("scope", form["required"])
        self.assertIn("currency", form["required"])
        for field_id in ("valid_from", "valid_to", "created_at"):
            self.assertEqual(
                form["properties"][field_id]["pattern"],
                RFC3339_PATTERN,
            )
        self.assertNotIn("default", json.dumps(form, sort_keys=True))

    def test_form_scope_matches_b1a_exclusivity_floor(self) -> None:
        form = load_schema("ux-configuration-form.schema.json")
        scope = form["properties"]["scope"]
        self.assertFalse(scope["additionalProperties"])
        self.assertEqual(scope["required"], ["organization_id"])
        self.assertEqual(
            scope["not"]["required"],
            ["product_id", "product_group_id"],
        )

    def test_accessible_view_variants_are_closed(self) -> None:
        view = load_schema("ux-view.schema.json")
        for variant in ("metricResult", "importStatus", "evidenceDrilldown"):
            with self.subTest(variant=variant):
                definition = view["$defs"][variant]
                self.assertFalse(definition["additionalProperties"])
                self.assertIn("view_hash", definition["required"])

    def test_metric_and_import_status_require_text_semantics(self) -> None:
        view = load_schema("ux-view.schema.json")
        for variant in ("metricResult", "importStatus"):
            with self.subTest(variant=variant):
                definition = view["$defs"][variant]
                required = set(definition["required"])
                self.assertTrue(
                    {
                        "status_label",
                        "status_token",
                        "semantic_role",
                        "accessible_summary",
                    }.issubset(required)
                )
                self.assertEqual(
                    definition["properties"]["semantic_role"]["const"],
                    "status",
                )

    def test_import_view_cannot_expose_storage_key(self) -> None:
        view = load_schema("ux-view.schema.json")
        import_view = view["$defs"]["importStatus"]
        self.assertNotIn("storage_key", import_view["properties"])
        self.assertNotIn("storage_key", import_view["required"])
        self.assertEqual(
            import_view["properties"]["raw_file_id"]["$ref"],
            "#/$defs/canonicalUuid",
        )
        self.assertEqual(
            view["$defs"]["canonicalUuid"]["pattern"],
            CANONICAL_UUID_PATTERN,
        )

    def test_evidence_drilldown_has_explicit_verification_claim(self) -> None:
        view = load_schema("ux-view.schema.json")
        drilldown = view["$defs"]["evidenceDrilldown"]
        required = set(drilldown["required"])
        self.assertIn("verification_status", required)
        self.assertIn("can_claim_verified_evidence", required)
        self.assertIn("evidence_chain_content_hash", required)

    def test_exception_contract_requires_cause_evidence_and_resolution(self) -> None:
        inbox = load_schema("exception-inbox.schema.json")
        exception = inbox["$defs"]["exception"]
        required = set(exception["required"])
        self.assertTrue(
            {
                "cause",
                "affected_metric_ids",
                "evidence_refs",
                "required_resolution",
                "accessible_summary",
            }.issubset(required)
        )
        self.assertFalse(exception["additionalProperties"])

    def test_exception_inbox_preserves_contexts_separately(self) -> None:
        inbox = load_schema("exception-inbox.schema.json")
        required = set(inbox["required"])
        self.assertIn("tenant_id", required)
        self.assertIn("organization_id", required)
        self.assertIn("mode", required)
        self.assertIn("available_metric_ids", required)
        self.assertIn("independent_results_preserved", required)
        self.assertEqual(
            inbox["properties"]["generated_at"]["pattern"],
            RFC3339_PATTERN,
        )
        self.assertEqual(
            inbox["$defs"]["rawFileEvidenceRef"]["properties"]
            ["raw_file_id"]["$ref"],
            "#/$defs/canonicalUuid",
        )
        self.assertEqual(
            inbox["$defs"]["canonicalUuid"]["pattern"],
            CANONICAL_UUID_PATTERN,
        )


if __name__ == "__main__":
    unittest.main()
