# Risk Register

| ID | Risk | Severity | Status | Treatment |
|---|---|---:|---|---|
| RISK-A-001 | Dedicated GitHub repository unavailable | High | OPEN | Create and connect `quantum-analytics` |
| RISK-A-002 | Prior Stage 1 artifacts unavailable or incompatible | High | OPEN | Source recovery and compatibility audit |
| RISK-A-003 | Two runtime processes could drift into microservices | Medium | OPEN | Enforce one codebase, domain model, and database |
| RISK-A-004 | Financial meanings may differ by source | High | OPEN | Source Authority Matrix and reconciliation |
| RISK-A-005 | Unknown WB schemas | Medium | OPEN | Quarantine and adapter Issue |
| RISK-A-006 | Repository bootstrap package could be imported without branch protection | Medium | OPEN | Apply protection before implementation |
| RISK-A-007 | Legacy `C40` leaks LarannA-specific constant into universal model | High | MITIGATED_IN_DESIGN | Replace with scoped versioned rule; test absence of fixed constants |
| RISK-A-008 | Agent architecture is mistaken for analytics architecture | High | MITIGATED_IN_DESIGN | Architecture Baseline explicitly defers GitHub mutation flow |
| RISK-A-009 | Historical QA is presented as Quantum evidence | High | MITIGATED_IN_GOVERNANCE | Evidence transfer prohibition in Reuse Matrix |
| RISK-A-010 | Incorrect source authority selected before schema inspection | High | CONTROLLED | All initial matrix rows remain DRAFT |
| RISK-A-011 | Empty or unavailable values become zero | Critical | MITIGATED_IN_CONTRACT | Typed-value schema rejects non-VALID values with payload |
| RISK-A-012 | Duplicate events under retry or concurrency | Critical | MITIGATED_IN_CONTRACT | Three-level idempotency and database uniqueness requirements |
| RISK-A-013 | History is overwritten during corrections | Critical | MITIGATED_IN_CONTRACT | Append-only revisions, reversals, supersession and restatement |
| RISK-A-014 | Foundation skeleton is mistaken for production API | High | OPEN | Runbook and ADR mark it non-production; release blocked |
| RISK-A-015 | PostgreSQL DDL differs from real driver/transaction behavior | High | OPEN | Require integration tests in later platform work |
| RISK-A-016 | Local filesystem adapter is mistaken for production object storage | High | OPEN | Adapter explicitly foundation-only |
| RISK-A-017 | Framework choice becomes prematurely locked | Medium | CONTROLLED | Standard-library boundary keeps choice reversible |
| RISK-A-018 | Synthetic schema is mistaken for real WB contract | Critical | CONTROLLED | TEST_ONLY; Source Authority remains DRAFT |
| RISK-A-019 | JSON proof ledger is mistaken for production persistence | High | CONTROLLED | Explicit A6-only limitation |
| RISK-A-020 | Structural fingerprint misses semantic drift | High | MITIGATED_IN_PROOF | Separate semantic fingerprint and validation quarantine |
| RISK-A-021 | Proof metric is mistaken for production finance | Critical | CONTROLLED | Synthetic metric ID and explicit limitations |
