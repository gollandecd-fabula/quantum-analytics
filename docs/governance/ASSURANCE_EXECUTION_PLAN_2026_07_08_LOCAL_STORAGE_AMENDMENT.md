# Assurance Execution Plan Amendment — Local Disk Encryption

Amendment ID: `QUANTUM-ASSURANCE-2026-07-08-LOCAL-STORAGE-A1`
Date: `2026-07-02`
Authority: `DR-2026-07-02-LOCAL-DISK-ENCRYPTION-NOT-REQUIRED`
Applies to: `docs/governance/ASSURANCE_EXECUTION_PLAN_2026_07_08.md`
Status: `ACTIVE`

## Amendment

For the local single-user Quantum pilot:

- full-disk encryption is not required;
- application-level encryption at rest for local working copies is not required;
- absence of local disk encryption is not a P0/P1 finding and does not block `PILOT_READY`;
- loopback-only runtime binding remains mandatory;
- operating-system account access control remains mandatory;
- minimization, tenant/account authorization, privacy-safe logs, retention, deletion, revocation,
  reconciliation, and prohibition on raw-data disclosure remain mandatory.

For hosted, cloud, shared, removable, exported, and backup storage, encryption at rest remains mandatory.
For separately approved non-loopback transport, TLS remains mandatory.

## Superseded plan text

For the local single-user version only, this amendment supersedes:

- section 2.5 references that treat all at-rest encryption as mandatory;
- section 5 references to encryption checks where those checks mean local disk encryption;
- section 8 the unconditional phrase `encrypted transport and storage`;
- section 8 the statement that any `unencrypted copy` is automatically P0/P1;
- section 10 criterion 12 where `encryption` means local disk or local application-storage encryption.

The remaining security, privacy, financial, reconciliation, recovery, and release gates are unchanged.

## Machine-readable authority

The controlling machine-readable version is
`docs/governance/ASSURANCE_EXECUTION_PLAN_2026_07_08.yaml`, plan version `v3`.
