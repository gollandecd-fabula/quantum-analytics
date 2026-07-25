from __future__ import annotations

import unittest

from quantum.application.finance_profile import (
    FinanceProfile,
    ProductRecord,
    build_profile,
    calculate_by_group,
    confirm_profile,
    validate_profile,
)


def _row(
    *,
    operation: str = "Продажа",
    vendor_code: str = "KNOWN",
    row_id: str = "1",
) -> dict[str, str]:
    sale = operation == "Продажа"
    return {
        "reportId": "77",
        "rrdId": row_id,
        "dateFrom": "2026-07-01",
        "dateTo": "2026-07-07",
        "currency": "RUB",
        "vendorCode": vendor_code,
        "techSize": "M",
        "sku": "460000000001",
        "docTypeName": "Продажа" if sale else "",
        "sellerOperName": operation,
        "quantity": "2" if sale else "0",
        "retailAmount": "2000" if sale else "0",
        "ppvzSalesCommission": "200" if sale else "0",
        "forPay": "1680" if sale else "0",
        "ppvzReward": "0",
        "acquiringFee": "0",
        "deliveryAmount": "1" if sale else "0",
        "returnAmount": "0",
        "deliveryService": "100" if sale else "0",
        "paidStorage": "0",
        "penalty": "0",
        "deduction": "0",
        "paidAcceptance": "0",
        "rebillLogisticCost": "0",
        "additionalPayment": "0",
        "orderDt": "2026-07-01" if sale else "",
        "saleDt": "2026-07-02" if sale else "",
        "srid": "event-" + row_id,
    }


def _profile(
    *,
    tax_base: str = "gross_sales_amount",
    idle_group: bool = False,
) -> FinanceProfile:
    products = [
        ProductRecord("KNOWN", "Товар", "Основная", "one.xlsx")
    ]
    if idle_group:
        products.append(
            ProductRecord(
                "IDLE",
                "Без продаж",
                "Неактивная",
                "one.xlsx",
            )
        )
    profile = build_profile(tuple(products))
    profile.tax_rate_percent = "6"
    profile.tax_base_metric_id = tax_base
    profile.other_expense_per_unit = "40"
    for group in profile.groups.values():
        group.cost_per_unit = "400"
        group.resalable_returned_units = "0"
        group.compensated_returned_units = "0"
        group.return_compensation_amount = "0"
        group.discounts_amount = "0"
        group.subsidies_amount = "0"
        group.advertising_amount = "0"
    confirm_profile(profile)
    return profile


class PlateauM2FinancialIntegrationTests(unittest.TestCase):
    def test_legacy_profile_requires_explicit_tax_base_reconfirmation(
        self,
    ) -> None:
        current = _profile()
        payload = current.to_dict()
        payload["schema_version"] = (
            "quantum-home-local-finance-profile-v1"
        )
        payload.pop("tax_base_metric_id", None)
        payload["confirmed"] = True
        restored = FinanceProfile.from_dict(payload)
        self.assertIsNone(restored.tax_base_metric_id)
        self.assertFalse(restored.confirmed)
        self.assertIn("Налоговая база", validate_profile(restored))

    def test_service_expense_without_sku_is_included(self) -> None:
        storage = _row(
            operation="Хранение",
            vendor_code="",
            row_id="2",
        )
        storage["paidStorage"] = "50"
        result = calculate_by_group(
            detailed_rows=(_row(), storage),
            profile=_profile(),
            organization_id="tenant-home-local",
            source_id="dataset:test",
            source_sha256="a" * 64,
        )
        self.assertEqual("CALCULATED", result.status)
        self.assertEqual(
            "1650.00",
            result.totals["net_marketplace_income_amount"],
        )
        self.assertEqual("650.00", result.totals["net_profit_amount"])
        self.assertIn(
            "Расходы Wildberries без артикула",
            [item.group_name for item in result.group_results],
        )

    def test_net_income_tax_base_uses_period_total(self) -> None:
        storage = _row(
            operation="Хранение",
            vendor_code="",
            row_id="2",
        )
        storage["paidStorage"] = "50"
        result = calculate_by_group(
            detailed_rows=(_row(), storage),
            profile=_profile(
                tax_base="net_marketplace_income_amount"
            ),
            organization_id="tenant-home-local",
            source_id="dataset:test",
            source_sha256="b" * 64,
        )
        self.assertEqual("CALCULATED", result.status)
        self.assertEqual("99.00", result.totals["tax_amount"])
        self.assertEqual("671.00", result.totals["net_profit_amount"])

    def test_unknown_nonblank_product_still_blocks(self) -> None:
        result = calculate_by_group(
            detailed_rows=(_row(vendor_code="UNKNOWN"),),
            profile=_profile(),
            organization_id="tenant-home-local",
            source_id="dataset:test",
            source_sha256="c" * 64,
        )
        self.assertEqual("CALCULATION_BLOCKED", result.status)
        self.assertEqual(
            ("UNKNOWN_PRODUCT_FINANCIAL_ROWS:1",),
            result.missing_inputs,
        )

    def test_physical_sale_without_sku_blocks(self) -> None:
        result = calculate_by_group(
            detailed_rows=(_row(vendor_code=""),),
            profile=_profile(),
            organization_id="tenant-home-local",
            source_id="dataset:test",
            source_sha256="d" * 64,
        )
        self.assertEqual("CALCULATION_BLOCKED", result.status)
        self.assertEqual(
            ("UNATTRIBUTED_PHYSICAL_ROWS:1",),
            result.missing_inputs,
        )

    def test_zero_activity_group_is_valid(self) -> None:
        result = calculate_by_group(
            detailed_rows=(_row(),),
            profile=_profile(idle_group=True),
            organization_id="tenant-home-local",
            source_id="dataset:test",
            source_sha256="e" * 64,
        )
        self.assertEqual("CALCULATED", result.status)
        idle = next(
            item
            for item in result.group_results
            if item.group_name == "Неактивная"
        )
        self.assertEqual("VALID", idle.state)
        self.assertEqual(("ZERO_ACTIVITY",), idle.reason_codes)


if __name__ == "__main__":
    unittest.main()
