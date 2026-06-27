# Quantum Analytics

Universal read-only marketplace analytics platform.

## Governance status

- Constitution: `docs/governance/CONSTITUTION.md`
- Runtime protocol: `docs/governance/RUNTIME_PROTOCOL.md`
- Current state: `docs/governance/CURRENT_STATE.md`
- Active stage contract: `docs/stage-contracts/STAGE-A-FOUNDATION-v1.md`
- Repository: `gollandecd-fabula/quantum-analytics`
- Working branch: `bootstrap/foundation-v5`
- Draft Pull Request: `#2 — FOUNDATION: import verified bootstrap v5`
- Bootstrap import status: `PASS_WITH_DOCUMENTED_NORMALIZATION`
- GitHub check: `Foundation CI / foundation — PASS (29 tests)`

## Architecture baseline

Modular monolith with two runtime entry points:

- API Service
- Worker Service

The Wildberries integration is the first adapter. The core domain remains marketplace-neutral.

## Security posture

MVP is read-only. External marketplace write tokens, write methods, and production execution controls are excluded.

## Release status

`RELEASE_BLOCKED`

The dedicated repository is connected, the verified bootstrap is present in Draft PR #2, and the Foundation CI check passes. Merge remains blocked until `main` protection, PostgreSQL integration evidence, production object-storage and recovery evidence, and representative Wildberries source contracts are available.
