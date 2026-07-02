import unittest

from quantum.ingestion.admission import StorageEnvironment
from tests.p16_fixtures import *  # noqa: F403


class P16LocalStorageEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.tenant = TenantContext("tenant-local", "account-local")
        self.registry = RealDatasetAdmissionRegistry()
        self.payload = build_xlsx()
        declared = self.registry.declare(
            tenant=self.tenant,
            declaration=declaration(self.tenant, self.payload),
        )
        self.validated = self.registry.inspect_and_validate(
            tenant=self.tenant,
            dataset_id=declared.declaration.dataset_id,
            payload=self.payload,
            policy=policy(),
            observed_at=NOW + timedelta(minutes=1),
        )

    def _admit(self, **storage_overrides):
        return self.registry.admit(
            tenant=self.tenant,
            dataset_id=self.validated.declaration.dataset_id,
            dataset_control_evidence=dataset_evidence(
                self.tenant,
                self.validated,
            ),
            storage_evidence=evidence(
                self.tenant,
                self.validated,
                **storage_overrides,
            ),
            admitted_at=NOW + timedelta(minutes=2),
        )

    def test_local_loopback_storage_does_not_require_local_encryption(self):
        admitted = self._admit(
            storage_environment=StorageEnvironment.LOCAL_SINGLE_USER,
            loopback_only=True,
            transport_encrypted=False,
            encryption_at_rest=False,
        )
        self.assertEqual(admitted.state, DatasetAdmissionState.ADMITTED)

    def test_local_storage_without_loopback_fails_closed(self):
        with self.assertRaises(AdmissionError) as error:
            self._admit(
                storage_environment=StorageEnvironment.LOCAL_SINGLE_USER,
                loopback_only=False,
                transport_encrypted=False,
                encryption_at_rest=False,
            )
        self.assertEqual(error.exception.code, "STORAGE_CONTROLS_INCOMPLETE")

    def test_local_exception_does_not_remove_common_storage_controls(self):
        with self.assertRaises(AdmissionError) as error:
            self._admit(
                storage_environment=StorageEnvironment.LOCAL_SINGLE_USER,
                loopback_only=True,
                transport_encrypted=False,
                encryption_at_rest=False,
                least_privilege_credentials=False,
            )
        self.assertEqual(error.exception.code, "STORAGE_CONTROLS_INCOMPLETE")

    def test_hosted_storage_still_requires_tls_and_encryption_at_rest(self):
        cases = (
            {"transport_encrypted": False, "encryption_at_rest": True},
            {"transport_encrypted": True, "encryption_at_rest": False},
        )
        for overrides in cases:
            with self.subTest(**overrides):
                with self.assertRaises(AdmissionError) as error:
                    self._admit(
                        storage_environment=StorageEnvironment.HOSTED_EXTERNAL,
                        loopback_only=False,
                        **overrides,
                    )
                self.assertEqual(
                    error.exception.code,
                    "STORAGE_CONTROLS_INCOMPLETE",
                )

    def test_storage_environment_must_be_typed(self):
        with self.assertRaises(AdmissionError) as error:
            evidence(
                self.tenant,
                self.validated,
                storage_environment="LOCAL_SINGLE_USER",
                loopback_only=True,
                transport_encrypted=False,
                encryption_at_rest=False,
            )
        self.assertEqual(
            error.exception.code,
            "STORAGE_EVIDENCE_ENVIRONMENT_INVALID",
        )


if __name__ == "__main__":
    unittest.main()
