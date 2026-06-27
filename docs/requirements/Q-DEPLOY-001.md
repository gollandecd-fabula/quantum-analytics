# Q-DEPLOY-001 — Final Hosting and Access Constraint

Status: `ACTIVE`
Authority: explicit user decision
Risk class: `R2`
Date: 2026-06-27

## Mandatory requirement

The final Quantum Analytics application must be deployed on exactly one approved platform:

- Railway;
- Vercel;
- Cloudflare.

No other production hosting provider may be selected without a new explicit user decision.

## Cost constraint

Development and initial operation must use free plans and free included quotas wherever technically possible. The selected platform must pass a documented free-tier feasibility proof before production selection.

A platform is not considered free-feasible when the required API, worker, database, file storage, authentication, backup, or recovery design depends on recurring paid features.

## Access constraint

The deployed application must not be publicly usable without authorization. Access must be restricted to registered and explicitly approved users.

Minimum controls:

- authenticated sessions;
- disabled-by-default new accounts or invitation/approval workflow;
- organization and tenant isolation;
- role-based authorization;
- account suspension and access revocation;
- no public access to marketplace reports or analytics;
- no secrets or commercial data in the source repository.

Repository visibility and application access are separate controls. A public development repository does not authorize public access to the deployed application.

## Platform evaluation order

### Railway

Evaluate first for compatibility with the current architecture:

- Python API service;
- separate Worker runtime;
- PostgreSQL;
- container-style deployment;
- persistent storage and background processing.

Selection remains conditional on proving that the complete required topology fits within the available free quota.

### Cloudflare

Evaluate as the primary zero-cost rearchitecture alternative:

- Workers or Python Workers;
- D1 or an approved external relational database;
- R2 for source-file storage;
- Queues or Workflows for background processing;
- Access or application-level authentication.

Selection requires an ADR because it may replace PostgreSQL and the current container/worker execution model.

### Vercel

Evaluate for a frontend-centric or stateless-function architecture:

- frontend and preview deployments;
- Python or framework functions for HTTP endpoints;
- external durable database and background-job solution where required.

Selection requires proof that ingestion, durable background work, replay, quarantine, and file processing do not rely on unsupported long-lived processes.

## Selection gate

Before selecting the final platform, produce a comparative evidence matrix covering:

- free-tier recurring cost;
- API runtime compatibility;
- durable worker and queue support;
- relational database semantics;
- immutable source-file storage;
- authentication and private application access;
- backup and restore;
- deployment rollback;
- observability;
- limits for file size, CPU time, memory, request duration, and scheduled work;
- migration cost from the current architecture.

## Acceptance criteria

- One of Railway, Vercel, or Cloudflare is selected by an approved ADR.
- A staging deployment succeeds on the selected platform.
- The application is inaccessible to unapproved users.
- Secrets are stored only in platform secret management.
- Synthetic upload, processing, replay, quarantine, and Evidence Chain pass in staging.
- Free-tier limits and expected consumption are documented.
- A migration path to a paid plan or another approved platform is documented without platform lock-in.
