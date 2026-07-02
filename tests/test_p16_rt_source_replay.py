import unittest

from tests.p16_fixtures import *  # noqa: F403


class P16RedTeamSourceReplayTests(unittest.TestCase):
    def setUp(self):
        self.tenant = TenantContext("tenant-source", "account-source")
        self.registry = RealDatasetAdmissionRegistry()

    def test_same_source_can_declare_a_new_reporting_period(self):
        first_payload = build_xlsx(rows=(("1", "SALE", "100.00"),))
        second_payload = build_xlsx(rows=(("2", "SALE", "200.00"),))
        first = declaration(self.tenant, first_payload)
        second = replace(
            declaration(self.tenant, second_payload),
            source_internal_id=first.source_internal_id,
            marketplace=first.marketplace,
            report_type=first.report_type,
            reporting_period_start=date(2026, 6, 8),
            reporting_period_end=date(2026, 6, 14),
            declared_at=NOW + timedelta(days=7),
        )

        first_record = self.registry.declare(
            tenant=self.tenant,
            declaration=first,
        )
        second_record = self.registry.declare(
            tenant=self.tenant,
            declaration=second,
        )

        self.assertNotEqual(
            first_record.declaration.dataset_id,
            second_record.declaration.dataset_id,
        )
        self.assertEqual(
            second_record.declaration.reporting_period_start,
            date(2026, 6, 8),
        )

    def test_same_source_and_period_with_new_bytes_is_replay(self):
        first_payload = build_xlsx(rows=(("1", "SALE", "100.00"),))
        replay_payload = build_xlsx(rows=(("9", "SALE", "900.00"),))
        first = declaration(self.tenant, first_payload)
        replay = replace(
            declaration(self.tenant, replay_payload),
            source_internal_id=first.source_internal_id,
            marketplace=first.marketplace,
            report_type=first.report_type,
            reporting_period_start=first.reporting_period_start,
            reporting_period_end=first.reporting_period_end,
        )
        self.registry.declare(tenant=self.tenant, declaration=first)

        with self.assertRaises(AdmissionError) as error:
            self.registry.declare(
                tenant=self.tenant,
                declaration=replay,
            )
        self.assertEqual(
            error.exception.code,
            "DATASET_SOURCE_REPLAY_DETECTED",
        )


if __name__ == "__main__":
    unittest.main()
