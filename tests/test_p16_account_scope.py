import unittest

from tests.p16_fixtures import *  # noqa: F403


class P16AccountScopeTests(unittest.TestCase):
    def setUp(self):
        self.owner = TenantContext("tenant-1", "account-1")
        self.non_owner = TenantContext("tenant-1", "account-2")
        self.registry = RealDatasetAdmissionRegistry()
        self.payload = wrap_xlsx(build_xlsx())
        self.record = self.registry.declare(
            tenant=self.owner,
            declaration=declaration(self.owner, self.payload),
        )

    def assert_not_found(self, operation):
        with self.assertRaises(AdmissionError) as error:
            operation()
        self.assertEqual(error.exception.code, "DATASET_NOT_FOUND")

    def test_non_owner_cannot_get_dataset(self):
        self.assert_not_found(
            lambda: self.registry.get(
                tenant=self.non_owner,
                dataset_id=self.record.declaration.dataset_id,
            )
        )

    def test_non_owner_cannot_validate_dataset(self):
        self.assert_not_found(
            lambda: self.registry.inspect_and_validate(
                tenant=self.non_owner,
                dataset_id=self.record.declaration.dataset_id,
                payload=self.payload,
                policy=policy(),
                observed_at=NOW + timedelta(minutes=1),
            )
        )

    def test_non_owner_cannot_read_evidence(self):
        self.assert_not_found(
            lambda: self.registry.evidence_summary(
                tenant=self.non_owner,
                dataset_id=self.record.declaration.dataset_id,
            )
        )

    def test_non_owner_cannot_revoke_dataset(self):
        self.assert_not_found(
            lambda: self.registry.revoke(
                tenant=self.non_owner,
                dataset_id=self.record.declaration.dataset_id,
                reason_code="OWNER_SCOPE_REQUIRED",
                revoked_at=NOW + timedelta(minutes=1),
            )
        )


if __name__ == "__main__":
    unittest.main()
