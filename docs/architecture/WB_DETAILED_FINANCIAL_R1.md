# WB detailed financial mapper R1

Status: `INTEGRATION_BUILD_R1 / UNIT_2_1_B`

## Boundary

The mapper consumes row mappings produced from an already admitted Wildberries detailed financial report. It supports the current camelCase Finance API field names and the previous snake_case field names. Direct XLSX row extraction remains a separate adapter boundary.

## Identity and direction

- Event identity uses report ID, report row ID and normalized operation content.
- Container filename, ZIP digest and `srid` are not unique event keys.
- Sale and return direction comes from document type and operation type.
- Sale and return monetary values are normalized by direction using absolute magnitude, so source sign cannot reverse the event.
- Quantities on non-sale operations are ignored.

## Kernel mapping

The mapper produces typed values for:

- gross sale units;
- returned units;
- signed gross sale amount;
- marketplace commission and payment-service costs;
- forward and reverse logistics;
- storage;
- fines and withholdings;
- payout as a separate reconciliation flow.

It does not create a complete finance request until explicit return treatment, discounts, subsidies, advertising, calculation profile, product cost, other expenses and tax inputs are supplied.

Paid acceptance, unclassified logistics, rebilled logistics and unclassified additional payments are preserved as blockers instead of being hidden inside another expense metric.

Raw source rows are not returned.
