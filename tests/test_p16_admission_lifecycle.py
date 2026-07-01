import unittest

from tests.p16_fixtures import *  # noqa: F403


class P16AdmissionLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tenant = TenantContext("tenant-1", "account-1")
        self.other = TenantContext("tenant-2", "account-2")
        self.registry = RealDatasetAdmissionRegistry()
    def test_full_state_machine_and_revocation(self):
        payload = wrap_xlsx(build_xlsx())
        declared = self.registry.declare(
            tenant=self.tenant,
            declaration=declaration(self.tenant, payload),
        )
        self.assertEqual(declared.state, DatasetAdmissionState.DECLARED)
        validated = self.registry.inspect_and_validate(
            tenant=self.tenant,
            dataset_id=declared.declaration.dataset_id,
            payload=payload,
            policy=policy(),
            observed_at=NOW + timedelta(minutes=1),
        )
        self.assertEqual(validated.state, DatasetAdmissionState.VALIDATED)
        admitted = self.registry.admit(
            tenant=self.tenant,
            dataset_id=declared.declaration.dataset_id,
            dataset_control_evidence=dataset_evidence(self.tenant, validated),
            storage_evidence=evidence(self.tenant, validated),
            admitted_at=NOW + timedelta(minutes=2),
        )
        self.assertEqual(admitted.state, DatasetAdmissionState.ADMITTED)
        self.registry.require_admitted(
            tenant=self.tenant,
            dataset_id=declared.declaration.dataset_id,
        )
        revoked = self.registry.revoke(
            tenant=self.tenant,
            dataset_id=declared.declaration.dataset_id,
            reason_code="OWNER_WITHDRAWAL",
            revoked_at=NOW + timedelta(minutes=3),
        )
        self.assertEqual(revoked.state, DatasetAdmissionState.REVOKED)
        with self.assertRaises(AdmissionError) as error:
            self.registry.require_admitted(
                tenant=self.tenant,
                dataset_id=declared.declaration.dataset_id,
            )
        self.assertEqual(error.exception.code, "DATASET_NOT_ADMITTED")
    def test_unknown_schema_stays_quarantined(self):
        payload = build_xlsx(headers=("different", "header", "set"))
        record = self.registry.declare(
            tenant=self.tenant,
            declaration=declaration(self.tenant, payload),
        )
        blocked = self.registry.inspect_and_validate(
            tenant=self.tenant,
            dataset_id=record.declaration.dataset_id,
            payload=payload,
            policy=policy(),
            observed_at=NOW + timedelta(minutes=1),
        )
        self.assertEqual(blocked.state, DatasetAdmissionState.QUARANTINED)
        self.assertIn("XLSX_SCHEMA_UNKNOWN", blocked.diagnostics)
        with self.assertRaises(AdmissionError) as error:
            self.registry.admit(
                tenant=self.tenant,
                dataset_id=record.declaration.dataset_id,
                dataset_control_evidence=dataset_evidence(self.tenant, blocked),
                storage_evidence=evidence(self.tenant, blocked),
                admitted_at=NOW + timedelta(minutes=2),
            )
        self.assertEqual(error.exception.code, "DATASET_NOT_VALIDATED")
    def test_row_control_mismatch_stays_quarantined(self):
        payload = build_xlsx()
        record = self.registry.declare(
            tenant=self.tenant,
            declaration=declaration(self.tenant, payload, rows=2),
        )
        blocked = self.registry.inspect_and_validate(
            tenant=self.tenant,
            dataset_id=record.declaration.dataset_id,
            payload=payload,
            policy=policy(),
            observed_at=NOW + timedelta(minutes=1),
        )
        self.assertEqual(blocked.state, DatasetAdmissionState.QUARANTINED)
        self.assertIn("DATASET_CONTROL_ROW_COUNT_MISMATCH", blocked.diagnostics)
    def test_original_digest_mismatch_is_rejected(self):
        payload = build_xlsx()
        record = self.registry.declare(
            tenant=self.tenant,
            declaration=declaration(self.tenant, payload),
        )
        rejected = self.registry.inspect_and_validate(
            tenant=self.tenant,
            dataset_id=record.declaration.dataset_id,
            payload=payload + b"tamper",
            policy=policy(),
            observed_at=NOW + timedelta(minutes=1),
        )
        self.assertEqual(rejected.state, DatasetAdmissionState.REJECTED)
        self.assertEqual(rejected.reason_code, "DATASET_ORIGINAL_FILE_MISMATCH")
    def test_hard_container_failure_is_rejected(self):
        payload = build_xlsx(macro=True)
        record = self.registry.declare(
            tenant=self.tenant,
            declaration=declaration(self.tenant, payload),
        )
        rejected = self.registry.inspect_and_validate(
            tenant=self.tenant,
            dataset_id=record.declaration.dataset_id,
            payload=payload,
            policy=policy(),
            observed_at=NOW + timedelta(minutes=1),
        )
        self.assertEqual(rejected.state, DatasetAdmissionState.REJECTED)
        self.assertEqual(rejected.reason_code, "XLSX_ACTIVE_CONTENT_FORBIDDEN")
    def test_cross_tenant_lookup_fails_closed(self):
        payload = build_xlsx()
        record = self.registry.declare(
            tenant=self.tenant,
            declaration=declaration(self.tenant, payload),
        )
        with self.assertRaises(AdmissionError) as error:
            self.registry.get(
                tenant=self.other,
                dataset_id=record.declaration.dataset_id,
            )
        self.assertEqual(error.exception.code, "DATASET_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
