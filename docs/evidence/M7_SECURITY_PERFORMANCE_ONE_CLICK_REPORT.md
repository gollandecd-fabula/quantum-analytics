# MILESTONE 7 — Security, Performance and One-Click

## Verdict

`PASS_LOCAL_PENDING_EXACT_HEAD_CI`

M7 adds a unified fail-closed assurance layer for security, candidate-versus-baseline performance and the existing Windows one-click path. It does not authorize production release, marketplace writes, merge to `main`, automatic price or advertising changes, or a final quality score.

## Baseline

- Branch: `fix/quantum-one-click-stable-release`
- M6 exact head: `0972d02312bdee3aae3583dc6d9caf369622a57d`
- Runtime: HOME_LOCAL, offline, read-only
- Existing financial semantics and marketplace adapters: unchanged
- Existing native one-button implementation: reused rather than rewritten

## Security gate

`tools/m7_security_performance_one_click.py audit` checks the current repository rather than relying on narrative evidence. The gate fails when it detects:

- marketplace writes enabled in repository policy or runtime source;
- implicit `AuthorityAttested`, `SchemaReviewed` or Defender-skip defaults;
- removal of local-path, package-manifest, reviewed-hash or Defender controls;
- `shell=True` in Quantum runtime source;
- unapproved network-write primitives in Quantum runtime source;
- missing `RELEASE_BLOCKED` package invariants.

Any P0 or P1 finding makes the audit exit nonzero. The audit output is written atomically as JSON and contains no source report rows, finance values or credentials.

## Performance gate

The performance job checks out two isolated trees on the same runner:

1. immutable M6 baseline `0972d02312bdee3aae3583dc6d9caf369622a57d`;
2. the exact current PR head.

It measures marketplace-neutral identifier normalization and frozen-registry resolution for 50,000 iterations, repeats the probe five times and compares medians. The candidate passes only when:

`candidate_median <= max(baseline_median × 1.75, baseline_median + 0.25 seconds)`

The ratio plus absolute slack prevents both large regressions and false failures caused by sub-second runner noise. This gate does not benchmark network access or marketplace writes.

## One-click exact-head Red Team

The dedicated Windows job:

- asserts the exact PR head;
- parses all critical one-click PowerShell surfaces;
- runs M7, one-click installer, Windows hardening and M0 recovery contracts;
- executes `scripts/ci/native_one_button_r37.ps1` on the same exact head;
- uploads the native result and QA evidence.

The audit also freezes actionable user-error contracts for missing Python, missing non-interactive input, invalid configuration, cancelled source selection and missing output.

## Local validation

- M7 assurance module syntax/compile: PASS;
- M7 unit tests for clean, P0, missing-error and performance-regression cases: 4/4 PASS;
- JSON evidence syntax: PASS;
- workflow static contract: covered by M7 repository tests;
- exact-head GitHub Actions: required after commit and push.

## Red Team findings and closure

- `M7-D001 P1` — distributed security controls without one gate: closed locally, pending exact-head CI.
- `M7-D002 P1` — no pinned performance comparison: closed locally, pending exact-head CI.
- `M7-D003 P1` — one-click evidence distributed across workflows: closed locally, pending exact-head CI.
- `M7-D004 P2` — no explicit actionable-error regression contract: closed.
- `M7-D005 P1` — evidence could target the wrong commit: closed locally by exact-head assertions, pending CI.

No security P0/P1 remains open in the M7 defect register.

## Safety preserved

- marketplace writes remain disabled;
- no external network calls were added to runtime code;
- no financial assumptions, costs, taxes or other expenses were added;
- recommendation generation remains separate from execution;
- Ozon semantic parsing remains fail-closed pending approved profiles;
- production release and final scoring remain blocked.

## Limitations

- Performance evidence is a targeted regression probe, not a production-capacity benchmark.
- The native one-click job validates the GitHub-hosted Windows environment; clean-machine reproduction remains MILESTONE 8.
- Production release remains blocked until subsequent milestones and Final Red Team.
