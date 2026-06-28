# Evidence Chain Contract v1

Status: `DRAFT_FOR_B3_REVIEW`
Risk class: `R2`
Tracking issue: `#9`

## Purpose

The Evidence Chain is an immutable directed acyclic graph that explains and
reproduces a Metric Snapshot from versioned contracts, transformations,
canonical events, source records, and retained source-file bytes.

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

Every node has a stable ID, a positive immutable artifact version, a content
hash, organization ID, mode, scenario boundary, and node-type-specific
metadata.

## Edge types

- `RESULT_DEFINED_BY`;
- `RESULT_CALCULATED_WITH`;
- `RESULT_USES_RESOLUTION`;
- `RESOLUTION_SELECTS_RULE`;
- `PROFILE_SELECTS_RULE`;
- `PROFILE_USES_ROUNDING`;
- `PROFILE_USES_SOURCE_AUTHORITY`;
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

Unknown edge types or node-type-incompatible edges are rejected.

## Required typed paths

For a publishable Metric Snapshot, the graph must provide these exact typed
paths from the root Metric Snapshot node:

- `RESULT_DEFINED_BY` to its Metric Definition;
- `RESULT_CALCULATED_WITH` to its Calculation Profile;
- `RESULT_USES_RESOLUTION` to every Rule Resolution used;
- `RULE_RESOLUTION -> RESOLUTION_SELECTS_RULE -> CONFIGURATION_RULE` for every
  selected Configuration Rule;
- `CALCULATION_PROFILE -> PROFILE_USES_ROUNDING -> ROUNDING_POLICY`;
- `CALCULATION_PROFILE -> PROFILE_USES_SOURCE_AUTHORITY -> SOURCE_AUTHORITY`;
- `RESULT_USES_TRANSFORMATION` to every applied Transformation;
- `RESULT_DERIVED_FROM_EVENT` to every contributing Canonical Event;
- `CANONICAL_EVENT -> EVENT_NORMALIZED_FROM_RECORD -> SOURCE_RECORD`;
- `SOURCE_RECORD -> RECORD_READ_FROM_FILE -> SOURCE_FILE`, including retained
  byte-level SHA-256 and storage locator metadata;
- `RESULT_HAS_FRESHNESS` to the freshness assessment;
- `RESULT_HAS_CONFIDENCE` to the confidence assessment.

Merely making each required node type reachable through arbitrary edges is not
sufficient. When a required typed path is absent, the result is `BLOCKED` with
`EVIDENCE_REQUIRED_PATH_MISSING`.

## Tenant and mode isolation

- Every node must have the same `organization_id` as the root.
- Actual graphs cannot contain Scenario nodes.
- Scenario graphs require one scenario ID and cannot contain another scenario.
- Cross-tenant or cross-mode edges are rejected before publication.

## Acyclicity and history edges

The calculation subgraph must be acyclic. Historical edges
`SNAPSHOT_SUPERSEDES` and `SNAPSHOT_RESTATES` form separate immutable chains and
must not create a cycle.

A graph cycle produces `EVIDENCE_GRAPH_CYCLE` and blocks publication.

## Hash and version verification

For every graph and node reference:

- version is a positive immutable integer;
- content SHA-256 is a lowercase 64-character hexadecimal value;
- aliases such as `latest` are forbidden;
- source-file nodes contain retained-byte SHA-256 and storage locator metadata;
- a storage locator without a matching content hash is not evidence.

## Reproducibility

A verifier receives the root Metric Snapshot and Evidence Chain and must be able
to:

1. verify graph and node hashes;
2. verify tenant and mode boundaries;
3. load all immutable referenced contracts and records;
4. reconstruct selected rule-resolution results;
5. replay transformations in declared order;
6. verify result state, value, unit, currency, rounding, expense boundary,
   freshness, confidence, and limitations;
7. reproduce the root snapshot hash.

B3 defines the replay contract and verifier fixtures. It does not implement the
B1b financial calculation kernel.

## Broken-link behavior

The graph fails closed on:

- missing node or required typed path;
- unknown or type-incompatible edge;
- invalid version or hash;
- tenant or mode contamination;
- transformation-order ambiguity;
- graph or history cycle;
- unapproved Source Authority or Rounding Policy;
- unavailable retained source bytes.

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
