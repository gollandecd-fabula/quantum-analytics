# Open Work and Blockers

## B1b recovery sequence

1. Restore branch `build-b1b-financial-kernel-v1` at `b3b33a11f8da671356c9bc6c8073b59819a9654c`.
2. Correct the two recorded SHA-256 values in `docs/evidence/ARTIFACT_MANIFEST_OVERLAY_B1B.json`.
3. Run Foundation CI and OSS Admission again.
4. Synchronize B1b execution evidence and current-state documents to the exact verified head.
5. Obtain a fresh independent exact-head review.
6. Remediate all findings and reach zero unresolved review threads.
7. Reverify exact head, manifest equality, and both CI workflows.
8. Merge PR #33 only with an exact-head guard.
9. Record post-merge closure in a separate PR.
10. Keep B2 and B6 gated until B1b closure is complete.

## Confirmed blocker

The latest checks fail because manifest v26 contains two incorrect file-content hashes. The available log does not establish a separate functional-kernel defect.

## Checkpoint completion

1. Pass exact-head CI for the checkpoint PR.
2. Complete independent review with no findings and zero unresolved threads.
3. Merge the checkpoint PR.
4. Create tag `quantum-recovery-2026-07-01-r1` and a matching GitHub Release.
5. Export a protected off-site copy and store its SHA-256 separately.
6. Perform a fresh-clone recovery drill and update the verification report.
