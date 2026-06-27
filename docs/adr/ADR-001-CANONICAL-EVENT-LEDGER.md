# ADR-001 — Canonical Event Ledger

Status: `ACCEPTED_WITHIN_STAGE_A4`
Date: 2026-06-27
Risk class: `R3`

## Context

Marketplace source files differ structurally and semantically. Financial calculations
must remain reproducible, marketplace-neutral, and resistant to silent source changes.

## Decision

Use an append-only canonical event ledger between normalization and analytics.

Every event has:

- stable business key;
- source row key;
- revision;
- idempotency key;
- event type;
- event and recognition timestamps;
- typed payload;
- provenance;
- optional supersession and reversal links.

## Consequences

Positive:

- historical corrections remain visible;
- multiple marketplace adapters share one domain;
- calculations can be reproduced;
- duplicate prevention is enforceable;
- Evidence Chain is direct.

Costs:

- more storage;
- explicit version and restatement logic;
- more complex reconciliation;
- stronger database constraints required.

## Rejected alternatives

- calculating directly from uploaded spreadsheets;
- mutable fact tables without source record lineage;
- deleting and replacing corrected events;
- marketplace-specific financial tables as the core model.
