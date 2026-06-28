# Evidence Chain Contract v1

Status: `DRAFT_FOR_B3_REVIEW`
Risk class: `R2`
Tracking: `[BUILD][B3] Define metric snapshots and Evidence Chain contracts`

## Purpose

The Evidence Chain is an immutable directed acyclic graph that explains and
reproduces a Metric Snapshot from versioned contracts, transformations,
canonical events, source records, and source files.

A human-readable explanation without machine-verifiable node references is not
sufficient evidence.

## Graph identity

Every graph contains:

- `evidence_chain_id` and positive version;
- canonical graph SHA-256;
- organization boundary;
- mode and optional scenario identifier;
- root Metric Snapshot reference;
- creation actor, timestamp, reason, and trace identifier;
- ordered node and edge collections.

The graph hash excludes only its own hash field.

## Node types

- `METRIC_SNAPSHOT`;
- `METRIC_DEFINITION`;
- `CALCULATION_PROFILE`;
- `RULE_RESOLUTION`;
- `CONFIGURATION_RULE`;
- `ROUNDING_POLICY`;
- `SOURCE_AUTHORITY`;
- `PRODUCT_MASTER`;
- `TRANSFORMATION`;
- `CANONICAL_EVENT`;
- `SOURCE_RECORD`;
- `SOURCE_FILE`;
- `FRESHNESS_ASSESSMENT`;
- `CONFIDENCE_ASSESSMENT`;
- `RECONCILIATION_RESULT`;
- `APPROVAL`.

Every node has a stable ID, positive immutable version where the node is
versioned, content hash, organization ID, mode, and node-type-specific metadata.

## Edge types

- `RESULT_DEFINED_BY`;
- `RESULT_CALCULATED_WITH`;
- `PROFILE_SELECTS_RULE`;
- `PROFILE_USES_ROUNDING`;
- `PROFILE_USES_SOURCE_AUTHORITY`;
- `RESULT_USES_RESOLUTION`;
- `RESULT_DERIVED_FROM_EVENT`;
- `EVENT_NORMALIZED_FROM_RECORD`;
- `RECORD_READ_FROM_FILE`;
- `RESULT_USES_TRANSFORMATION`;
- `RESULT_USES_PRODUCT_MASTER`;
- `RESULT_HAS_FRESHNESS`;
- `RESULT_HAS_CONFIDENCE`;
- `RESULT_RECONCILED_BY`;
- `ARTIFACT_APPROVED_BY`;
- `SNAPSHOT_SUPERSEDES`;
- `SNAPSHOT_RESTATES`.

Unknown edge types are rejected.

## Required paths

For a publishable Metric Snapshot, the graph must provide paths from the root to:

- its Metric Definition;
- its Calculation Profile;
- the exact Rounding Policy;
- required Source Authority;
- every selected Configuration Rule through a Rule Resolution node;
- every contributing Canonical Event;
- each event's Source Record;
- each record's Source File and SHA-256;
- every applied Transformation;
- actor/reason/trace audit metadata.

When a required path is absent, the result is `BLOCKED` with
`METRIC_EVIDENCE_INCOMPLETE`.

## Tenant and mode isolation

- Every node must have the same `organization_id` as the root unless a later
  approved cross-organization contract explicitly permits a reference.
- Actual graphs cannot contain Scenario nodes.
- Scenario graphs require one scenario ID; Scenario nodes from another scenario
  are forbidden.
- Cross-tenant or cross-mode edges are rejected before graph publication.

## Acyclicity and history edges

The calculation subgraph must be acyclic. Historical edges
`SNAPSHOT_SUPERSEDES` and `SNAPSHOT_RESTATES` form separate chains and cannot
point forward to a descendant or create a cycle.

A graph cycle produces `EVIDENCE_GRAPH_CYCLE` and blocks publication.

## Hash and version verification

For every node:

- content is canonicalized according to its own contract;
- SHA-256 must match the node reference;
- version must be a positive immutable integer when applicable;
- aliases such as `latest` are forbidden;
- source-file nodes contain byte-level SHA-256 and storage locator metadata;
- a locator is not evidence without a matching content hash.

## Reproducibility

A verifier receives the root Metric Snapshot and Evidence Chain and must be able
to:

1. verify graph and node hashes;
2. verify tenant/mode boundaries;
3. load all immutable referenced contracts and records;
4. reconstruct selected rule-resolution results;
5. replay transformations in declared order;
6. verify the result state, value, unit, currency, rounding, expense boundary,
   freshness, confidence, and limitations;
7. reproduce the root snapshot hash.

B3 defines the replay contract but does not implement the B1b financial
calculation kernel.

## Broken-link behavior

The graph fails closed on:

- missing node;
- missing required path;
- unknown node or edge type;
- version alias or non-positive version;
- hash mismatch;
- tenant mismatch;
- Actual/Scenario contamination;
- transformation order ambiguity;
- dependency or history cycle;
- unapproved Source Authority or Rounding Policy;
- source file unavailable without retained immutable bytes.

Independent metrics with complete evidence remain available.

## Diagnostics

- `EVIDENCE_NODE_MISSING`;
- `EVIDENCE_EDGE_INVALID`;
- `EVIDENCE_REQUIRED_PATH_MISSING`;
- `EVIDENCE_HASH_MISMATCH`;
- `EVIDENCE_VERSION_INVALID`;
- `EVIDENCE_TENANT_MISMATCH`;
- `EVIDENCE_MODE_CONTAMINATION`;
- `EVIDENCE_GRAPH_CYCLE`;
- `EVIDENCE_TRANSFORMATION_ORDER_AMBIGUOUS`;
- `EVIDENCE_SOURCE_FILE_UNAVAILABLE`;
- `EVIDENCE_APPROVAL_MISSING`;
- `EVIDENCE_REPRODUCTION_FAILED`.

## Gate

B3 creates contracts, schemas, fixtures, and verifier tests only. Creating a
financial Metric Snapshot by evaluating formulas remains B1b R3 work and is not
authorized.
