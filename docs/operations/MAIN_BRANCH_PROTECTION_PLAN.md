# Main Branch Protection Plan

Status: `APPLIED_WITH_UI_EVIDENCE`
Date applied: 2026-06-27
Repository: `gollandecd-fabula/quantum-analytics`
Ruleset: `Protect main`
Ruleset ID: `18204094`
Target: default branch `main`
Enforcement: `ACTIVE`

## Applied controls

- Require a pull request before merging.
- Required approvals: `0` while no independent reviewer account is configured.
- Require conversation resolution before merging.
- Require status checks to pass before merging.
- Required check: `foundation` from GitHub Actions.
- Require branches to be up to date before merging.
- Restrict branch deletion.
- Block force pushes.
- Bypass list is empty.

## Controls intentionally not enabled

- Restrict branch creation.
- Restrict all branch updates.
- Require signed commits.
- Require deployments to succeed.
- Require code scanning or code quality results.
- Require review from Code Owners.
- Require approval of the most recent reviewable push.
- Automatically request Copilot review.

These controls remain excluded because they are either unavailable in the current free workflow, unnecessary for the single-owner bootstrap phase, or would create an unresolvable self-approval gate.

## Evidence

- User-provided GitHub UI screenshot shows `Rulesets / Protect main` with status `Active`.
- The same screen shows the ruleset applies to one target: `main`.
- Creation confirmation: `Ruleset created`.
- Repository metadata confirms visibility `public` and default branch `main`.
- Current-head GitHub Actions workflow `Foundation CI` must remain passing before merge.

## Remaining verification

A negative enforcement test—attempting a direct update or merge with a missing/failing required check—has not been executed. The rule configuration itself is complete. This test is useful operational evidence but is not required to preserve the current Draft PR state.

## Review rule

Do not require one approving review until an independent reviewer account is configured. R2 and higher changes still require independent verification evidence under the Constitution.
