# Main Branch Protection Plan

Status: `REQUIRED_BEFORE_FOUNDATION_MERGE`

The current GitHub Connector cannot configure branch protection or repository rulesets. Apply the following controls to branch `main` through GitHub repository settings.

## Required controls

- Require a pull request before merging.
- Require status checks to pass before merging.
- Required check name: `foundation`.
- Require branches to be up to date before merging, when the option is available.
- Require conversation resolution before merging.
- Block force pushes.
- Block branch deletion.
- Do not allow bypass for ordinary changes.
- Keep Draft PR #2 unmerged until the rules are active and the current-head `foundation` check passes.

## Review rule

Do not require one approving review until an independent reviewer account is configured; otherwise the repository owner would create an unresolvable self-approval gate. R2 and higher changes still require independent verification evidence under the Constitution.

## Verification evidence

After configuration, capture:

- repository rules or branch-protection settings;
- required check `foundation`;
- a blocked merge attempt when the check is absent or failing;
- a passing current-head CI run.
