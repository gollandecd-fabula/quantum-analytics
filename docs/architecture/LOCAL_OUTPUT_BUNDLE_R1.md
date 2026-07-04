# Local output bundle R1

Status: `INTEGRATION_BUILD_R1 / UNIT_2_3_A`

## Single source of truth

The local output bundle is built once from the admitted source-bridge result and its recommendation bundle. JSON, Excel and HTML renderers consume the same immutable document and do not recalculate marketplace or financial metrics.

The bundle contains:

- dataset and source identity;
- run status;
- source-bridge analysis;
- policy-bound recommendations;
- limitations;
- canonical SHA-256 content hash.

Raw marketplace rows, raw payloads and source-row collections are forbidden recursively.

## Produced files

The atomic writer creates one local directory with:

- `quantum_result.json`;
- `recommendations.json`;
- `Quantum_Report.xlsx`;
- `dashboard.html`;
- `evidence_manifest.json`.

The evidence manifest records size and SHA-256 for the first four artifacts and excludes itself from that list.

## Excel

The XLSX writer is dependency-free and deterministic. It creates valid OOXML sheets:

- `Сводка`;
- `Показатели`;
- `Рекомендации`;
- `Ограничения`;
- `Источники`.

Values are written as inline strings, so source text cannot become an Excel formula. ZIP entry timestamps are fixed for deterministic bytes.

## Dashboard

The HTML dashboard is self-contained, uses no CDN or external library, and performs no network request. It includes metric and recommendation tables plus local search, severity and category filters.

## Failure isolation

The Windows integration wrapper returns a structured output error without exposing exception messages. Output failure must not change source admission or source-bridge status.
