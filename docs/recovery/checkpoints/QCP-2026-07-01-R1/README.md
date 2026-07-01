# Quantum Recovery Checkpoint QCP-2026-07-01-R1

This directory is the canonical emergency-recovery index for Quantum Analytics.

## Preserved states

1. **Verified stable baseline:** `main@d1e8b46c0809476f6faece7b2808e6dd5d1f22c3`.
2. **Work in progress:** PR #33 at `b3b33a11f8da671356c9bc6c8073b59819a9654c`.

The WIP state is not a release candidate and must never be treated as a verified baseline.

## Current boundaries

- Stable project state: `BUILD_P1_5_COMPLETE`.
- Active contract: `STAGE-B-BUILD-v1`.
- B1b: recovery-only WIP.
- B2 and B6: gated by B1b.
- B7 external access: not authorized.
- Real or anonymized commercial data: not admitted.
- Source Authority: not activated.
- Marketplace writes: disabled.
- Production release: `RELEASE_BLOCKED`.

## Recovery invariant

A valid restore reproduces the exact Git commits, checkpoint hashes, stage gates, security exclusions, and open blockers recorded here. Chat history alone is not a sufficient recovery source.

## Required post-merge completion

After this documentation-only checkpoint passes exact-head CI and independent review:

1. merge it into `main`;
2. create immutable tag `quantum-recovery-2026-07-01-r1` on the merge commit;
3. create a GitHub Release with the same name;
4. export a repository bundle or archive;
5. store the encrypted archive and separately stored SHA-256 outside GitHub;
6. perform a fresh-clone recovery drill and update the verification report.
