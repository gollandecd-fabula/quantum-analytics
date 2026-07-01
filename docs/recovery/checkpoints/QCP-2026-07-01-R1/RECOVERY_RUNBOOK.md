# Quantum Recovery Runbook

## Stable state

Use repository `gollandecd-fabula/quantum-analytics` and restore exact commit `d1e8b46c0809476f6faece7b2808e6dd5d1f22c3`.

After opening `CHECKPOINT.yaml`, apply recovery sources in the recorded precedence order:

1. latest explicit project-owner decision available in the recovery record;
2. immutable `docs/stage-contracts/STAGE-B-BUILD-v1.md`;
3. `PROJECT_RULES_MASTER.yaml`;
4. `docs/evidence/STAGE_B_EXECUTION_STATE.yaml`;
5. `docs/governance/CURRENT_STATE.md`;
6. unit evidence, including `EXECUTION_STATE_SNAPSHOT.yaml` and `WIP_STATE_SNAPSHOT.yaml`;
7. GitHub issues, pull requests, reviews, and `OPEN_WORK_AND_BLOCKERS.md`;
8. chat-history summaries only as the lowest-priority supplemental source.

## Work in progress

Recover branch `build-b1b-financial-kernel-v1` at exact commit `b3b33a11f8da671356c9bc6c8073b59819a9654c`.

Treat it as `WIP_RECOVERY_ONLY`. Do not merge it before the recorded manifest mismatch is fixed and all exact-head gates pass.

## Required backup form

The external disaster-recovery copy must be a Git bundle, or equivalent multi-ref export, that contains both the stable and WIP histories.

Required refs:

- `refs/heads/main`;
- `refs/heads/build-b1b-financial-kernel-v1`;
- `refs/tags/quantum-recovery-2026-07-01-r1`.

A GitHub Release source archive or `git archive` of a single tree is not sufficient because it omits the unmerged WIP ref.

Before accepting the backup:

1. verify the bundle;
2. confirm the WIP branch resolves to `b3b33a11f8da671356c9bc6c8073b59819a9654c`;
3. confirm the recovery tag resolves to the checkpoint merge commit;
4. calculate SHA-256;
5. store the encrypted bundle and its checksum separately outside GitHub.

## Continuation order

1. Fix the two PR #33 manifest hashes.
2. Run Foundation CI.
3. Run OSS Admission checks.
4. Synchronize state and evidence to the verified head.
5. Complete independent review.
6. Reach zero unresolved review threads.
7. Merge with an exact-head guard.
8. Create a separate closure PR.

Keep real data, Source Authority, marketplace writes, external access, and production release disabled.
