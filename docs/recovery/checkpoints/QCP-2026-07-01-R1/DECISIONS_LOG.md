# Recovery Decision Log

## D-REC-001 — Dual-state checkpoint

The checkpoint preserves stable `main` and PR #33 WIP separately. A failing or review-pending branch must never be represented as verified state.

## D-REC-002 — GitHub is canonical

Critical project rules are committed here because chat history is not a durable or independently verifiable recovery source.

## D-REC-003 — No automatic WIP merge

PR #33 is recoverable but not mergeable until exact-head CI, manifest equality, independent review, and zero unresolved threads pass.

## D-REC-004 — Stage Contract precedence

`docs/stage-contracts/STAGE-B-BUILD-v1.md` remains immutable authority for Stage B. This checkpoint summarizes but does not replace it.

## D-REC-005 — Read-only marketplace-neutral core

Quantum remains marketplace-neutral and read-only. Wildberries is an adapter. Marketplace writes, external action execution, and production deployment remain excluded.

## D-REC-006 — Controlled financial kernel

Financial logic is Decimal-based, versioned, evidence-linked, and free of hidden universal commercial constants. Synthetic-only Golden Oracle evidence is required before real-data use.

## D-REC-007 — Controlled self-learning

Self-learning is allowed only through an auditable closed loop with experiments, measured results, human approval, versioning, rollback, and no autonomous commercial action.

## D-REC-008 — External backup required

A Git tag and GitHub Release are necessary but insufficient. A verified encrypted off-site archive is required after checkpoint merge.
