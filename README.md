# Quantum Analytics

Universal read-only marketplace analytics platform.

## Governance status

- Constitution: `docs/governance/CONSTITUTION.md`
- Runtime protocol: `docs/governance/RUNTIME_PROTOCOL.md`
- Current state: `docs/governance/CURRENT_STATE.md`
- Active stage contract: `docs/stage-contracts/STAGE-A-FOUNDATION-v1.md`
- Repository: `gollandecd-fabula/quantum-analytics`
- Working branch: `bootstrap/foundation-v5`
- Pull Request: `#2 — FOUNDATION: import verified bootstrap v5` — Ready for merge
- Bootstrap import status: `PASS_WITH_DOCUMENTED_NORMALIZATION`
- Repository controls: `Protect main` ruleset — Active
- GitHub check: `Foundation CI / foundation — PASS (34 tests)`
- Review remediation: 1 P1 and 3 P2 findings fixed; all review threads resolved

## Architecture baseline

Modular monolith with two runtime entry points:

- API Service
- Worker Service

The Wildberries integration is the first adapter. The core domain remains marketplace-neutral.

## Security posture

MVP is read-only. External marketplace write tokens, write methods, and production execution controls are excluded.

## Release status

`RELEASE_BLOCKED`

The governed repository baseline is ready for merge into protected `main`. Production release remains blocked until PostgreSQL integration evidence, production object-storage and recovery evidence, representative Wildberries source contracts, approved-user authentication, and free-tier staging proof for Railway, Vercel, or Cloudflare are available.
