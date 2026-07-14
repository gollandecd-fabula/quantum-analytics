# WB Windows source dispatch R1

Status: `INTEGRATION_BUILD_R1 / UNIT_2_1_D`

## Execution boundary

The existing HOME_LOCAL Windows runner remains responsible for file selection, malware evidence, source SHA-256 binding, schema review, quarantine and admission. Source analytics starts only after the local pilot report confirms `storage_zone_state = ADMITTED`.

The dispatcher receives the same in-memory payload that was hashed and reviewed before admission. It does not reread the source file, so a later file replacement cannot change the analytic input.

## Dispatch behavior

- The verified supplier-goods header hash routes to the supplier-goods bridge.
- A detailed financial header set routes to the detailed ZIP/XLSX bridge.
- An unknown header set produces `SOURCE_BRIDGE_UNSUPPORTED`.
- A recognized but invalid source produces `SOURCE_BRIDGE_BLOCKED`.
- An unexpected internal exception produces `SOURCE_BRIDGE_ERROR` without exposing its message.

All non-complete outcomes retain `finance_request = null` and `finance_request_state = BLOCKED`. They do not alter the top-level admission result or the admitted source.

## Reviewed source context

When report metadata is absent from workbook rows, the bridge may use only explicit reviewed context:

- report ID from `report_id` or a numeric report marker in the filename;
- period from `reporting_period_start` and `reporting_period_end`;
- currency from explicit `source_currency`.

No currency, cost, tax, return treatment, advertising or other financial value is inferred by default.
