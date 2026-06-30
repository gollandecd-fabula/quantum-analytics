from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import unittest
from uuid import uuid4

from quantum.access import TenantContext
from quantum.adapters.wildberries.synthetic import normalize_row
from quantum.domain.idempotency import canonical_json_hash
from quantum.domain.source_rows import ImmutableSourceRow, SourceRowStatus
from quantum.infrastructure.in_memory_canonical_ledger import (
    CanonicalLedgerError,
    InMemoryCanonicalLedger,
)


class P13EventIntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tenant = TenantContext(str(uuid4()), str(uuid4()))
        self.ledger = InMemoryCanonicalLedger()

    def build(
        self,
        *,
        row_id: str,
        operation_id: str,
        operation_type: str,
        product: str,
        quantity: str,
        amount: str,
        revision: str = "1",
        supersedes: str = "",
        reverses: str = "",
    ):
        row = {
            "row_id": row_id,
            "operation_id": operation_id,
            "operation_type": operation_type,
            "event_time": "2026-06-01T10:00:00Z",
            "recognition_time": "2026-06-01T10:05:00Z",
            "product_external_id": product,
            "quantity": quantity,
            "gross_amount": amount,
            "currency": "RUB",
            "revision": revision,
            "supersedes_event_id": supersedes,
            "reversal_of_event_id": reverses,
        }
        source_record_id = f"src-{row_id}"
        normalized = normalize_row(
            row,
            organization_id=self.tenant.tenant_id,
            marketplace_account_id="wb-account",
            import_batch_id="batch",
            source_record_id=source_record_id,
            source_file_sha256="a" * 64,
            schema_version="wb-synthetic-operations-v1",
            adapter_id="wildberries-synthetic",
            adapter_version="1.0",
            trace_id="trace",
            actor="test",
        )
        source = ImmutableSourceRow(
            source_record_id=source_record_id,
            tenant_id=self.tenant.tenant_id,
            raw_file_id=str(uuid4()),
            source_file_sha256="a" * 64,
            import_batch_id="batch",
            row_number=int(row_id) + 1,
            source_row_key=normalized.source_row_key,
            raw_row_hash=canonical_json_hash(row),
            raw_payload=row,
            structural_fingerprint={"sha256": "b" * 64},
            semantic_fingerprint={"sha256": "c" * 64},
            validation_status=SourceRowStatus.VALID,
            diagnostics=(),
            adapter_id="wildberries-synthetic",
            adapter_version="1.0",
            schema_version="wb-synthetic-operations-v1",
            ingested_at=datetime(2026, 6, 30, tzinfo=UTC),
        )
        return source, normalized.event

    def test_payload_must_match_semantic_hash(self) -> None:
        source, event = self.build(
            row_id="1",
            operation_id="sale-1",
            operation_type="SALE",
            product="product-a",
            quantity="1",
            amount="1000.00",
        )
        payload = {key: dict(value) for key, value in event.payload.items()}
        payload["quantity"]["value"] = 2
        tampered = replace(event, payload=payload)
        with self.assertRaisesRegex(
            CanonicalLedgerError,
            "EVENT_SEMANTIC_HASH_MISMATCH",
        ):
            self.ledger.append(
                tenant=self.tenant,
                source_row=source,
                event=tampered,
            )

    def test_provenance_requires_created_at(self) -> None:
        source, event = self.build(
            row_id="1",
            operation_id="sale-1",
            operation_type="SALE",
            product="product-a",
            quantity="1",
            amount="1000.00",
        )
        provenance = dict(event.provenance)
        provenance.pop("created_at")
        invalid = replace(event, provenance=provenance)
        with self.assertRaisesRegex(
            CanonicalLedgerError,
            "EVENT_PROVENANCE_INCOMPLETE",
        ):
            self.ledger.append(
                tenant=self.tenant,
                source_row=source,
                event=invalid,
            )

    def test_boolean_is_not_an_integer_quantity(self) -> None:
        sale_source, sale = self.build(
            row_id="1",
            operation_id="sale-1",
            operation_type="SALE",
            product="product-a",
            quantity="1",
            amount="1000.00",
        )
        self.ledger.append(
            tenant=self.tenant,
            source_row=sale_source,
            event=sale,
        )
        return_source, returned = self.build(
            row_id="2",
            operation_id="return-1",
            operation_type="RETURN",
            product="product-a",
            quantity="1",
            amount="1000.00",
            reverses=sale.event_id,
        )
        payload = {key: dict(value) for key, value in returned.payload.items()}
        payload["quantity"]["value"] = True
        invalid = replace(
            returned,
            payload=payload,
            semantic_payload_hash=canonical_json_hash(payload),
        )
        with self.assertRaisesRegex(
            CanonicalLedgerError,
            "EVENT_TYPED_INTEGER_INVALID",
        ):
            self.ledger.append(
                tenant=self.tenant,
                source_row=return_source,
                event=invalid,
            )


if __name__ == "__main__":
    unittest.main()
