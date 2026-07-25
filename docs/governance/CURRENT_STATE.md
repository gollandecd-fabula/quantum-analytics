# CURRENT STATE

Date: 2026-07-25  
Live program: `WB_RELEASE_R2`  
Live namespace: `WBR2`  
Current product unit: `WBR2-M5 — Scheduled weekly and monthly reports`  
Current phase: `UNIVERSAL_PARTIAL_EXACT_HEAD_VALIDATION`
Release status: `RELEASE_BLOCKED`  
Working branch: `fix/quantum-wb-release-r2`  
Validated product head: `5e0e52c0141c5860ea108ba515a073094037ad72`  
Containing governance/audit head: resolved from Git; not self-referenced here  
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

`WBR2-GOV-R1` was validated at
`96e96a88cbb16ef6e0ca2219f2f4abff372b0f2e`.

Validation PR #129 closed with `merged=false`; issue #124 closed as completed.

## WBR2-M5 closure

`WBR2-M5 — Scheduled weekly and monthly reports` is:

- validated at exact head `5e0e52c0141c5860ea108ba515a073094037ad72`;
- integrated into `fix/quantum-wb-release-r2` by fast-forward;
- supported by M5 Linux and Windows, Foundation, OSS, M4 regressions, M7,
  M8, standalone L4, M3 same-artifact A/B, installer and Native Red Team;
- recorded in Validation PR #130, which closed with `merged=false`.

No `WBR2-M6` is assigned or authorized.

## Full-project Red Team R1

A cross-milestone audit was started from immutable working head
`b8e94e8cdf3f2b2179193c752fd17a1a52fb6690`.

Its RTM-first commit is
`30e52ea175eea627bb7469ba0142463d921237a2`.

This is an audit and corrective cycle, not an invented `WBR2-M6`. The candidate
must pass exact-head Linux, hosted Windows, manifest, installer, installed-runtime
and same-artifact gates before integration into the working branch.

The audit explicitly enforces the latest financial-input requirement:

- tax rate and tax base/model are entered and changed by the user;
- cost per product/group is entered and changed by the user;
- other expenses and applicable missing report values are entered by the user;
- no business value is silently prefilled or hard-coded;
- missing or invalid values block only dependent metrics; independent observed and derived metrics continue;
- profile changes affect calculations only after explicit successful Save.

Candidate fixes cover staged dialog editing, corrupt-profile recovery, bounded
window geometry, profile resource limits, removal of duplicate persistence and
a distinct `CONFIGURATION_REQUIRED` self-test state. They are not authoritative
until the exact candidate head passes validation.

## Universal intake and maximum-available calculations R1

The user-authorized corrective cycle `QUANTUM-UNIVERSAL-PARTIAL-R1` starts from
`f251c9325e701b6cf3de127111b86fe8e2d71269`; its RTM-first commit is
`a300184c673f79f15e37eb388ef41c4a85773f2a`.

The candidate contract is:

- every uploaded file receives an auditable per-file result;
- safe XLSX/XLSM, delimited text, JSON tables and XML tables are processed
  without requiring a named Wildberries report or exact header hash;
- ZIP, TAR, TAR.GZ/TGZ, GZIP, BZIP2 and XZ are inspected under bounded archive
  rules; safe members continue independently;
- unsupported RAR/7z and non-tabular data are retained with explicit reason
  codes and do not abort other files;
- unknown columns, units, currency, sign and product attribution are never
  invented;
- each financial metric is `VALID`, `PARTIAL` or `BLOCKED` according to its own
  dependencies;
- partial totals expose coverage and excluded scopes and are never represented
  as complete totals;
- GUI, JSON, Excel and HTML show calculated values first, then unavailable
  values and exact required data.

This candidate is not authoritative until exact-head Linux, hosted Windows,
archive corpus, installer, installed-runtime and same-artifact gates pass.

## Release-candidate evidence

The exact containing Git head is the only valid source identity for an RC build.
This static file does not predeclare a dynamic build PASS. Authoritative RC
evidence is a successful GitHub Actions installer run whose `head_sha` equals
the containing Git head, together with downloaded artifact hashes and native
self-test evidence.

The release candidate remains read-only and WB-only. It cannot write to a
marketplace.

Historical closed-pilot authorization marker retained for compatibility:
`AUTHORIZED_FOR_CLOSED_PILOT_PENDING_ADMISSION_CONTROLS`. This is not a
production release authorization and does not override `RELEASE_BLOCKED`.

## Evidence boundary

Repository, Linux and hosted Windows evidence do not establish physical
installation, real monitor usability or real-report execution on the operator
computer.

The following remain blocked or unverified:

- physical installation and real-report user path, L5;
- physical verification of user-entered financial values and persistence;
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


## XLSX namespace fallback corrective R1

Physical Windows L5 started at exact head `a4e7957c661f46f87c408da7f347fcbbcdc49414`: the GUI launched, but a real operator XLSX was rejected before queue admission with `XLSX_XML_NAMESPACE_UNMODELED`. The old installer is superseded for XLSX pilot import.

Corrective cycle `QUANTUM-XLSX-NAMESPACE-FALLBACK-R1` uses RTM-first commit `ccc07dcb0a016768b3a287d61fb854760e30891c`. Strict schema discovery is now diagnostic; namespace-extended, strict and transitional OOXML can proceed through bounded universal extraction. External relationships, XML entities, active content, encryption, archive corruption and resource-limit violations remain fail-closed. Formula code is never executed and cached formula values are omitted.

The exact rejected workbook was not uploaded. Hosted validation therefore uses synthetic namespace and adversarial XLSX corpora. Physical acceptance remains incomplete until the replacement installer is retested with the operator file.
