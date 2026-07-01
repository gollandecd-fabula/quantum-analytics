# Quantum Recovery Runbook

## Stable state

Use repository `gollandecd-fabula/quantum-analytics` and restore exact commit `d1e8b46c0809476f6faece7b2808e6dd5d1f22c3`.

Read the checkpoint identity, project rules, stable execution snapshot, Stage B contract, live execution state, and current-state document in that order.

## Work in progress

Recover branch `build-b1b-financial-kernel-v1` at exact commit `b3b33a11f8da671356c9bc6c8073b59819a9654c`.

Treat it as `WIP_RECOVERY_ONLY`. Do not merge it before the recorded manifest mismatch is fixed and all exact-head gates pass.

## Continuation order

1. Fix the two manifest hashes.
2. Run Foundation CI.
3. Run OSS Admission checks.
4. Synchronize state and evidence to the verified head.
5. Complete independent review.
6. Reach zero unresolved review threads.
7. Merge with an exact-head guard.
8. Create a separate closure PR.

Keep real data, Source Authority, marketplace writes, external access, and production release disabled.
