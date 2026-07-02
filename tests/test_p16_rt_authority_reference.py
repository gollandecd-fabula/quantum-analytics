import unittest

from tests.p16_fixtures import *  # noqa: F403
from quantum.ingestion._admission_contracts_v2 import (
    DatasetControlEvidence as DirectDatasetControlEvidence,
)


class P16RedTeamAuthorityReferenceTests(unittest.TestCase):
    def test_policy_and_evidence_accept_same_schema_references(self):
        self.assertIs(DirectDatasetControlEvidence, DatasetControlEvidence)
        tenant = TenantContext("tenant-authority", "account-authority")
        registry = RealDatasetAdmissionRegistry()
        payload = build_xlsx()
        base = policy()
        direct = replace(
            base.schemas[0],
            schema_id="docs/schema/wb-weekly",
            schema_version="v1/reviewed",
            schema_authority_reference="docs/security/schema-v1",
        )
        reviewed_policy = replace(
            base,
            version=base.version + 1,
            schemas=(direct, base.schemas[1]),
        )
        record = registry.declare(
            tenant=tenant,
            declaration=declaration(tenant, payload),
        )
        validated = registry.inspect_and_validate(
            tenant=tenant,
            dataset_id=record.declaration.dataset_id,
            payload=payload,
            policy=reviewed_policy,
            observed_at=NOW + timedelta(minutes=1),
        )
        self.assertEqual(validated.state, DatasetAdmissionState.VALIDATED)
        self.assertEqual(
            validated.inspection.matched_schema_authority_reference,
            "docs/security/schema-v1",
        )
        admitted = registry.admit(
            tenant=tenant,
            dataset_id=validated.declaration.dataset_id,
            dataset_control_evidence=dataset_evidence(tenant, validated),
            storage_evidence=evidence(tenant, validated),
            admitted_at=NOW + timedelta(minutes=2),
        )
        self.assertEqual(admitted.state, DatasetAdmissionState.ADMITTED)


if __name__ == "__main__":
    unittest.main()
