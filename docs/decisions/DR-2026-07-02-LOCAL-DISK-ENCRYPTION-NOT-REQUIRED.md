# Decision Record — Local Pilot Disk Encryption Exception

Decision ID: `DR-2026-07-02-LOCAL-DISK-ENCRYPTION-NOT-REQUIRED`
Date: `2026-07-02`
Risk class: `R3`
Status: `APPROVED`
Owner decision: full-disk encryption and application-level encryption at rest are not mandatory for the local single-user Quantum pilot.

## Decision

For the local version running on a project-owner-controlled computer:

- full-disk encryption is optional;
- application-level encryption at rest for local working copies is optional;
- absence of local disk encryption is not a `P0`, `P1`, or pilot-readiness blocker;
- the application must remain bound to loopback (`127.0.0.1` or equivalent) unless a separate network-exposure decision is approved;
- raw commercial data remains prohibited in GitHub, CI, screenshots, issue bodies, PR comments, evidence packages, and external model prompts;
- authenticated account and tenant checks, minimization, retention, deletion, privacy-safe logging, source reconciliation, and read-only marketplace behavior remain mandatory.

## Controls that remain mandatory

- TLS for any approved non-loopback transport.
- Encryption at rest for hosted, cloud, shared, removable, exported, and backup storage.
- No public or LAN exposure of the local pilot without a separate approval.
- Operating-system account access controls on the local computer.
- Deletion of local raw and derived data according to the approved retention policy.
- No marketplace write credentials or write capability.

## Superseded requirements

For the local single-user pilot only, this decision supersedes statements in:

- `docs/governance/ASSURANCE_EXECUTION_PLAN_2026_07_08.md`;
- `docs/governance/ASSURANCE_EXECUTION_PLAN_2026_07_08.yaml`;
- `docs/decisions/DR-2026-07-01-REAL-COMMERCIAL-DATA-PILOT.md`;
- `docs/security/REAL_COMMERCIAL_DATA_ADMISSION_CONTRACT_2026_07_08.md`;

where those statements made local full-disk encryption or local encryption at rest an unconditional pilot gate.

It does not weaken encryption requirements for hosted, external, shared, removable, exported, or backup storage.

## Consequences

- Local disk encryption is removed from the July 8 pilot exit criteria.
- AppSec verification must distinguish local loopback storage from hosted or external storage.
- An unencrypted local working copy is not by itself a security finding.
- Unencrypted hosted/external storage or unencrypted approved non-loopback transport remains a blocking finding.
- Production release remains `RELEASE_BLOCKED`.
