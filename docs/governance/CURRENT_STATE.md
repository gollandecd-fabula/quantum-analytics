# CURRENT STATE

Date: 2026-07-25  
Live program: `WB_RELEASE_R2`  
Live namespace: `WBR2`  
Current unit: `WBR2-M5 — Scheduled weekly and monthly reports`  
Release status: `RELEASE_BLOCKED`  
Working branch: `fix/quantum-wb-release-r2`  
Marketplace writes: `DISABLED`  
Ozon: `DEFERRED`  
Gatekeeper: `DISCONNECTED`

## Authoritative live execution state

The only live execution-state artifact is:

- `docs/evidence/WB_RELEASE_R2_EXECUTION_STATE.yaml`

`docs/evidence/STAGE_B_EXECUTION_STATE.yaml` remains the byte-identical
historical Stage-B snapshot. Its older internal live declaration is superseded
by the WBR2 pointer.

## Historical Stage-B compatibility markers

These literal markers are retained only for historical regression compatibility
and do not override the WBR2 live pointer:

Status: `TECHNICAL_PLATEAU_CANDIDATE`  
Live execution state: `docs/evidence/STAGE_B_EXECUTION_STATE.yaml`  
Current unit: `M9 — Historical Stage-B plateau snapshot`

## Completed WBR2 governance reconciliation

`WBR2-GOV-R1` was validated at:

`96e96a88cbb16ef6e0ca2219f2f4abff372b0f2e`

Validation PR #129 closed with `merged=false`; issue #124 closed as completed.
The Stage-B snapshot was preserved, one WBR2 live-state was established and
superseded WBR2 construction PRs were closed unmerged.

## Current product implementation unit

`WBR2-M5 — Scheduled weekly and monthly reports` is implemented by the
containing commit directly above governance head
`96e96a88cbb16ef6e0ca2219f2f4abff372b0f2e`.

The containing exact head is resolved from Git rather than self-referenced in
this file. It must pass all mandatory exact-head workflows and its validation
PR must close with `merged=false` before the working branch may advance.

M5 adds:

- deterministic previous completed Monday-Sunday week selection;
- deterministic previous completed calendar month selection;
- exact non-overlapping source coverage enforcement;
- SHA-256-bound input identity and idempotent package reuse;
- atomic Excel, dashboard, finance JSON, recommendation JSON, text summary and
  manifest publication;
- bounded scheduled-run outcome state and missed-run recovery;
- Windows Task Scheduler as an external trigger of the same governed command;
- manual weekly/monthly generation and schedule controls on the existing
  `Отчёты` page;
- background execution coordinated with the existing import queue.

No `WBR2-M6` is assigned or authorized.

## Current product

Quantum remains a local Windows read-only decision center for Wildberries
reports. It performs local admission, governed financial calculation and local
JSON, Excel and HTML output. It has no marketplace-write capability.

## Evidence boundary

Exact-head repository, Linux and hosted Windows evidence may support WBR2-M5.
This does not establish physical installation or real-report execution on the
operator computer.

Historical closed-pilot authorization marker retained for compatibility:
`AUTHORIZED_FOR_CLOSED_PILOT_PENDING_ADMISSION_CONTROLS`. This is not a
production release authorization.

The following remain blocked or unverified:

- physical installation and real-report user path, L5;
- applicable tax regime and tax base confirmation;
- Authenticode signing where required;
- merge into `main`;
- deployment or production release;
- Ozon activation;
- marketplace writes.

Until those boundaries are explicitly satisfied:

`FAIL-CLOSED`  
`PROTOCOL_IMPLEMENTATION_INCOMPLETE`  
`MILESTONE_NOT_COMPLETE`  
`RELEASE_BLOCKED`
