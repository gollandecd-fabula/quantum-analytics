# ADR-002 — Typed Missing and Conflict States

Status: `ACCEPTED_WITHIN_STAGE_A4`
Date: 2026-06-27
Risk class: `R3`

## Decision

Represent `EMPTY`, `BLOCKED`, `UNAVAILABLE`, `CONFLICT`, `INVALID`, and
`NOT_APPLICABLE` as explicit states distinct from every valid value, including zero.

## Consequences

- dependent calculations fail closed;
- UI can explain why a metric is unavailable;
- reconciliation conflicts cannot silently become zero;
- aggregations must disclose excluded states.
