# Local output bundle R1

Status: `INTEGRATION_BUILD_R1 / UNIT_2_3`

## Purpose

The local output bundle is the immutable, privacy-checked source of truth for every user-facing output. JSON, XLSX and HTML renderers consume the same canonical document and never recalculate marketplace or financial metrics.

The bundle contains:

- dataset, source and run identity;
- admitted source-bridge analysis;
- governed finance-kernel result, when available;
- reconciliation state and differences;
- policy-bound recommendations;
- data-quality and blocked-input state;
- calculation, policy and rounding references;
- source, calculation, recommendation and runtime provenance;
- limitations;
- canonical SHA-256 content hash.

Raw marketplace rows, workbook bytes, raw payloads and source-row collections are recursively forbidden. Missing sections remain explicit `NOT_AVAILABLE` or blocked states; they are never converted to zero.

## Single implementation paths

- `quantum.outputs.local_bundle` builds and validates the immutable document.
- `quantum.outputs.xlsx_report` renders deterministic OOXML from the bundle.
- `quantum.outputs.dashboard` renders the self-contained offline dashboard.
- `quantum.outputs.writer` performs transactional directory publication and verification.
- compatibility wrappers in `local_bundle` delegate to those canonical modules and contain no duplicate renderer or writer logic.

## Produced files

One immutable directory is named from the dataset identifier and bundle-hash prefix. It contains:

- `quantum_result.json`;
- `recommendations.json`;
- `Quantum_Report.xlsx`;
- `dashboard.html`;
- `evidence_manifest.json`.

The evidence manifest records the size and SHA-256 of the first four artifacts and excludes itself. A repeated run with the same canonical bundle reuses the verified directory. A conflicting or modified directory is rejected.

Publication uses a staging directory, file and directory `fsync` where supported, full verification, and one final directory rename. A failure removes staging artifacts and does not leave a partially published bundle.

## Excel contract

The detailed management presentation, cell typing, formatting, chart, navigation and security contract is defined in `EXCEL_REPORT_R1.md`.

The deterministic dependency-free XLSX contains exactly:

1. `Управленческое резюме`;
2. `Рекомендации`;
3. `Финансы по товарам`;
4. `Продажи`;
5. `Реклама`;
6. `Возвраты`;
7. `Остатки и хранение`;
8. `Расходы`;
9. `Качество данных`;
10. `Параметры расчёта`;
11. `Источники данных`;
12. `Журнал изменений`.

The current source bridge is aggregate-level, so product-level sheets expose verified aggregate metrics or an explicit source/mapping requirement. The renderer does not invent SKU allocation. Valid governed numbers are emitted as numeric cells; missing or blocked values remain explicit text states. Source text is emitted as `inlineStr` and cannot become a cell formula. Worksheet cell formulas are forbidden, the chart uses literal caches without formula references, and ZIP timestamps are fixed for deterministic bytes.

## Dashboard contract

The HTML dashboard is self-contained, uses no CDN or external library and performs no network request. It contains:

- core financial KPI cards;
- an offline financial bar visualization;
- governed finance and source metrics;
- recommendation search and severity, priority and category filters;
- action, reason, current and forecast effects, confidence, evidence and limitations;
- data-quality and provenance controls;
- bundle and source hashes.

## HOME_LOCAL integration

After the source bridge and recommendations are attached, `windows_runner` automatically invokes the Windows output adapter. The result is stored in the primary report under `output_bundle`, while the console summary exposes output status and directory.

Output generation is fail-isolated. It cannot change admission, finance or reconciliation status and cannot enable marketplace writes. Error responses contain a stable reason code and exception type but not exception messages or sensitive paths.

## Verification

Directory verification rejects:

- missing, extra or symlinked artifacts;
- invalid manifest fields or hashes;
- artifact size or SHA-256 mismatch;
- bundle/recommendation disagreement;
- dashboard not bound to the bundle hash;
- unexpected XLSX sheets;
- worksheet cell formulas;
- malformed JSON, HTML binding or OOXML.
