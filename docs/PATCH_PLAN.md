# Patch Plan — One-Click Stable Release

Date: 2026-07-06
Branch: `fix/quantum-one-click-stable-release`

## Status

`BLOCKED`

## Patch policy

The governing prompt requires minimal patches only:

```text
find problem → fix minimally → test → repeat until working release
```

No code patch is safe in this audit pass because the repository could not be cloned and tests could not be executed in the local environment.

## Immediate patch decision

| Area | Decision | Reason |
|---|---|---|
| Application code | No change | Current tests cannot be run locally after patch. |
| Installer code | No change | No one-click file was verified executable. Creating one without test would simulate readiness. |
| Financial logic | No change | The prompt forbids untested business/financial changes. |
| Migration/data | No change | Data-destructive risk must remain zero. |
| Documentation | Create audit/blocker reports | Safe, factual, and required by the prompt. |

## Minimal safe patch set completed

- Added factual release audit documents.
- Did not alter runtime behavior.
- Did not create a fake release artifact.

## Required future patch loop

1. Obtain a real checkout-capable environment.
2. Run:
   ```text
   git status --short --branch
   git rev-parse HEAD
   git ls-files
   PYTHONPATH=src python -m quantum.scripts.ci
   ```
3. Locate actual run/installer files.
4. If one-click installer is absent, add it as a minimal launcher around existing runtime only after tests pass.
5. Add installer tests.
6. Add smoke-test that verifies health endpoint and UI/upload/calculation paths.
7. Package only after current tests and smoke-test pass.

## Rollback plan

All changes in this audit pass are documentation-only. Rollback is safe by reverting the documentation commits on `fix/quantum-one-click-stable-release`.