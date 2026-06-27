# Quantum Analytics

Universal read-only marketplace analytics platform.

## Governance status

- Constitution: `docs/governance/CONSTITUTION.md`
- Runtime protocol: `docs/governance/RUNTIME_PROTOCOL.md`
- Current state: `docs/governance/CURRENT_STATE.md`
- Active stage contract: `docs/stage-contracts/STAGE-A-FOUNDATION-v1.md`
- Repository: `gollandecd-fabula/quantum-analytics`
- Default branch: `main`
- FOUNDATION Pull Request: `#2 — FOUNDATION: import verified bootstrap v5` — merged
- FOUNDATION merge commit: `4aa2e69cd985879271b44ad3345f73e972add845`
- Bootstrap import status: `PASS_MERGED_WITH_DOCUMENTED_NORMALIZATION`
- Repository controls: `Protect main` ruleset — Active
- Final pre-merge check: `Foundation CI / foundation — PASS (34 tests)`
- Review remediation: 1 P1 and 3 P2 findings fixed; all review threads resolved before merge

## Architecture baseline

Modular monolith with two runtime entry points:

- API Service
- Worker Service

The Wildberries integration is the first adapter. The core domain remains marketplace-neutral.

## Security posture

MVP is read-only. External marketplace write tokens, write methods, and production execution controls are excluded.

## Deployment constraint

Final hosting is restricted to one approved platform:

- Railway;
- Vercel;
- Cloudflare.

The selected platform must pass documented free-tier feasibility and approved-user-only access checks.

## Release status

`RELEASE_BLOCKED`

The governed repository baseline is merged into protected `main`. Production release remains blocked until PostgreSQL integration evidence, production object-storage and recovery evidence, representative Wildberries source contracts, approved-user authentication, and free-tier staging proof for Railway, Vercel, or Cloudflare are available.
