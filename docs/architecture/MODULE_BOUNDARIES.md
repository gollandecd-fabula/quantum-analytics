# Module Boundaries v1

## Domain

Pure business invariants:

- typed states;
- canonical events;
- event links;
- idempotency key construction.

No filesystem, database, HTTP, marketplace, or framework imports.

## Application

Ports and use-case boundaries:

- raw storage;
- source record repository;
- canonical event repository;
- unit of work;
- clock and identifier providers.

## Infrastructure

Adapters:

- immutable local raw storage for foundation tests;
- PostgreSQL schema contract;
- future object storage and database adapters.

## Delivery

- API runtime entry point;
- Worker runtime entry point.

Delivery modules depend inward. Domain modules never depend on delivery or infrastructure.
