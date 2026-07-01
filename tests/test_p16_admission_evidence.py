import unittest

from tests.p16_fixtures import *  # noqa: F403


class P16AdmissionEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tenant = TenantContext("tenant-1", "account-1")
        self.other = TenantContext("tenant-2", "account-2")
        self.registry = RealDatasetAdmissionRegistry()
    def test_incomplete_storage_controls_block_admission(self):
        payload = build_xlsx()
        record = self.registry.declare(
            tenant=self.tenant,
            declaration=declaration(self.tenant, payload),
        )
        self.registry.inspect_and_validate(
            tenant=self.tenant,
            dataset_id=record.declaration.dataset_id,
            payload=payload,
            policy=policy(),
            observed_at=NOW + timedelta(minutes=1),
        )
        with self.assertRaises(AdmissionError) as error:
            self.registry.admit(
                tenant=self.tenant,
                dataset_id=record.declaration.dataset_id,
                dataset_control_evidence=dataset_evidence(
                    self.tenant,
                    self.registry.get(
                        tenant=self.tenant,
                        dataset_id=record.declaration.dataset_id,
                    ),
                ),
                storage_evidence=evidence(
                    self.tenant,
                    self.registry.get(
                        tenant=self.tenant,
                        dataset_id=record.declaration.dataset_id,
                    ),
                    encryption_at_rest=False,
                ),
                admitted_at=NOW + timedelta(minutes=2),
            )
        self.assertEqual(error.exception.code, "STORAGE_CONTROLS_INCOMPLETE")
    def test_evidence_summary_contains_no_raw_headers_or_rows(self):
        payload = build_xlsx()
        record = self.registry.declare(
            tenant=self.tenant,
            declaration=declaration(self.tenant, payload),
        )
        self.registry.inspect_and_validate(
            tenant=self.tenant,
            dataset_id=record.declaration.dataset_id,
            payload=payload,
            policy=policy(),
            observed_at=NOW + timedelta(minutes=1),
        )
        summary = self.registry.evidence_summary(
            tenant=self.tenant,
            dataset_id=record.declaration.dataset_id,
        )
        serialized = json.dumps(summary, sort_keys=True)
        self.assertNotIn("operation_id", serialized)
        self.assertNotIn("SALE", serialized)
        self.assertNotIn("100.00", serialized)
        self.assertNotIn(self.tenant.tenant_id, summary["tenant_id_sha256"])
        self.assertNotIn(record.declaration.source_internal_id, serialized)
        self.assertNotIn("source_internal_id", summary)
        self.assertEqual(
            summary["source_internal_id_sha256"],
            sha256(
                record.declaration.source_internal_id.encode("utf-8")
            ).hexdigest(),
        )
    def test_declaration_requires_future_retention_and_authority(self):
        payload = build_xlsx()
        values = declaration(self.tenant, payload).__dict__ if hasattr(declaration(self.tenant, payload), "__dict__") else {
            field: getattr(declaration(self.tenant, payload), field)
            for field in declaration(self.tenant, payload).__dataclass_fields__
        }
        values["dataset_id"] = str(uuid4())
        values["lawful_authority_attested"] = False
        with self.assertRaises(AdmissionError) as error:
            DatasetDeclaration(**values)
        self.assertEqual(error.exception.code, "DATASET_AUTHORITY_ATTESTATION_REQUIRED")
    def test_quarantined_dataset_can_be_revalidated_with_new_policy(self):
        payload = build_xlsx()
        record = self.registry.declare(
            tenant=self.tenant,
            declaration=declaration(self.tenant, payload),
        )
        wrong_policy = policy(headers=("wrong", "header", "set"))
        blocked = self.registry.inspect_and_validate(
            tenant=self.tenant,
            dataset_id=record.declaration.dataset_id,
            payload=payload,
            policy=wrong_policy,
            observed_at=NOW + timedelta(minutes=1),
        )
        self.assertEqual(blocked.state, DatasetAdmissionState.QUARANTINED)
        validated = self.registry.inspect_and_validate(
            tenant=self.tenant,
            dataset_id=record.declaration.dataset_id,
            payload=payload,
            policy=policy(),
            observed_at=NOW + timedelta(minutes=2),
        )
        self.assertEqual(validated.state, DatasetAdmissionState.VALIDATED)
        self.assertEqual(validated.policy_content_hash, policy().content_hash)
        self.assertEqual(
            [decision.state for decision in validated.decisions],
            [
                DatasetAdmissionState.DECLARED,
                DatasetAdmissionState.QUARANTINED,
                DatasetAdmissionState.QUARANTINED,
                DatasetAdmissionState.VALIDATED,
            ],
        )
    def test_personal_data_sensitivity_is_not_approved_in_foundation(self):
        payload = build_xlsx()
        base = declaration(self.tenant, payload)
        values = {
            field: getattr(base, field)
            for field in base.__dataclass_fields__
        }
        values["dataset_id"] = str(uuid4())
        values["sensitivity"] = DatasetSensitivity.COMMERCIAL_WITH_PERSONAL_DATA
        with self.assertRaises(AdmissionError) as error:
            DatasetDeclaration(**values)
        self.assertEqual(error.exception.code, "DATASET_PERSONAL_DATA_NOT_APPROVED")
    def test_storage_evidence_must_bind_to_dataset_and_source_hash(self):
        payload = build_xlsx()
        record = self.registry.declare(
            tenant=self.tenant,
            declaration=declaration(self.tenant, payload),
        )
        validated = self.registry.inspect_and_validate(
            tenant=self.tenant,
            dataset_id=record.declaration.dataset_id,
            payload=payload,
            policy=policy(),
            observed_at=NOW + timedelta(minutes=1),
        )
        with self.assertRaises(AdmissionError) as error:
            self.registry.admit(
                tenant=self.tenant,
                dataset_id=record.declaration.dataset_id,
                dataset_control_evidence=dataset_evidence(self.tenant, validated),
                storage_evidence=evidence(
                    self.tenant,
                    validated,
                    dataset_id=str(uuid4()),
                ),
                admitted_at=NOW + timedelta(minutes=2),
            )
        self.assertEqual(error.exception.code, "STORAGE_EVIDENCE_DATASET_MISMATCH")
        with self.assertRaises(AdmissionError) as error:
            self.registry.admit(
                tenant=self.tenant,
                dataset_id=record.declaration.dataset_id,
                dataset_control_evidence=dataset_evidence(self.tenant, validated),
                storage_evidence=evidence(
                    self.tenant,
                    validated,
                    original_file_sha256="f" * 64,
                ),
                admitted_at=NOW + timedelta(minutes=2),
            )
        self.assertEqual(error.exception.code, "STORAGE_EVIDENCE_FILE_MISMATCH")
    def test_decision_history_is_privacy_safe_and_complete(self):
        payload = build_xlsx()
        record = self.registry.declare(
            tenant=self.tenant,
            declaration=declaration(self.tenant, payload),
        )
        validated = self.registry.inspect_and_validate(
            tenant=self.tenant,
            dataset_id=record.declaration.dataset_id,
            payload=payload,
            policy=policy(),
            observed_at=NOW + timedelta(minutes=1),
        )
        admitted = self.registry.admit(
            tenant=self.tenant,
            dataset_id=record.declaration.dataset_id,
            dataset_control_evidence=dataset_evidence(self.tenant, validated),
            storage_evidence=evidence(self.tenant, validated),
            admitted_at=NOW + timedelta(minutes=2),
        )
        self.assertEqual(len(admitted.decisions), 4)
        summary = self.registry.evidence_summary(
            tenant=self.tenant,
            dataset_id=record.declaration.dataset_id,
        )
        self.assertEqual(summary["decision_count"], 4)
        serialized = json.dumps(summary, sort_keys=True)
        self.assertNotIn(self.tenant.account_id, serialized)


if __name__ == "__main__":
    unittest.main()
