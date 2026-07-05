# Interactive dashboard R1

Status: `INTEGRATION_BUILD_R1 / UNIT_2_5`

## Purpose

`dashboard.html` is a self-contained local management application rendered from the immutable output bundle. It never recalculates marketplace or finance metrics and never contacts an external service.

The dashboard is regenerated automatically after every successful HOME_LOCAL output build. The reload control only reloads the current local file; it does not poll or transmit data.

## View contract

The interface contains four views:

1. **Обзор** — governed KPI cards, semantic financial structure, priority actions and calculation status;
2. **Рекомендации** — combined search/filter/sort controls, responsive recommendation cards, current/forecast effects, confidence and evidence counts;
3. **Метрики** — source/calculation scope filters, state/unit filters, sorting and provenance/accounting drill-down;
4. **Качество и контроль** — admission/source/reconciliation states, limitations, parameters, runtime metadata and SHA-256 controls.

The original recommendation reason/evidence text is preserved. Known action, priority, severity and category codes receive Russian presentation labels without changing the governed contract.

## Interaction contract

- tab-style view navigation;
- recommendation search, severity, priority, category and sorting controls;
- metric search, scope, state, unit and numeric sorting controls;
- reset controls and explicit result counts;
- recommendation CSV export;
- recommendation and metric detail drawer;
- Escape and overlay close behavior;
- drawer focus return and keyboard focus containment;
- print view;
- reload of the local generated snapshot;
- internal copy controls for governed hashes.

CSV fields beginning with `=`, `+`, `-` or `@` are prefixed before download so a spreadsheet cannot interpret source text as a formula.

## Financial semantics

Financial values are formatted with the governed unit/currency metadata.

- income is teal;
- expense is amber even when its numeric amount is positive;
- negative result is red;
- profitability is formatted as a percentage;
- missing or blocked values remain explicit text states and are never converted to zero.

## Security boundary

The generated HTML includes a restrictive Content Security Policy:

- `default-src 'none'`;
- inline local style/script only;
- `connect-src 'none'`;
- no objects, frames, base URL or form submission;
- no external `src` or non-fragment `href` references.

Bundle JSON is escaped before embedding. Runtime data is inserted with DOM `textContent`; `innerHTML`, `document.write`, `eval`, network APIs and dynamic remote resources are forbidden by tests and output verification.

The transactional writer verifies:

- dashboard schema version;
- bundle-hash binding;
- bundle-data element;
- required CSP directives;
- absence of URL schemes, external-resource tags and network APIs;
- absence of unsafe DOM sinks.

## Accessibility and responsive behavior

- semantic navigation and tab/tabpanel relationships;
- labelled controls;
- keyboard-operable buttons and filters;
- skip link;
- `aria-live` status toast;
- modal drawer semantics;
- Escape close and focus restoration;
- focus containment while the drawer is open;
- responsive layouts from desktop to 390-pixel mobile width;
- no mobile horizontal page overflow;
- print stylesheet that exposes all report views.

## QA

The final candidate was exercised in Chromium 144 with synthetic governed data.

Verified interactions:

- four KPI cards;
- six recommendations;
- nineteen combined source/calculation metrics;
- navigation between all views;
- recommendation and metric filters;
- sorting and reset;
- recommendation and metric drill-down;
- Escape/close/focus behavior;
- CSV download;
- desktop and mobile rendering;
- zero browser console/page errors;
- zero mobile horizontal overflow.

Screenshots were reviewed for overview, recommendations, metrics, detail drawer and mobile layouts.

## Limitations

The dashboard is a local immutable snapshot, not a continuously running web service. New source data becomes visible after the HOME_LOCAL pipeline creates a new output bundle and the new `dashboard.html` is opened or reloaded.
