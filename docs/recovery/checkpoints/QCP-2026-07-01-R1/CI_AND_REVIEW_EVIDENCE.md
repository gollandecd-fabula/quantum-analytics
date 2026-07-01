# CI and Review Evidence

## Stable baseline

- Baseline commit: `d1e8b46c0809476f6faece7b2808e6dd5d1f22c3`
- Completed implementation commit: `8a714e5688f3af5872305f8e1fdbdb4f56ee9d9a`
- Unit: P1.5 / B5
- Foundation run `28454778048`: PASS
- OSS run `28454777923`: PASS
- Targeted tests: 64
- Final independent review: PASS
- Unresolved threads: 0

## B1b work in progress

- PR: 33
- Head: `b3b33a11f8da671356c9bc6c8073b59819a9654c`
- Merge ref observed at snapshot: `9858df459c4103ae653aa48b8d5fb978f608b48a`
- Manifest overlay: 26
- Foundation run `28480911185`: FAILURE
- OSS run `28480911169`: FAILURE
- Confirmed cause: two manifest content-hash mismatches
- Exact-head review: incomplete
- Merge status: blocked

## Recovery checkpoint QCP-2026-07-01-R1

- PR: 34
- Exact reviewed head: `dba81778f3c9cc931acf3bfe44a692d8d08213d6`
- Foundation run `28498083253`: PASS
- OSS Admission, official registries, and OSV run `28498083225`: PASS
- Repository manifest equality: PASS
- Independent review findings: 3
- Findings remediated: 3
- Final Codex verdict: `+1`
- Unresolved review threads: 0
- Merge commit: `eed62fcc22f624b3632d16db3cf00410d3d4d412`
- Merged at: `2026-07-01T06:33:49Z`
- External tag/bundle/restore completion: pending
- Release status: `RELEASE_BLOCKED`
