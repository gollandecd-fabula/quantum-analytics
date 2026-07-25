# MILESTONE 3 — P0/P1 Stabilization

**Date:** 2026-07-11  
**Baseline head:** `d5f95b9668f5d788df11ccab6efd49c73d71de1f`  
**Branch:** `fix/quantum-one-click-stable-release`  
**Mode:** test-first, fail-closed, minimal scope  
**Marketplace writes:** disabled

## Verdict before exact-head CI

`CANDIDATE_PASS_WITH_LIMITATIONS`

M1 closed and verified the two previously reproduced P1 findings. M3 therefore did not assume that runtime rewrites were required. It re-attacked the critical boundaries and added permanent regression tests for previously unmapped or source-only scenarios that could otherwise create incorrect financial conclusions or false readiness claims.

## P0/P1 defect baseline

| ID | Boundary | Pre-M3 state | M3 result |
|---|---|---|---|
| M1-D001 | One-click config persistence | CLOSED_VERIFIED | Revalidated by existing Windows production/native gates |
| M1-D002 | Workflow exit-code masking | CLOSED_VERIFIED | Revalidated by truthful exact-head workflow gates |
| M3-RT01 | Missing cost per unit | Coverage gap | Fail-closed: `KERNEL_REQUEST_INVALID` |
| M3-RT02 | Missing tax rate | Coverage gap | Fail-closed: `KERNEL_REQUEST_INVALID` |
| M3-RT03 | Missing other expenses | Coverage gap | Fail-closed: `KERNEL_REQUEST_INVALID` |
| M3-RT04 | Unknown financial input | Coverage gap | Fail-closed: `KERNEL_INPUTS_INVALID` |
| M3-RT05 | Explicit zero revenue | Coverage gap | Preserved as valid zero; not converted to missing |
| M3-RT06 | Division by zero | Source-only coverage | Returns typed `BLOCKED / EXPRESSION_DIVISION_BY_ZERO` |
| M3-RT07 | Decimal comma | Coverage gap | Accepted at WB numeric parsing boundaries |
| M3-RT08 | Changed column order | Coverage gap | Deterministically rejected; no silent remapping |
| M3-RT09 | Missing source file | Existing boundary | Privacy-safe error report; no calculation or marketplace write |

## Test-first evidence

The new M3 test module was executed against the exact Windows source-package artifact built from the M2 head.

- 7 tests per run;
- 3 consecutive runs;
- 21/21 PASS;
- source `compileall`: PASS;
- local Red Team log SHA-256: `4dca8420fd1ed60c18aebd0ba5a0a1eb10c2bba49e9798a4ebd0f7a215164db2`.

No product-runtime patch was justified by these attacks. The correct stabilization action is to preserve the existing fail-closed behavior as permanent regression coverage rather than rewrite working financial or ingestion code.

## Stale issue triage

Open issues #43 and #48 are legacy implementation/governance work items whose titles contain `P1`; they are not treated as newly reproduced runtime defects.

- Issue #43 concerns an earlier financial-kernel port. The current branch contains the kernel and exact-head finance tests.
- Issue #48 concerns the real XLSX admission foundation. The current branch contains the admission state machine and adversarial test coverage, but an authorized real dataset and reconciliation remain an external data/approval prerequisite. M3 does not claim that prerequisite is complete.

The issues are not closed automatically in M3 because their governance scope is broader than a code defect closure.

## M3 scope

Allowed changes:

1. one P0/P1 Red Team regression-test module;
2. this evidence report;
3. a machine-readable defect register;
4. immutable manifest overlay R48;
5. one-line manifest-chain extension.

No runtime, finance kernel, adapter, launcher, installer or marketplace-write code is changed.

## Gate requirements

M3 can receive `PASS_WITH_LIMITATIONS` only if the final exact head passes:

- M3 regression tests;
- full Foundation CI;
- OSS Admission CI;
- all mandatory Windows package/installer gates;
- Windows Production Repair;
- Native One-Button Red Team;
- M1 Baseline and Reproduction Audit;
- immutable manifest equality.

## Remaining limitations outside P0/P1 scope

- no pinned linter;
- no pinned type checker;
- wheel/sdist intentionally disabled by the Foundation backend;
- changed WB column order remains fail-closed rather than automatically remapped;
- browser-render/screenshot QA remains unexecuted;
- authorized real-commercial-data admission and reconciliation remain pending;
- standalone production release remains blocked;
- final score is not calculated before M9.
