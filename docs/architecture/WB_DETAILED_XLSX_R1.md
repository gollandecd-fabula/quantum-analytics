# WB detailed XLSX bridge R1

Status: `INTEGRATION_BUILD_R1 / UNIT_2_1_C`

The bridge connects the existing admitted ZIP/XLSX boundary to the detailed financial mapper. It accepts the schema-discovery record produced during review and verifies the actual sheet name, header row, ordered headers, normalized header SHA-256, column count and data-row count before any financial normalization.

Both direct XLSX and a ZIP containing exactly one XLSX are supported through the existing governed ingestion primitives. Formula cells, unsafe relationships, archive traversal and unsupported containers remain rejected by the existing admission and parser controls.

Raw row mappings exist only inside one function call. The returned report contains the financial aggregate, canonical ledger hash and a compact XLSX binding record, but not the source rows.

The bridge does not relax the blockers produced by the detailed financial mapper. Return condition, return compensation, discounts, subsidies, advertising, calculation profile, product cost, other expenses and tax still require explicit authoritative inputs.
