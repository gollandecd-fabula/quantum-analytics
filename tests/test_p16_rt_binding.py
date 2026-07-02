import unittest
from tests.p16_fixtures import *  # noqa: F403


class P16RedTeamBindingTests(unittest.TestCase):
    def setUp(self):
        self.tenant = TenantContext("tenant-bind", "account-bind")
        self.registry = RealDatasetAdmissionRegistry()
        payload = build_xlsx()
        declared = self.registry.declare(tenant=self.tenant, declaration=declaration(self.tenant, payload))
        self.validated = self.registry.inspect_and_validate(
            tenant=self.tenant,
            dataset_id=declared.declaration.dataset_id,
            payload=payload,
            policy=policy(),
            observed_at=NOW + timedelta(minutes=1),
        )
        self.dataset_id = declared.declaration.dataset_id

    def _blocked(self, code, **changes):
        with self.assertRaises(AdmissionError) as error:
            self.registry.admit(
                tenant=self.tenant,
                dataset_id=self.dataset_id,
                dataset_control_evidence=dataset_evidence(self.tenant, self.validated, **changes),
                storage_evidence=evidence(self.tenant, self.validated),
                admitted_at=NOW + timedelta(minutes=2),
            )
        self.assertEqual(error.exception.code, code)

    def test_authority_binding(self):
        self._blocked("DATASET_EVIDENCE_AUTHORITY_MISMATCH", owner_authority_reference="different-authority")

    def test_policy_binding(self):
        self._blocked("DATASET_EVIDENCE_POLICY_MISMATCH", policy_content_hash="f" * 64)

    def test_schema_binding(self):
        self._blocked("DATASET_EVIDENCE_SCHEMA_MISMATCH", matched_schema_id="other-schema")


if __name__ == "__main__":
    unittest.main()
