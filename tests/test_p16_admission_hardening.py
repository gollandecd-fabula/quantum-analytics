import unittest

from tests.p16_fixtures import *  # noqa: F403


class P16AdmissionHardeningTests(unittest.TestCase):
    def setUp(self):
        self.tenant = TenantContext("tenant-1", "account-1")
        self.other = TenantContext("tenant-2", "account-2")
        self.registry = RealDatasetAdmissionRegistry()
    def test_dataset_controls_are_mandatory_and_bound(self):
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
                dataset_control_evidence=dataset_evidence(
                    self.tenant,
                    validated,
                    malware_scan_clean=False,
                ),
                storage_evidence=evidence(self.tenant, validated),
                admitted_at=NOW + timedelta(minutes=2),
            )
        self.assertEqual(error.exception.code, "DATASET_CONTROLS_INCOMPLETE")
        with self.assertRaises(AdmissionError) as error:
            self.registry.admit(
                tenant=self.tenant,
                dataset_id=record.declaration.dataset_id,
                dataset_control_evidence=dataset_evidence(
                    self.tenant,
                    validated,
                    dataset_id=str(uuid4()),
                ),
                storage_evidence=evidence(self.tenant, validated),
                admitted_at=NOW + timedelta(minutes=2),
            )
        self.assertEqual(error.exception.code, "DATASET_EVIDENCE_DATASET_MISMATCH")
    def test_stale_evidence_is_rejected(self):
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
            observed_at=NOW + timedelta(minutes=2),
        )
        with self.assertRaises(AdmissionError) as error:
            self.registry.admit(
                tenant=self.tenant,
                dataset_id=record.declaration.dataset_id,
                dataset_control_evidence=dataset_evidence(
                    self.tenant,
                    validated,
                    verified_at=NOW + timedelta(minutes=1),
                ),
                storage_evidence=evidence(
                    self.tenant,
                    validated,
                    verified_at=NOW + timedelta(minutes=2),
                ),
                admitted_at=NOW + timedelta(minutes=3),
            )
        self.assertEqual(error.exception.code, "DATASET_EVIDENCE_STALE")
    def test_decision_time_cannot_move_backwards(self):
        payload = build_xlsx()
        record = self.registry.declare(
            tenant=self.tenant,
            declaration=declaration(self.tenant, payload),
        )
        with self.assertRaises(AdmissionError) as error:
            self.registry.inspect_and_validate(
                tenant=self.tenant,
                dataset_id=record.declaration.dataset_id,
                payload=payload,
                policy=policy(),
                observed_at=NOW - timedelta(seconds=1),
            )
        self.assertEqual(error.exception.code, "DATASET_DECISION_TIME_REGRESSION")
    def test_transport_encryption_is_mandatory(self):
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
                    transport_encrypted=False,
                ),
                admitted_at=NOW + timedelta(minutes=2),
            )
        self.assertEqual(error.exception.code, "STORAGE_CONTROLS_INCOMPLETE")


if __name__ == "__main__":
    unittest.main()
