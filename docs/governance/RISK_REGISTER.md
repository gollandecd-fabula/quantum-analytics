# Risk Register

| ID | Risk | Severity | Status | Treatment |
|---|---|---:|---|---|
| RISK-A-001 | Dedicated GitHub repository unavailable | High | CLOSED | Dedicated repository connected; protected `main` is source of truth |
| RISK-A-002 | Prior Stage 1 artifacts unavailable or incompatible | High | CLOSED_WITH_LIMITATIONS | Recovery and reuse classification completed; unsupported legacy claims are not inherited |
| RISK-A-003 | Two runtime processes drift into microservices | Medium | CONTROLLED | One codebase, domain model, database boundary, and modular-monolith contract |
| RISK-A-004 | Financial meanings differ by source | High | OPEN | Keep Source Authority DRAFT; define reconciliation and verified source contracts in BUILD |
| RISK-A-005 | Unknown Wildberries schemas | Medium | OPEN | Quarantine, diagnostic package, adapter Issue, and representative-file gate |
| RISK-A-006 | Bootstrap imported without branch protection | Medium | CLOSED | `Protect main` ruleset active; PR and `foundation` check required |
| RISK-A-007 | Legacy `C40` leaks a store-specific constant into the universal model | High | MITIGATED_IN_DESIGN | Scoped versioned OTHER_EXPENSE rule; scan and tests must prove no fixed constant |
| RISK-A-008 | Agent architecture is mistaken for analytics architecture | High | MITIGATED_IN_DESIGN | Architecture baseline and module boundaries are authoritative |
| RISK-A-009 | Historical QA is presented as Quantum evidence | High | MITIGATED_IN_GOVERNANCE | Only repository evidence and current CI count as Quantum evidence |
| RISK-A-010 | Incorrect source authority selected before schema inspection | High | CONTROLLED | All real-source authority rows remain DRAFT |
| RISK-A-011 | Empty or unavailable values become zero | Critical | MITIGATED_IN_CONTRACT | Typed-value and UI acceptance contracts distinguish zero from missing states |
| RISK-A-012 | Duplicate events under retry or concurrency | Critical | MITIGATED_IN_CONTRACT | File, source-record, event idempotency and event-id uniqueness controls |
| RISK-A-013 | History is overwritten during corrections | Critical | MITIGATED_IN_CONTRACT | Append-only revisions, reversals, supersession, and restatement |
| RISK-A-014 | Foundation skeleton is mistaken for production API | High | CONTROLLED | README and CURRENT_STATE retain `RELEASE_BLOCKED` and explicit limitations |
| RISK-A-015 | PostgreSQL DDL differs from real driver and transaction behavior | High | OPEN | Require integration tests, migration preflight, rollback, and transaction evidence |
| RISK-A-016 | Local filesystem adapter is mistaken for production object storage | High | OPEN | Implement and prove durable storage before external deployment |
| RISK-A-017 | Framework choice becomes prematurely locked | Medium | CONTROLLED | Keep standard-library/domain boundaries and ADR gate for new dependencies |
| RISK-A-018 | Synthetic schema is mistaken for real Wildberries contract | Critical | CONTROLLED | TEST_ONLY label; representative-file admission and Source Authority gate |
| RISK-A-019 | JSON proof ledger is mistaken for production persistence | High | CONTROLLED | A6-only limitation; PostgreSQL integration remains mandatory |
| RISK-A-020 | Structural fingerprint misses semantic drift | High | MITIGATED_IN_PROOF | Separate semantic fingerprint and validation quarantine |
| RISK-A-021 | Synthetic proof metric is mistaken for production finance | Critical | CONTROLLED | Synthetic label and no active financial profile or source authority |
| RISK-B-001 | A fixed cost, tax, tax base, other expense, allocation, or rounding assumption enters canonical logic | Critical | OPEN | Configurable rule contract, fixed-constant scan, golden tests, and R3 activation gate |
| RISK-B-002 | Overlapping rules double count expenses or select different results nondeterministically | Critical | OPEN | Deterministic precedence, exclusivity, overlap diagnostics, and property tests |
| RISK-B-003 | Intermediate and presentation rounding produce inconsistent financial results | High | OPEN | Versioned rounding policy, decimal arithmetic, golden and differential tests |
| RISK-B-004 | Operational, settlement, and tax-recognition views are silently mixed | Critical | OPEN | Separate result contracts, explicit view labels, and reconciliation tests |
| RISK-B-005 | Return, restock, resale, write-off, loss, or compensation double counts value or cost | Critical | OPEN | Lifecycle state machine, golden paths, conservation properties, and reconciliation |
| RISK-B-006 | Unverified source authority publishes a financially valid result | Critical | OPEN | DRAFT-by-default authority, fail-closed publication, and R3 activation approval |
| RISK-B-007 | Evidence Chain no longer matches the calculation snapshot after rule or event change | High | OPEN | Immutable metric snapshot and version/hash integrity tests |
| RISK-B-008 | Scenario data contaminates Actual reporting | Critical | OPEN | Separate stores/namespaces, mutation guards, and isolation tests |
| RISK-B-009 | UI or export converts BLOCKED, UNAVAILABLE, CONFLICT, or EMPTY to zero | Critical | OPEN | Typed API contract, UI snapshots, export round-trip tests, and accessibility checks |
| RISK-B-010 | Recommendation is presented as certain or executes an external action | High | OPEN | Evidence, confidence, limitations, no-action alternative, and read-only enforcement |
| RISK-B-011 | Authentication or tenant isolation exposes another organization's data | Critical | NOT_STARTED | Threat model, approved-user access, tenant-policy enforcement, and cross-tenant tests |
| RISK-B-012 | Free-tier platform limits break imports, workers, storage, backup, or recovery | High | NOT_STARTED | Railway/Vercel/Cloudflare comparative staging proof and exit plan |
| RISK-B-013 | Implementation actor approves its own financial oracle or R2+ change | High | CONTROLLED | Proposer/verifier separation and protected Pull Request workflow |
| RISK-B-014 | BUILD work uses real commercial data before classification and admission approval | Critical | CONTROLLED | Synthetic-only by default; explicit data-admission gate and no commercial data in GitHub |
| RISK-B-015 | New dependency introduces security, license, cost, or platform lock-in risk | High | OPEN | ADR, vulnerability/license checks, SBOM, provenance, and free-tier impact review |
