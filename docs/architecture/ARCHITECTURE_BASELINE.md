# Quantum Architecture Baseline — Foundation Draft

Status: `DRAFT`
Risk class: `R1 documentation`; implementation remains blocked.

## Architecture style

Modular monolith with two runtime entry points:

1. API Service
2. Worker Service

They share:

- one repository;
- one domain model;
- one relational database;
- one migration stream;
- one release version;
- explicit internal module boundaries.

This is not a microservice architecture.

## Core flow

```text
Marketplace Adapter
→ Autonomous Data Intake
→ Immutable Raw Storage
→ Schema Registry
→ Normalization
→ Universal Product Master
→ Canonical Event Ledger
→ Versioned Calculation Rules
→ Reconciliation
→ Financial Analytics
→ Analytics Validity
→ Decision Support
→ Dashboard and Exports
```

## Foundation runtime boundaries

### API Service

- authenticated user-facing API;
- upload initiation and status;
- configuration profile management;
- metric and evidence queries;
- Exception Inbox;
- no marketplace write methods.

### Worker Service

- file fingerprinting;
- schema detection;
- quarantine;
- normalization;
- idempotent event publication;
- reconciliation jobs;
- recalculation jobs;
- evidence materialization;
- retry and Dead Letter Queue.

## Persistence baseline

- PostgreSQL for durable relational state;
- object/file storage for immutable source files and derived diagnostics;
- SQLite permitted only for isolated local tests;
- Redis is not required until load evidence demonstrates need.

## Explicitly deferred

- OpenAI Agents SDK runtime as a production subsystem;
- GitHub App webhook processing;
- autonomous branch, commit, PR, check-run, or merge operations;
- marketplace write tokens and methods;
- Kubernetes and independent microservices.

## Mandatory trust boundaries

- source files are untrusted;
- model output is not authority;
- financial rules require versioned snapshots;
- no production secrets inside implementation sandboxes;
- dependent calculations fail closed on missing or conflicting inputs;
- published snapshots are immutable and restated by new versions.
