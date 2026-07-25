from __future__ import annotations

import unittest

from quantum.application.finance_profile import (
    ProductRecord,
    build_profile,
    calculate_by_group,
)


ROW = {
    "reportId": "77",
    "rrdId": "1",
    "dateFrom": "2026-07-01",
    "dateTo": "2026-07-07",
    "currency": "RUB",
    "vendorCode": "KNOWN",
    "techSize": "M",
    "sku": "460000000001",
    "docTypeName": "Продажа",
    "sellerOperName": "Продажа",
    "quantity": "2",
    "retailAmount": "2000",
    "ppvzSalesCommission": "200",
    "forPay": "1680",
    "ppvzReward": "0",
    "acquiringFee": "0",
    "deliveryAmount": "1",
    "returnAmount": "0",
    "deliveryService": "100",
    "paidStorage": "20",
    "penalty": "0",
    "deduction": "0",
    "paidAcceptance": "0",
    "rebillLogisticCost": "0",
    "additionalPayment": "0",
    "orderDt": "2026-07-01",
    "saleDt": "2026-07-02",
    "srid": "blocked-reason-sale",
}


class FinanceProfileBlockReasonTests(unittest.TestCase):
    def test_primary_reason_is_exposed_instead_of_dependent_metrics(self) -> None:
        profile = build_profile(
            (ProductRecord("KNOWN", "Товар", "Футболка", "test"),)
        )
        profile.tax_rate_percent = "6"
        profile.tax_base_metric_id = "gross_sales_amount"
        profile.other_expense_per_unit = "40"
        group = profile.groups["Футболка"]
        group.cost_per_unit = "400"
        group.resalable_returned_units = "0"
        group.compensated_returned_units = "0"
        group.return_compensation_amount = "500"
        group.discounts_amount = "0"
        group.subsidies_amount = "0"
        group.advertising_amount = "0"

        result = calculate_by_group(
            detailed_rows=(ROW,),
            profile=profile,
            organization_id="tenant-invalid-compensation",
            source_id="test:invalid-compensation",
            source_sha256="d" * 64,
        )

        self.assertEqual(result.status, "CALCULATION_BLOCKED")
        self.assertIn(
            "Футболка: RETURN_COMPENSATION_SEMANTICS_INVALID",
            result.missing_inputs,
        )
        self.assertNotIn(
            "Футболка: net_marketplace_income_amount",
            result.missing_inputs,
        )
        self.assertNotIn(
            "Футболка: net_profit_amount",
            result.missing_inputs,
        )


if __name__ == "__main__":
    unittest.main()
