import unittest

from quantum.adapters.wildberries.detailed_financial import (
    WbDetailedFinancialError,
    normalize_detailed_financial_rows,
)


SOURCE_SHA = "a" * 64


def sale_row(**overrides):
    row = {
        "reportId": 706623362,
        "rrdId": 1,
        "dateFrom": "2026-04-27",
        "dateTo": "2026-05-03",
        "currency": "RUB",
        "vendorCode": "iz-507",
        "techSize": "2XL",
        "sku": "460000000001",
        "docTypeName": "Продажа",
        "sellerOperName": "Продажа",
        "quantity": 1,
        "retailAmount": "1764",
        "ppvzSalesCommission": "327",
        "forPay": "1200",
        "ppvzReward": "70",
        "acquiringFee": "80",
        "deliveryAmount": 0,
        "returnAmount": 0,
        "deliveryService": "0",
        "paidStorage": "0",
        "penalty": "0",
        "deduction": "0",
        "paidAcceptance": "0",
        "rebillLogisticCost": "0",
        "additionalPayment": "0",
        "orderDt": "2026-04-24T00:00:00Z",
        "saleDt": "2026-04-27T00:00:00Z",
        "srid": "shared-srid",
    }
    row.update(overrides)
    return row


def return_row(**overrides):
    row = sale_row(
        rrdId=2,
        docTypeName="Возврат",
        sellerOperName="Возврат",
        retailAmount="-500",
        ppvzSalesCommission="-50",
        ppvzReward="-5",
        acquiringFee="-10",
        forPay="-300",
    )
    row.update(overrides)
    return row


def logistics_row(**overrides):
    row = sale_row(
        rrdId=3,
        docTypeName="",
        sellerOperName="Логистика",
        quantity=8,
        retailAmount="0",
        ppvzSalesCommission="0",
        ppvzReward="0",
        acquiringFee="0",
        forPay="0",
        deliveryAmount=1,
        returnAmount=0,
        deliveryService="110.17",
        vendorCode="",
        techSize="",
        sku="",
    )
    row.update(overrides)
    return row


class WbDetailedFinancialTests(unittest.TestCase):
    def test_sale_return_direction_comes_from_document_not_sign(self):
        result = normalize_detailed_financial_rows(
            [sale_row(), return_row()],
            source_id="report-706623362",
            source_sha256=SOURCE_SHA,
        )
        metrics = result["observed_metrics"]
        self.assertEqual(metrics["gross_sales_units"]["value"], "1")
        self.assertEqual(metrics["returned_units"]["value"], "1")
        self.assertEqual(metrics["gross_sales_amount"]["value"], "1264.00")
        self.assertEqual(metrics["payout_amount"]["value"], "900.00")
        self.assertEqual(
            metrics["marketplace_commission_amount"]["value"],
            "412.00",
        )
        self.assertEqual(result["event_count"], 2)
        self.assertFalse(result["raw_rows_in_report"])

    def test_same_srid_is_allowed_when_rows_are_distinct(self):
        result = normalize_detailed_financial_rows(
            [sale_row(rrdId=1), logistics_row(rrdId=2)],
            source_id="report-706623362",
            source_sha256=SOURCE_SHA,
        )
        self.assertEqual(result["event_count"], 2)
        self.assertEqual(
            result["observed_metrics"]["forward_logistics_amount"]["value"],
            "110.17",
        )

    def test_event_identity_is_independent_of_container_source_id(self):
        first = normalize_detailed_financial_rows(
            [sale_row()],
            source_id="upload-a",
            source_sha256="a" * 64,
        )
        second = normalize_detailed_financial_rows(
            [sale_row()],
            source_id="upload-b",
            source_sha256="b" * 64,
        )
        self.assertEqual(
            first["canonical_ledger_sha256"],
            second["canonical_ledger_sha256"],
        )

    def test_exact_duplicate_is_blocked(self):
        row = sale_row()
        with self.assertRaises(WbDetailedFinancialError) as error:
            normalize_detailed_financial_rows(
                [row, dict(row)],
                source_id="report-706623362",
                source_sha256=SOURCE_SHA,
            )
        self.assertEqual(error.exception.code, "WB_DETAILED_EVENT_DUPLICATE")

    def test_unknown_operation_is_blocked(self):
        with self.assertRaises(WbDetailedFinancialError) as error:
            normalize_detailed_financial_rows(
                [sale_row(sellerOperName="Неизвестная операция")],
                source_id="report-706623362",
                source_sha256=SOURCE_SHA,
            )
        self.assertTrue(
            error.exception.code.startswith(
                "WB_DETAILED_OPERATION_UNSUPPORTED:"
            )
        )

    def test_reverse_logistics_is_classified_from_return_count(self):
        result = normalize_detailed_financial_rows(
            [
                logistics_row(
                    deliveryAmount=0,
                    returnAmount=1,
                    deliveryService="56.50",
                )
            ],
            source_id="report-706623362",
            source_sha256=SOURCE_SHA,
        )
        self.assertEqual(
            result["observed_metrics"]["reverse_logistics_amount"]["value"],
            "56.50",
        )
        self.assertEqual(
            result["observed_metrics"]["forward_logistics_amount"]["value"],
            "0.00",
        )

    def test_acceptance_is_preserved_as_blocker_not_hidden(self):
        result = normalize_detailed_financial_rows(
            [
                sale_row(
                    rrdId=4,
                    docTypeName="",
                    sellerOperName="Обработка товара",
                    quantity=0,
                    retailAmount="0",
                    ppvzSalesCommission="0",
                    ppvzReward="0",
                    acquiringFee="0",
                    forPay="0",
                    paidAcceptance="1080",
                )
            ],
            source_id="report-706623362",
            source_sha256=SOURCE_SHA,
        )
        self.assertEqual(
            result["unsupported_components"]["paid_acceptance_amount"],
            "1080.00",
        )
        self.assertIn(
            "PAID_ACCEPTANCE_OUTSIDE_KERNEL_EXPENSE_BOUNDARY",
            result["finance_request_reason_codes"],
        )
        self.assertIsNone(result["finance_request"])

    def test_alias_conflict_is_blocked(self):
        row = sale_row()
        row["realizationreport_id"] = 999
        with self.assertRaises(WbDetailedFinancialError) as error:
            normalize_detailed_financial_rows(
                [row],
                source_id="report-706623362",
                source_sha256=SOURCE_SHA,
            )
        self.assertEqual(
            error.exception.code,
            "WB_DETAILED_ALIAS_CONFLICT:report_id",
        )


if __name__ == "__main__":
    unittest.main()
