# CURRENT STATE

Date: 2026-07-14
Status: `PLATEAU_RED_TEAM_IN_PROGRESS`
Release status: `RELEASE_BLOCKED`
Working branch: `fix/quantum-plateau-redteam`
Pull request: `#102`
Base branch: `main`
Marketplace writes: `DISABLED`

## Current product

The active user-facing product is a local Windows desktop decision center for
Wildberries reports. The current release surface is not a hosted API/worker
deployment and has no authorized marketplace-write capability.

Main runtime:

- `quantum.application.desktop_center`;
- local Finance Center UI;
- local report admission and immutable storage;
- local finance calculation and local exports.

## Plateau acceptance criteria

A technical plateau candidate requires all of the following on one exact head:

1. zero open P0 defects;
2. zero open P1 defects;
3. all mandatory Linux and Windows CI gates pass;
4. a repeated independent Red Team pass finds no new P0/P1 defect;
5. manifest evidence matches the tracked tree byte-for-byte;
6. self-test fails closed and passes its known-answer controls;
7. the produced installer passes native package tests;
8. marketplace writes remain disabled.

Historical PASS results do not transfer to a later commit.

## Completed milestones

### M0 — Baseline and release integrity

- The previous long-lived release branch was found to be hundreds of commits
ahead of and multiple commits behind `main`.
- Historical evidence was treated as exact-head evidence only, not as proof for
later commits.
- Work was moved to a separate plateau branch and draft PR.

### M1 — Live runtime integration

- Fixed the MRO defect where tested persistence methods were shadowed by a
different active queue implementation.
- Bound report persistence, managed-source switching and requeue behavior to
the actual desktop runtime.
- Added live-class integration tests.

### M2 — Financial orchestration

- Added finance profile schema v2.
- Tax base must be selected explicitly by the user.
- Legacy v1 profiles are migrated as unconfirmed.
- Unknown nonblank product identifiers block calculation.
- Physical sale/return rows without an identifier block calculation.
- Marketplace service rows without an identifier are retained as separate
unallocated WB expenses.
- Zero-activity product groups are valid.
- Tax is calculated once at period level and shown separately from pre-tax
product-group profit.
- M2 exact head passed all mandatory automated gates before later milestones
changed the head.

### M3 — Durable state and privacy

- Report index v2 stores only portable paths controlled by the Quantum root.
- External absolute user paths are not accepted as durable sources.
- Index publication uses staged validation, fsync and bounded replace retry.
- Corrupt index recovery falls back to verified output evidence.
- The financial parser processes the same XLSX bytes that were hashed.
- Application-level XLSX parsing normalizes low-level errors.

### M4 — Schema review and attestations

- Desktop import no longer invents authority or schema attestations.
- The user explicitly confirms authority for the selected batch.
- Each XLSX presents sheet, header row, headers, row count, formulas, reporting
period and SHA-256 before `SchemaReviewed` is forwarded.
- Declined or failed review prevents queue admission.

### M5 — Self-test trustworthiness

- Desktop PASS now depends on nested Finance Center PASS.
- Finance Center self-test executes a known-answer finance calculation,
validates configuration, verifies live MRO, performs a persistence round-trip
and confirms the schema-review gate.
- Self-test CLI returns a nonzero exit code on failure.

## Active milestone

### M6 — Build, documentation and release metadata

In progress:

- standard Python package build surface;
- truthful desktop entry points and version metadata;
- removal of stale Foundation/cloud documentation;
- wheel build smoke test;
- exact-head manifest evidence for M6;
- complete mandatory CI rerun.

## Open release boundaries

The following are not software defects that can be truthfully closed by CI:

- Authenticode signing requires an approved code-signing certificate;
- physical user-pilot evidence requires installation on the target computer;
- the applicable tax regime and tax base require user/accountant confirmation;
- merge into `main` requires an explicit release decision after exact-head
checks complete.

Until those boundaries are satisfied, the status remains `RELEASE_BLOCKED`.
