# ADR-003 — Foundation Technology Baseline

Status: `ACCEPTED_WITHIN_STAGE_A5`
Date: 2026-06-27
Risk class: `R1`

## Context

The project has no connected source repository and no previously approved application
framework. A5 requires executable API and Worker entry points, persistence boundaries,
migration discipline, and baseline CI without creating unnecessary dependency or
supply-chain risk.

## Decision

Use Python 3.12+ and the standard library for the initial foundation skeleton.

The foundation includes:

- one Python package;
- API and Worker entry points;
- domain invariants;
- ports for raw storage and event persistence;
- immutable local raw-storage adapter for tests;
- PostgreSQL DDL migration;
- standard-library `unittest`;
- local CI runner.

No third-party runtime package is introduced in A5.

## Rationale

- reversible technology choice;
- deterministic local validation;
- no dependency pinning before a dedicated repository exists;
- no hidden network access;
- no premature framework commitment;
- domain contracts remain reusable if FastAPI, Django, Litestar, or another delivery
  framework is approved later.

## Consequences

The A5 API is a technical-health skeleton, not a production web API.
Authentication, database drivers, ORM, migrations runner, task queue, and production
server remain unimplemented and release-blocking.
