# CURRENT STATE

Date: 2026-07-14
Status: `TECHNICAL_PLATEAU_CANDIDATE`
Release status: `RELEASE_BLOCKED`
Working branch: `fix/quantum-plateau-redteam`
Pull request: `#102`
Base branch: `main`
Marketplace writes: `DISABLED`
Current unit: `M9 — Final plateau verification and release dossier`
Live execution state: `docs/evidence/STAGE_B_EXECUTION_STATE.yaml`

## Current product

The active user-facing product is a local Windows desktop decision center for
Wildberries reports. It installs from one offline EXE, stores reports locally,
restores admitted reports after restart, calculates economics only from an
explicitly confirmed finance profile and has no marketplace-write capability.

Main runtime:

- `quantum.application.desktop_center`;
- local Finance Center UI;
- local report admission and immutable managed storage;
- local financial calculation and exports;
- fail-closed desktop and Finance Center self-tests.

## Plateau acceptance criteria

Technical plateau requires all of the following on one immutable exact head:

1. zero open P0 software defects;
2. zero open P1 software defects;
3. manifest equality for the complete tracked tree;
4. all mandatory Linux and Windows gates pass;
5. an independent repeated Red Team run finds no new P0/P1 defect;
6. the repeated gate run passes without production-code changes;
7. the offline EXE passes native and installed-runtime checks;
8. marketplace writes remain disabled.

Historical PASS results do not transfer to a later commit.

## Completed milestones

### M0 — Baseline and release integrity

- Historical evidence was restricted to its exact commit.
- Work moved from the long-lived release branch to PR #102.
- The plateau branch now contains current `main` as a real ancestor.

### M1 — Live runtime integration

- Removed shadowed queue behavior from the active class path.
- Bound report persistence, managed-source switching and repeat processing to
  the runtime used by the desktop UI.

### M2 — Financial orchestration

- Finance profile schema v2 requires explicit tax rate, tax base, cost and
  other expenses.
- Unknown products and physical sales or returns without SKU block calculation.
- Marketplace service expenses without SKU are retained separately.
- Tax is calculated once at period level.
- Zero-activity groups are valid.

### M3 — Durable state and privacy

- Report index v2 stores portable Quantum-controlled paths only.
- External source paths are not accepted as durable report sources.
- Index writes use staged JSON validation, fsync and bounded replace retry.
- The financial parser processes the same immutable XLSX bytes that were hashed.

### M4 — Authority and schema review

- The desktop no longer invents authority or schema attestations.
- Users explicitly confirm authority and inspect the detected XLSX schema.
- Declined or failed review prevents queue admission.

### M5 — Trustworthy self-test

- Desktop PASS depends on Finance Center PASS.
- Known-answer finance, configuration, runtime MRO, persistence round-trip,
  privacy and schema-review controls are checked fail-closed.
- Windows path canonicalization covers long-path and 8.3 representations.

### M6 — Build and documentation

- Standard PEP 517 wheel build is enabled.
- The setuptools backend is version-pinned.
- Package metadata and entry points identify the real desktop product.
- Primary documentation no longer describes an obsolete hosted API/worker
  deployment.

### M7 — Desktop release integration

- Current `main` is a real ancestor of the plateau branch.
- The release gate verifies desktop self-test, installed runtime, offline EXE,
  exact source commit, SHA-256 and read-only scope.
- Installed-copy detection survives partial updates and missing package-only
  installer files.
- Legacy `localhost:8000` launch behavior is rejected.

## Final milestone

### M8/M9 — Repeated verification and release dossier

The source tree is frozen as a technical plateau candidate. Final acceptance is
performed by two complete exact-head Linux/Windows runs without production-code
changes. The final defect register and Red Team dossier are maintained at:

- `docs/evidence/M9_DEFECT_REGISTER.json`;
- `docs/evidence/M9_PLATEAU_RED_TEAM_REPORT.md`.

## Real commercial data boundary

Pilot authorization remains
`AUTHORIZED_FOR_CLOSED_PILOT_PENDING_ADMISSION_CONTROLS`.
Only data that passes the declared admission controls may be used. Raw real
commercial data remains prohibited in external model prompts. Local disk
encryption is not a pilot gate under the recorded local-storage amendment;
hosted external storage encryption and approved non-loopback TLS remain
mandatory. Production release and marketplace writes remain blocked.

## External release boundaries

The following are not unresolved software defects:

- Authenticode signing requires an approved code-signing certificate;
- physical user-pilot evidence requires installation on the target computer;
- the applicable tax regime and tax base require user or accountant confirmation;
- merge into `main` requires a separate explicit release decision.

Until those boundaries are satisfied, the status remains `RELEASE_BLOCKED`.
