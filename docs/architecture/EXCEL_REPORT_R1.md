# Excel report R1

Status: `INTEGRATION_BUILD_R1 / UNIT_2_4`

## Purpose

`Quantum_Report.xlsx` is the local management workbook produced from the immutable output bundle. It does not recalculate marketplace or financial metrics. Every displayed value comes from the governed bundle created by Unit 2.3.

The renderer remains dependency-free at runtime and writes deterministic OOXML directly. No spreadsheet library is added to the HOME_LOCAL package.

## Workbook contract

The workbook contains exactly twelve sheets in this order:

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

## Management summary

The first sheet contains:

- report title and generated-at/source metadata;
- KPI cards for net profit, profit per sold unit, profitability and sold units;
- semantic red/green/neutral KPI states;
- a financial-structure table using governed source/calculation metrics;
- a literal cached column chart with no chart formulas or worksheet references;
- run, reconciliation, recommendation, blocked-metric, publication and marketplace-write controls;
- internal workbook navigation;
- bundle/source identity, policy reference and SHA-256 control values.

Positive expense amounts are not coloured as positive business outcomes. Expense rows use an amber semantic style; negative values use red conditional formatting.

## Data sheets

All data sheets use a consistent presentation layer:

- two-row title band;
- internal link back to the management summary;
- dataset, generated-at and bundle metadata strip;
- frozen header row;
- frozen management columns where appropriate;
- auto-filtered table range;
- bounded column widths and wrapped long text;
- increased row height for recommendation/evidence text;
- sheet-specific tab colour;
- print margins and fit-to-width settings.

The recommendations sheet retains all nineteen contract fields. Management fields appear first; IDs, action codes, states and currency metadata remain available to the right.

## Cell typing and formats

Valid governed values are emitted as numeric OOXML cells rather than strings.

- money: `#,##0.00 ₽` with red negative format;
- ratios/rates: percentage format;
- item/count metrics: integer format;
- other numeric values: decimal format;
- booleans: boolean cells;
- hashes and serialized policy/provenance values: wrapped technical text.

Missing, blocked or unavailable values remain explicit text states. The renderer never converts them to zero.

## Security and integrity

- source text is always written as `inlineStr`, so text beginning with `=` cannot become a cell formula;
- worksheet cell formula elements are forbidden and verified namespace-aware;
- conditional-format formulas are renderer-owned static rules and never contain source text;
- the chart uses literal category/value caches and contains no chart formula references;
- hyperlinks are internal workbook locations only;
- no external link, query, macro, VBA or data connection is created;
- fixed ZIP timestamps preserve deterministic bytes;
- the transactional output writer verifies workbook sheets, XML validity and absence of worksheet cell formulas.

## Visual QA

The final candidate was imported and rendered through an independent spreadsheet engine. The following were visually checked:

- management summary;
- recommendations;
- financial results.

Checks covered title hierarchy, KPI number formats, negative/expense colour semantics, row wrapping, frozen management columns, navigation, chart labels and technical-field readability.
