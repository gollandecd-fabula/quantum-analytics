# Local Pilot Orchestrator R20

Status: INTERNAL PILOT CANDIDATE / RELEASE_BLOCKED

R20 connects the existing admission, finance and B2 reconciliation contracts through one dependency-free local execution boundary.

Required sequence:

1. Validate loopback-only execution scope.
2. Declare, inspect and admit the dataset.
3. Require the admitted dataset at the reconciliation time.
4. Run ACTUAL finance requests in PREVIEW_ONLY state.
5. Build B2 totals only through explicit metric bindings.
6. Require reconciliation state RECONCILED.
7. Return canonical evidence without persisting input bytes.

Mandatory controls:

- host equals 127.0.0.1;
- read-only, one operator and one organization;
- marketplace writes, public hosting and production credentials disabled;
- tenant, account and organization identities must match;
- only synthetic fixtures are stored in the repository;
- production release remains blocked.
