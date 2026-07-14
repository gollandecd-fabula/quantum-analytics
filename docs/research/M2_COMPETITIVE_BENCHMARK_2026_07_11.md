# MILESTONE 2 — Competitive Research & Benchmark

**Date:** 2026-07-11  
**Scope:** research evidence only; no runtime implementation  
**Branch target:** `fix/quantum-one-click-stable-release`  
**Marketplace writes:** disabled  
**M2 Red Team verdict:** `PASS_WITH_LIMITATIONS`

## 1. Executive conclusion

Quantum should not imitate a competitor's all-in-one product. The strongest combined pattern is:

1. one prioritized **Decision Center**;
2. one marketplace-neutral semantic metric layer;
3. profit-first SKU and inventory decisions;
4. anomaly → cause → evidence → recommended action;
5. competitor and SEO estimates shown only as preliminary hypotheses;
6. AI limited to explanation and recommendation;
7. no automatic marketplace execution.

The benchmark includes **7 global platforms** and **6 WB/Ozon-oriented services**. Scores below measure only the fit of publicly documented patterns to Quantum. They do not measure product quality, factual accuracy, security, pricing or procurement suitability.

## 2. Methodology

Only official public product pages were used for scored capability claims. Each criterion is rated from 0 to 4 and converted to a weighted 0–100 fit score.

| Criterion | Weight |
|---|---:|
| Decision Center / action prioritization | 15% |
| Profit and financial analytics | 15% |
| Data unification / semantic layer | 10% |
| Root-cause explanation | 10% |
| Forecasting / anomaly detection | 8% |
| Marketplace / competitor intelligence | 8% |
| Advertising / SEO analytics | 8% |
| Inventory / supply planning | 6% |
| Multi-marketplace architecture | 6% |
| Evidence / auditability | 5% |
| Custom reports / exports | 3% |
| UI / visualization quality | 3% |
| Recommendation-only compatibility | 2% |
| Local/privacy/offline fit | 1% |

### Evidence limitations

- No demo account or hands-on product validation was performed.
- No vendor calculation was reconciled against a known financial truth set.
- No pricing, SLA, accessibility, browser-render or load test was performed.
- Vendor marketing and security statements remain unverified assertions.
- External marketplace estimates are not internal facts and must carry provenance and confidence.
- Public capabilities can change after 2026-07-11.

## 3. Global platforms

| Platform | Fit /100 | Evidence | Publicly documented pattern |
|---|---:|---|---|
| Triple Whale | 75.0 | HIGH | Unified ecommerce data, measurement, dashboards, custom BI and AI-driven action planning. |
| Northbeam | 59.0 | HIGH | Marketing intelligence focused on multi-touch attribution, incrementality, MMM, product and creative analytics. |
| Daasity | 65.8 | HIGH | Omnichannel analytics combining sales, marketing and inventory with managed data infrastructure. |
| Polar Analytics | 84.5 | HIGH | Commerce BI with connectors, semantic layer, warehouse, incrementality and AI analyst/media/inventory agents. |
| Glew | 67.0 | HIGH | Commerce data platform with automated ELT, validation, warehouse, integrations and customizable analytics. |
| DataHawk | 86.2 | HIGH | Marketplace analytics for sales, ads, SEO, inventory and profitability, with issue detection and next-action guidance. |
| Pacvue | 84.0 | HIGH | Commerce operations and media platform spanning digital shelf, measurement, competitive intelligence and automation. |

### Global ranking

1. **DataHawk** — 86.2
2. **Polar Analytics** — 84.5
3. **Pacvue** — 84.0
4. **Triple Whale** — 75.0
5. **Glew** — 67.0
6. **Daasity** — 65.8
7. **Northbeam** — 59.0

## 4. Wildberries/Ozon-oriented services

| Service | Fit /100 | Evidence | Publicly documented pattern |
|---|---:|---|---|
| MPSTATS | 76.8 | HIGH | Marketplace analytics for WB, Ozon and Yandex Market, including niches, competitors, ads, SKU audits and AI tools. |
| Moneyplace | 73.5 | HIGH | Marketplace analytics with financial dashboards, unit economics, competitor tracking, SEO and ad automation. |
| MarketGuru | 82.8 | HIGH | WB-focused analytics, finance, SEO, ads, reviews, inventory and AI recommendations. |
| Маяк | 68.2 | HIGH | WB/Ozon internal and external analytics, advertising, supply planning, product and financial analytics. |
| SellerFox | 49.2 | MEDIUM | External marketplace intelligence with product, seller and brand dynamics, charts and cross-market comparisons. |
| Stat4Market | UNSCORED | LOW | The public page identifies WB/Ozon analytics but exposes insufficient verifiable feature detail without client-side execution. |

### Regional ranking

1. **MarketGuru** — 82.8
2. **MPSTATS** — 76.8
3. **Moneyplace** — 73.5
4. **Маяк** — 68.2
5. **SellerFox** — 49.2

`Stat4Market` is deliberately unscored because the accessible public page did not expose enough verifiable feature detail. M2 does not fill the gap with assumptions.

## 5. ADOPT / ADAPT / DEFER / REJECT

| Pattern | Decision | Quantum interpretation |
|---|---|---|
| Prioritized Decision Center | **ADOPT** | The main screen should rank problems and opportunities by expected profit impact, urgency and confidence, then show cause, evidence and next action. |
| Canonical metric and semantic layer | **ADOPT** | A single marketplace-neutral definition of profit, units, returns, stock and advertising metrics prevents conflicting dashboards. |
| Profit-first merchandising and inventory risk | **ADOPT** | Prioritize SKU profit, margin, return burden, storage cost, stock-out and overstock risks over gross revenue. |
| Anomaly and root-cause cards | **ADOPT** | Detect material changes, separate symptom from cause and provide a reproducible evidence trail. |
| External competitor and SEO intelligence | **ADAPT** | Use marketplace estimates only as preliminary hypotheses, never as confirmed internal facts. |
| AI analyst / agent | **ADAPT** | AI may explain evidence, propose scenarios and draft actions, but cannot execute marketplace changes. |
| Attribution, MMM and incrementality | **DEFER** | These methods require sufficient history, controlled data quality and explicit causal assumptions not yet established for the local pilot. |
| Cloud warehouse and reverse ETL | **DEFER** | Useful at larger scale, but conflicts with the present local/offline confidentiality constraint and is unnecessary before stable local workflows. |
| Automatic bids, prices, campaigns, replies or inventory execution | **REJECT** | Current Quantum scope permits recommendations only and keeps marketplace writes disabled. |
| Opaque estimates or hidden financial defaults | **REJECT** | A recommendation cannot be confirmed when required inputs, assumptions or source lineage are missing. |
| All-in-one feature expansion before stability | **REJECT** | Competitive breadth is not a reason to destabilize the existing local pilot or rewrite the architecture. |

## 6. Required Quantum target pattern

### Decision Center card contract

Every prioritized card should contain:

- problem or opportunity;
- expected impact range, not a false point estimate;
- priority and urgency;
- confirmed cause or explicitly marked hypothesis;
- source lineage and confidence;
- affected marketplace, SKU and period;
- recommended next action;
- prerequisites and missing inputs;
- expected result and assumptions;
- a link to detailed evidence and charts.

### Architecture contract

- Business core remains marketplace-neutral.
- WB, Ozon and future marketplaces map into canonical contracts through adapters.
- Financial calculations remain deterministic and fail closed.
- AI does not replace Decimal finance, evidence lineage or tenant isolation.
- Marketplace writes remain disabled.
- External commercial data is not sent to vendors by this research milestone.

## 7. Red Team challenge

The benchmark would be unsafe if interpreted as proof that a vendor's claims are true. M2 therefore rejects these shortcuts:

- ranking vendors as “best” based on marketing pages;
- using competitor estimates as confirmed financial facts;
- copying autonomous execution features into a recommendation-only product;
- copying proprietary UI or workflows;
- using hidden defaults to imitate polished dashboards;
- expanding into every feature before the existing pilot is stable;
- choosing a cloud warehouse before local/privacy requirements are resolved.

## 8. Exit criteria

| Gate | Result |
|---|---|
| 5–7 global platforms | PASS — 7 |
| 5–7 WB/Ozon-oriented services | PASS — 6 |
| Weighted benchmark | PASS |
| ADOPT / ADAPT / DEFER / REJECT matrix | PASS |
| Red Team limitations documented | PASS |
| Runtime implementation | NOT PERFORMED |
| Marketplace writes | DISABLED |
| Procurement decision | NOT MADE |
| Final score 98+ | NOT APPLICABLE BEFORE M9 |

## 9. Official source register

| Platform | Official public source | Evidence tier |
|---|---|---|
| Triple Whale | https://www.triplewhale.com/ | HIGH |
| Northbeam | https://www.northbeam.io/ | HIGH |
| Daasity | https://www.daasity.com/ | HIGH |
| Polar Analytics | https://www.polaranalytics.com/ | HIGH |
| Glew | https://www.glew.io/ | HIGH |
| DataHawk | https://datahawk.co/ | HIGH |
| Pacvue | https://pacvue.com/ | HIGH |
| MPSTATS | https://mpstats.io/ | HIGH |
| Moneyplace | https://moneyplace.io/ | HIGH |
| MarketGuru | https://marketguru.io/ | HIGH |
| Маяк | https://mayak.bz/ | HIGH |
| SellerFox | https://sellerden.ru/sellerfox/ | MEDIUM |
| Stat4Market | https://stat4market.com/ | LOW |
