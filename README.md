# Quantum Analytics

Universal read-only marketplace analytics platform.

## Governance status

- Constitution: `docs/governance/CONSTITUTION.md`
- Runtime protocol: `docs/governance/RUNTIME_PROTOCOL.md`
- Current state: `docs/governance/CURRENT_STATE.md`
- Active stage contract: `docs/stage-contracts/STAGE-A-FOUNDATION-v1.md`
- Bootstrap status: local package prepared; dedicated GitHub repository is not yet connected.

## Architecture baseline

Modular monolith with two runtime entry points:

- API Service
- Worker Service

The Wildberries integration is the first adapter. The core domain remains marketplace-neutral.

## Security posture

MVP is read-only. External write tokens, write methods, and execution controls are excluded.
