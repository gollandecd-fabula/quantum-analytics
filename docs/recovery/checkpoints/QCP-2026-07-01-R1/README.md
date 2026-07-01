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

A GitHub Release source archive or `git archive` of one commit is supplemental only. It does not preserve the unmerged PR #33 WIP ref and therefore is not a valid dual-state disaster-recovery backup.

## Required post-merge completion

After this checkpoint passes exact-head CI and independent review:

1. merge it into `main`;
2. create immutable tag `quantum-recovery-2026-07-01-r1` on the merge commit;
3. create a Git bundle that explicitly contains:
   - `refs/heads/main`;
   - `refs/heads/build-b1b-financial-kernel-v1` at `b3b33a11f8da671356c9bc6c8073b59819a9654c`;
   - `refs/tags/quantum-recovery-2026-07-01-r1`;
4. verify the bundle and record its advertised refs;
5. optionally create a matching GitHub Release, but never use its source archive as the sole backup;
6. store the encrypted bundle and a separately stored SHA-256 outside GitHub;
7. perform an isolated clone from the bundle, verify both stable and WIP commits, and update the verification report.
