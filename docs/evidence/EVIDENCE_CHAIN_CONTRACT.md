# Evidence Chain Contract v1

Status: `DRAFT_FOR_B3_REVIEW`
Risk class: `R2`
Tracking issue: `#9`

## Purpose

The Evidence Chain is an immutable directed acyclic graph that explains and
reproduces a Metric Snapshot from versioned contracts, transformations,
canonical events, source records, retained source-file bytes, and approval
artifacts.

A human-readable explanation without machine-verifiable node references is not
sufficient evidence.

## Graph identity and canonical hash

Every graph contains:

- `evidence_chain_id` and positive version;
- canonical graph SHA-256;
- organization boundary;
- mode and optional scenario identifier;
- hashed root Metric Snapshot reference;
- creation actor, timestamp, reason, and trace identifier;
- ordered node and edge collections.

The graph hash excludes only its own top-level `content_hash`. Canonical bytes
are UTF-8 JSON after removing that field, sorting every object key
lexicographically, using separators `,` and `:`, preserving array order, and
emitting non-ASCII characters as UTF-8. The SHA-256 of those exact bytes must
equal `content_hash`.

## Snapshot/Evidence hash direction

The root Metric Snapshot stores an `evidence_chain_ref` containing only the
stable Evidence Chain identifier and positive version. It deliberately omits
the Evidence Chain content hash. The Evidence Chain is created after the
snapshot and its `root_metric_snapshot_ref` contains the already-computed
Metric Snapshot content hash. The graph hash covers that hashed root reference.
This one-way direction breaks the otherwise circular Snapshot/Chain hash
dependency without weakening root-snapshot integrity.

## Node and edge vocabulary

Supported node types include `METRIC_SNAPSHOT`, `METRIC_DEFINITION`,
`CALCULATION_PROFILE`, `RULE_RESOLUTION`, `CONFIGURATION_RULE`,
`ROUNDING_POLICY`, `SOURCE_AUTHORITY`, `PRODUCT_MASTER`, `TRANSFORMATION`,
`CANONICAL_EVENT`, `SOURCE_RECORD`, `SOURCE_FILE`, `FRESHNESS_ASSESSMENT`,
`CONFIDENCE_ASSESSMENT`, `RECONCILIATION_RESULT`, and `APPROVAL`.

Every node has a stable ID, positive immutable artifact version, content hash,
organization ID, mode, scenario boundary, and node-type-specific metadata.

Supported edges include `RESULT_DEFINED_BY`, `RESULT_CALCULATED_WITH`,
`RESULT_USES_RESOLUTION`, `RESOLUTION_SELECTS_RULE`, `PROFILE_SELECTS_RULE`,
`PROFILE_USES_ROUNDING`, `PROFILE_USES_SOURCE_AUTHORITY`,
`RESULT_DERIVED_FROM_EVENT`, `EVENT_NORMALIZED_FROM_RECORD`,
`RECORD_READ_FROM_FILE`, `RESULT_USES_TRANSFORMATION`,
`RESULT_USES_PRODUCT_MASTER`, `RESULT_HAS_FRESHNESS`,
`RESULT_HAS_CONFIDENCE`, `RESULT_RECONCILED_BY`, `ARTIFACT_APPROVED_BY`,
`SNAPSHOT_SUPERSEDES`, and `SNAPSHOT_RESTATES`.

Unknown edge types or node-type-incompatible edges are rejected.

## Required typed paths

For a publishable Metric Snapshot, the graph must provide these exact typed
paths from the root Metric Snapshot node:

- `RESULT_DEFINED_BY` to its Metric Definition;
- `RESULT_CALCULATED_WITH` to its Calculation Profile;
- `RESULT_USES_RESOLUTION` to every Rule Resolution used;
- `RULE_RESOLUTION -> RESOLUTION_SELECTS_RULE -> CONFIGURATION_RULE`;
- `CALCULATION_PROFILE -> PROFILE_USES_ROUNDING -> ROUNDING_POLICY`;
- `ROUNDING_POLICY -> ARTIFACT_APPROVED_BY -> APPROVAL`;
- `CALCULATION_PROFILE -> PROFILE_USES_SOURCE_AUTHORITY -> SOURCE_AUTHORITY`;
- `SOURCE_AUTHORITY -> ARTIFACT_APPROVED_BY -> APPROVAL`;
- `RESULT_USES_TRANSFORMATION` to every applied Transformation;
- `RESULT_DERIVED_FROM_EVENT` to every contributing Canonical Event;
- `CANONICAL_EVENT -> EVENT_NORMALIZED_FROM_RECORD -> SOURCE_RECORD`;
- `SOURCE_RECORD -> RECORD_READ_FROM_FILE -> SOURCE_FILE`;
- `RESULT_HAS_FRESHNESS` to the freshness assessment;
- `RESULT_HAS_CONFIDENCE` to the confidence assessment.

Every required `APPROVAL` node has metadata `status: APPROVED`, a non-empty
`approved_at`, and a non-empty `approver`. A missing approval path, wrong target
node type, or non-approved metadata produces `EVIDENCE_APPROVAL_MISSING`.

For the root Metric Snapshot, all `RESULT_USES_TRANSFORMATION` edges use a
zero-based, unique, contiguous `sequence` set `0..n-1`. Duplicate, missing,
negative, non-integer, or gapped values produce
`EVIDENCE_TRANSFORMATION_ORDER_AMBIGUOUS`.

Merely making each required node type reachable through arbitrary edges is not
sufficient. A missing required typed path produces
`EVIDENCE_REQUIRED_PATH_MISSING`.

## Tenant, mode, and acyclicity

- Every node has the same `organization_id` as the root.
- Actual graphs cannot contain Scenario nodes.
- Scenario graphs require one scenario ID and cannot contain another scenario.
- Cross-tenant or cross-mode edges are rejected.
- The calculation subgraph must be acyclic.
- `SNAPSHOT_SUPERSEDES` and `SNAPSHOT_RESTATES` form immutable history chains
  and must not create a cycle.

A graph cycle produces `EVIDENCE_GRAPH_CYCLE`.

## Hash, source-byte, and version verification

For every graph and node reference:

- version is a positive immutable integer;
- content SHA-256 is lowercase 64-character hexadecimal;
- the graph hash is recalculated from canonical bytes and compared for equality;
- aliases such as `latest` are forbidden;
- source-file nodes contain retained-byte SHA-256 and storage locator metadata;
- `SOURCE_FILE.artifact_ref.content_hash` equals the retained-byte SHA-256;
- a storage locator without matching retained bytes and hash is not evidence.

## Reproducibility

A verifier receives the root Metric Snapshot and Evidence Chain and must:

1. verify graph and node hashes;
2. verify tenant and mode boundaries;
3. verify rounding-policy and source-authority approval paths and metadata;
4. load immutable referenced contracts, events, records, and source bytes;
5. reconstruct selected rule-resolution results;
6. replay transformations in declared order;
7. verify result state, value, unit, currency, rounding, expense boundary,
   freshness, confidence, and limitations;
8. reproduce the root snapshot hash.

B3 defines the replay contract and verifier fixtures. It does not implement the
B1b financial calculation kernel.

## Fail-closed diagnostics

The graph fails closed on missing nodes or paths, unknown or incompatible
edges, invalid versions or hashes, tenant or mode contamination,
transformation-order ambiguity, graph cycles, unapproved Source Authority or
Rounding Policy, unavailable retained bytes, or replay failure.

Diagnostics:

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

B3 creates contracts, schemas, fixtures, verifier tests, and evidence only.
Creating a financial Metric Snapshot by evaluating formulas remains B1b R3
work and is not authorized.
