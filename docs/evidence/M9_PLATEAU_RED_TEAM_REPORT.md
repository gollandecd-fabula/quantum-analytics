# Quantum M9 Plateau Verification Report

Date: 2026-07-14  
Branch: `fix/quantum-plateau-redteam`  
Pull request: `#102`  
Status: `TECHNICAL_PLATEAU_CANDIDATE`  
Production release: `RELEASE_BLOCKED`

## Scope

This report covers the local Windows desktop Wildberries analytics product,
offline installation, report admission and durable storage, finance profiles,
economic calculation, desktop self-test and read-only release boundaries.

It does not authorize marketplace writes, public hosting, production
credentials or merge into `main`.

## Verification method

The project was evaluated milestone by milestone:

1. freeze an exact source head;
2. inspect the active runtime path;
3. review financial assumptions, durable state, Windows filesystem behavior,
   authority boundaries, packaging and installer behavior;
4. add a regression for every confirmed defect;
5. run Linux and Windows verification gates;
6. investigate every unexpected result;
7. bind final bytes through append-only manifest overlays.

## Material findings and remediation

### Runtime integrity

The live desktop class previously resolved some queue operations to a different
mixin from the one covered by persistence tests. Shadowed behavior was removed.
Live-class regressions now bind persistence and repeat processing to the actual
UI runtime.

### Financial correctness

The finance profile requires explicit tax rate, tax base, product cost and
other expenses. Tax is calculated once at period level. Unknown products and
physical sales or returns without SKU fail closed. WB service expenses without
SKU remain in period economics. Zero-activity groups are valid.

### Durable report state

Admitted reports survive restart through report index v2. Only portable paths
inside the Quantum root are durable. Index publication uses staged JSON
validation, fsync and bounded replacement retry. Corrupt indexes recover from
verified output evidence. Calculation parses the same immutable XLSX bytes that
were hashed.

### Authority and schema review

The desktop no longer sends automatic `AuthorityAttested` or `SchemaReviewed`
flags. Users confirm authority for the selected batch and inspect the detected
sheet, header row, columns, formula count, reporting period and SHA-256 before
admission.

### Self-test

Desktop PASS depends on nested Finance Center PASS. Controls include
known-answer finance, configuration, active MRO, persistence round-trip, path
privacy, schema-review availability and disabled marketplace writes. Windows
long-path and 8.3 path representations are normalized.

### Packaging and Windows release

The Python wheel uses a pinned PEP 517 backend and is built in isolation. The
release workflow no longer checks the retired localhost HTTP server. It verifies
the desktop self-test, installed launcher, installed runtime, offline EXE,
source commit, native self-test, SHA-256, WB-only scope and disabled writes.
Installed-copy detection tolerates partial upgrades without requiring a
package-only installer inside the installed application.

## Plateau acceptance gate

The source tree is accepted as a technical plateau only after two consecutive
complete exact-head Linux and Windows runs pass without production-code changes:

```text
P0 = 0
P1 = 0
manifest diff = 0
RUN A = all mandatory gates PASS
RUN B = all mandatory gates PASS on the same SHA
marketplace writes = DISABLED
offline EXE native self-test = PASS
```

Final run identifiers and the distributable hash are release metadata. They may
be recorded in the PR conversation or delivery report without changing this
immutable source tree.

## External boundaries

The following remain outside software remediation:

- Authenticode requires an approved code-signing certificate;
- physical installation and a real-report pilot require the target computer;
- the applicable tax regime requires user or accountant confirmation;
- merging PR #102 into `main` requires a separate explicit decision.

Technical plateau therefore does not equal production authorization.

## Defect summary

The machine-readable register is `docs/evidence/M9_DEFECT_REGISTER.json`.
At candidate freeze it records zero known open P0 and P1 software findings.
Marketplace writes remain disabled and production release remains blocked until
external boundaries are satisfied.
