# Third-Party Notices — OSS Dependency Admission

Generated: 2026-06-29

This document records prospective components admitted for future Quantum Analytics
implementation. This stage does **not** install, vendor, bundle, or execute any listed
third-party package. Exact installation, lock files, distribution hashes, transitive
license review, and current vulnerability review remain mandatory in the implementation
stage that first introduces each component.

| Component | Candidate version | License | Admission status | Intended boundary |
|---|---:|---|---|---|
| DuckDB | 1.5.4 | MIT | Approved for future integration | B2 analytical SQL and reconciliation |
| Polars | 1.42.0 | MIT | Approved for future integration | ingestion and normalization |
| Pandera | 0.32.0 | MIT | Approved for future integration | dataframe contracts and quarantine |
| Hypothesis | 6.155.7 | MPL-2.0 | Approved for development/testing only | property-based tests |
| FastAPI | 0.138.1 | MIT | Approved for future integration | B4 API transport |
| Pydantic | 2.13.4 | MIT | Approved for future integration | typed boundaries and DTO validation |
| React-admin | 5.15.1 | MIT | Registry confirmation required | B5 operational UI |
| Apache ECharts | 6.1.0 | Apache-2.0 | Registry confirmation required | B6 visualization |
| wbsdk | 1.2.8 | MIT | Audit required; not approved for runtime | isolated WB read-only adapter candidate |

## Mandatory restrictions

- No component may replace Quantum financial contracts, Decimal semantics, Evidence
  Chain, tenant isolation, or authorization controls.
- No marketplace write operation is admitted.
- `wbsdk` cannot be imported by domain services and cannot enter runtime dependencies
  before the dedicated source, endpoint, security, and read-only facade audit passes.
- GPL/AGPL-family source code identified during research is architecture reference only
  unless separately approved.
- Copyright and license notices must be preserved when a component is installed or
  distributed.
